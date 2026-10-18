"""The supervisor's view: every Newt on the team, what it carries, what still needs people, and what drives the work."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.capture.service import org_task_type
from app.colleague import career
from app.colleague.service import intern_name
from app.db import get_session
from app.graduation import engine
from app.live import pending_drafts
from app.models import Agent, Apprenticeship, Audit, Case, Prediction, TaskType, User
from app.outcomes import capacity, insights
from app.outcomes.kpis import outcomes

router = APIRouter(tags=["team"])


def _tt(session: Session, user: User, task_type_id: str) -> TaskType:
    try:
        return org_task_type(session, user.org_id, task_type_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/team")
def team(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    out = []
    for tt in session.scalars(select(TaskType).join(Apprenticeship).join(Agent).where(Agent.org_id == user.org_id).order_by(TaskType.name)):
        ev = engine.evaluate(session, tt)
        handbacks = sum(1 for (o,) in session.execute(select(Prediction.output).join(Case, Case.id == Prediction.case_id).where(
            Case.task_type_id == tt.id, Case.status == "open", Prediction.run_id.is_(None))) if ((o or {}).get("hand_back") or {}).get("hand_back"))
        cap = capacity.plan(session, tt)
        r = career.rank(session, tt)
        out.append({
            "id": tt.id, "name": tt.name, "team": session.get(Apprenticeship, tt.apprenticeship_id).team,
            "intern_name": intern_name(session, tt), "rank": r, "title": career.TITLES[r], "status": tt.status,
            "evidence": {"n_above": ev["n_above"], "errors_above": ev["errors_above"], "ucb": ev["ucb"], "alpha": ev["alpha"],
                         "coverage": ev["coverage"], "eligible": ev["eligible"]},
            "needs_people": {"drafts": len(pending_drafts(session, tt)), "handbacks": handbacks,
                             "audits": session.scalar(select(func.count()).select_from(Audit).where(Audit.task_type_id == tt.id, Audit.result.is_(None))) or 0},
            "kpis": [k for k in outcomes(session, tt, weeks=2)["kpis"] if k["this_week"] is not None][:3],
            "capacity": cap, "human_work": capacity.human_work(session, tt),
        })
    total = sum(t["capacity"]["volume_per_week"] for t in out)
    carried = sum(t["capacity"]["current"]["cases_per_week"] for t in out)
    hours = sum(t["capacity"]["current"]["hours_per_week"] or 0 for t in out)
    return {"newts": out, "role": {"newts": len(out), "volume_per_week": round(total, 1), "carried_per_week": round(carried, 1),
                                   "share": round(carried / total, 3) if total else 0.0, "hours_per_week": round(hours, 1)}}


@router.get("/task-types/{task_type_id}/capacity")
def get_capacity(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _tt(session, user, task_type_id)
    return {**capacity.plan(session, tt), "human_work": capacity.human_work(session, tt)}


@router.get("/task-types/{task_type_id}/sample-work")
def sample_work(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any] | None:
    """The most recent case Newt worked with tools, step by step, and how it was scored: Newt showing its work.
    Only cases the mentor has already decided (or Newt finished), so nothing sealed is revealed."""
    from app.models import Comparison

    tt = _tt(session, user, task_type_id)
    row = session.execute(select(Prediction, Case, Comparison).join(Case, Case.id == Prediction.case_id)
                          .join(Comparison, Comparison.prediction_id == Prediction.id)
                          .where(Case.task_type_id == tt.id).order_by(Prediction.created_at.desc()).limit(200)).all()
    for p, case, comp in row:
        if p.trajectory:
            return {"subject": (case.snapshot or {}).get("subject", ""), "steps": p.trajectory, "decision": (p.output or {}).get("decision"),
                    "agreement": comp.effective_agreement, "decision_match": comp.decision_match, "checks": comp.steps,
                    "live": p.run_id is None}
    return None


@router.get("/task-types/{task_type_id}/insights")
def get_insights(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _tt(session, user, task_type_id)
    return {**insights.drivers(session, tt), "initiatives": insights.progress(session, tt), "rank": career.rank(session, tt)}
