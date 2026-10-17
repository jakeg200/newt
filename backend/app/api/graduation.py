from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import live
from app.agents.context import utc
from app.auth import current_user, require_role
from app.capture.service import org_task_type
from app.db import get_session
from app.graduation import drift, engine, track_record
from app.models import ActionLog, Agent, Apprenticeship, Audit, Case, DriftCheck, GraduationEvent, Prediction, TaskType, User

router = APIRouter(tags=["graduation and autonomy"])

mentor = require_role("mentor", "admin")
operator = require_role("mentor", "manager", "admin")
manager_or_admin = require_role("manager", "admin")


def _tt(session: Session, user: User, task_type_id: str) -> TaskType:
    try:
        return org_task_type(session, user.org_id, task_type_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _org_task_types(session: Session, user: User) -> list[TaskType]:
    return list(session.scalars(select(TaskType).join(Apprenticeship).join(Agent).where(Agent.org_id == user.org_id).order_by(TaskType.name)))


@router.get("/board")
def board(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """One row per task type: stage and progress to the next one."""
    rows = []
    for tt in _org_task_types(session, user):
        ev = engine.evaluate(session, tt)
        grad = engine.last_graduation(session, tt)
        since = utc(grad.signed_at) if grad else None
        audits = engine.audits_since(session, tt, since)
        last_drift = session.scalar(select(DriftCheck).where(DriftCheck.task_type_id == tt.id).order_by(DriftCheck.checked_at.desc()).limit(1))
        rows.append({
            "id": tt.id, "name": tt.name, "status": tt.status, "tau": tt.tau,
            "evaluation": {k: ev[k] for k in ("cases", "live_cases", "agreement_rate", "tau", "n_above", "errors_above",
                                               "ucb", "alpha", "coverage", "min_cases", "cases_needed", "more_clean_cases_needed",
                                               "live_above", "eligible", "checks")},
            "supervised_cases": engine.supervised_cases(session, tt, since),
            "supervised_needed": engine.SUPERVISED_BEFORE_AUTONOMY,
            "untouched": live.untouched_rate(session, tt),
            "audits": {"passed": sum(a.result == "pass" for a in audits), "failed": sum(a.result == "fail" for a in audits),
                       "pending": session.scalar(select(func.count()).select_from(Audit).where(Audit.task_type_id == tt.id, Audit.result.is_(None))) or 0},
            "last_drift": {"checked_at": last_drift.checked_at, "drifted": last_drift.drifted} if last_drift else None,
            "graduated_at": grad.signed_at if grad else None,
        })
    return rows


@router.get("/task-types/{task_type_id}/evaluation")
def evaluation(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    ev = engine.evaluate(session, _tt(session, user, task_type_id))
    if user.role not in ("mentor", "admin"):  # examples show case content
        ev = {k: v for k, v in ev.items() if k not in ("agreements", "disagreements", "hand_backs")}
    return ev


class GraduateIn(BaseModel):
    to: Literal["supervised", "autonomous"]


@router.post("/task-types/{task_type_id}/graduate")
def graduate(task_type_id: str, body: GraduateIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _tt(session, user, task_type_id)
    try:
        ev = engine.sign(session, tt, user, body.to)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except engine.GraduationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"status": tt.status, "tau": tt.tau, "event_id": ev.id, "signed_at": ev.signed_at}


@router.get("/task-types/{task_type_id}/track-record")
def get_track_record(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    return track_record.build(session, _tt(session, user, task_type_id))


@router.get("/task-types/{task_type_id}/track-record.pdf")
def get_track_record_pdf(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> Response:
    tt = _tt(session, user, task_type_id)
    data = track_record.pdf(track_record.build(session, tt))
    name = "".join(ch if ch.isalnum() else "-" for ch in tt.name.lower()).strip("-")
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="track-record-{name}.pdf"'})


@router.get("/task-types/{task_type_id}/history")
def history(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    tt = _tt(session, user, task_type_id)
    events = session.scalars(select(GraduationEvent).where(GraduationEvent.task_type_id == tt.id).order_by(GraduationEvent.signed_at.desc()))
    return [{"id": e.id, "from": e.from_status, "to": e.to_status, "signed_by": e.signed_by, "signed_at": e.signed_at,
             "reason": e.evidence.get("reason"), "recertified": e.evidence.get("recertified"),
             "ucb": e.evidence.get("ucb"), "duration_s": e.evidence.get("duration_s")} for e in events]


@router.post("/task-types/{task_type_id}/drift-check", status_code=status.HTTP_201_CREATED)
def drift_check(task_type_id: str, user: User = Depends(operator), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _tt(session, user, task_type_id)
    row = drift.check(session, tt)
    return {"drifted": row.drifted, "result": row.result, "status": tt.status}


class SwapIn(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=50)


@router.post("/agents/{agent_id}/swap")
def swap(agent_id: str, body: SwapIn, user: User = Depends(manager_or_admin), session: Session = Depends(get_session)) -> dict[str, Any]:
    agent = session.get(Agent, agent_id)
    if agent is None or agent.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    runs = engine.swap_model(session, agent, user, body.model, body.version)
    return {"agent_id": agent.id, "model": agent.model, "version": agent.version, "reprobation_runs": [r.id for r in runs]}


# Supervised practice, hand-backs, audits, digest --------------------------------------------

@router.get("/supervised")
def supervised(task_type_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return live.pending_drafts(session, _tt(session, user, task_type_id))


class DraftDecision(BaseModel):
    decision: str | None = None
    fields: dict[str, Any] | None = None
    text_outputs: dict[str, str] | None = None
    note: str | None = Field(default=None, max_length=2000)


def _decide(session: Session, user: User, prediction_id: str, body: DraftDecision, approve: bool) -> dict[str, Any]:
    try:
        return live.decide_draft(session, user, prediction_id, approve=approve, decision=body.decision, fields=body.fields,
                                 text_outputs=body.text_outputs, note=body.note)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/supervised/{prediction_id}/approve")
def approve(prediction_id: str, body: DraftDecision, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _decide(session, user, prediction_id, body, approve=True)


@router.post("/supervised/{prediction_id}/reject")
def reject(prediction_id: str, body: DraftDecision, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    if not body.decision:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "say what you decided instead")
    return _decide(session, user, prediction_id, body, approve=False)


@router.get("/handbacks")
def handbacks(task_type_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Live cases a graduated agent handed back, still waiting for a person."""
    tt = _tt(session, user, task_type_id)
    rows = session.execute(select(Prediction, Case).join(Case, Case.id == Prediction.case_id)
                           .where(Case.task_type_id == tt.id, Prediction.run_id.is_(None), Case.status == "open")
                           .order_by(Case.received_at.desc()).limit(100)).all()
    out = []
    for p, case in rows:
        hb = (p.output or {}).get("hand_back") or {}
        if hb.get("hand_back"):
            snap = case.snapshot or {}
            out.append({"prediction_id": p.id, "case": {"id": case.id, "received_at": case.received_at, "subject": snap.get("subject", ""),
                                                        "inputs": snap.get("inputs", {})},
                        "reasons": hb.get("reasons", []), "agent_decision": (p.output or {}).get("decision"), "confidence": p.confidence})
    return out


@router.get("/audits")
def audits(task_type_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return live.audit_queue(session, _tt(session, user, task_type_id))


class AuditIn(BaseModel):
    decision: str
    fields: dict[str, Any] | None = None


@router.post("/audits/{audit_id}")
def submit_audit(audit_id: str, body: AuditIn, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return live.submit_audit(session, user, audit_id, body.decision, body.fields)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/autonomy/digest")
def digest(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    """What the agent did on its own, and what it didn't: counts for everyone, details for the mentor."""
    tt = _tt(session, user, task_type_id)
    rows = session.execute(select(ActionLog, Case).join(Case, Case.id == ActionLog.case_id)
                           .where(Case.task_type_id == tt.id, ActionLog.mode == "autonomous")
                           .order_by(ActionLog.created_at.desc()).limit(200)).all()
    executed = [a for a, _ in rows if a.status == "executed"]
    blocked = [a for a, _ in rows if a.status == "blocked"]
    handled = {a.case_id for a in executed}
    out: dict[str, Any] = {"status": tt.status, "cases_handled": len(handled), "actions_executed": len(executed),
                           "actions_blocked": len(blocked), "handbacks": len(handbacks(task_type_id, user, session)) if user.role in ("mentor", "admin") else None,
                           "audits_pending": session.scalar(select(func.count()).select_from(Audit).where(Audit.task_type_id == tt.id, Audit.result.is_(None))) or 0}
    if user.role in ("mentor", "admin"):
        out["recent"] = [{"case_id": c.id, "subject": (c.snapshot or {}).get("subject", ""), "action": a.action, "status": a.status,
                          "payload": a.payload, "reasons": a.policy_check.get("reasons", []), "at": a.created_at} for a, c in rows[:50]]
    return out
