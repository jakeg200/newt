from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user, require_role
from app.backtest.runner import create_repredict
from app.capture.service import org_task_type
from app.config import get_settings
from app.db import get_session
from app.learning import rules as rules_mod
from app.learning import teaching
from app.models import Agent, Apprenticeship, Case, HumanAction, Rule, TaskType, User

router = APIRouter(tags=["teaching"])

mentor = require_role("mentor", "admin")


def _task_type(session: Session, user: User, task_type_id: str) -> TaskType:
    try:
        return org_task_type(session, user.org_id, task_type_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/teaching/queue")
def get_queue(task_type_id: str, limit: int = Query(default=20, ge=0, le=100), user: User = Depends(mentor),
              session: Session = Depends(get_session)) -> dict[str, Any]:
    return teaching.queue(session, _task_type(session, user, task_type_id), limit)


@router.get("/teaching/summary")
def get_summary(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    """Counts only, so managers can see it too."""
    tt = _task_type(session, user, task_type_id)
    out = teaching.summary(session, tt)
    rp = teaching.latest_repredict(session, tt.id)
    out["latest_repredict"] = {"id": rp.id, "status": rp.status, "reason": rp.params.get("reason"),
                               "changed": rp.stats.get("changed"), "compared": rp.stats.get("compared_with_previous"),
                               "created_at": rp.created_at} if rp else None
    return out


class LessonIn(BaseModel):
    prediction_id: str
    attribution: Literal["intern_wrong", "both_fine", "mentor_changed", "couldnt_know"]
    note: str | None = Field(default=None, max_length=2000)
    reply_ok: bool | None = None
    rule_text: str | None = Field(default=None, max_length=500)


@router.post("/lessons", status_code=status.HTTP_201_CREATED)
def post_lesson(body: LessonIn, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return teaching.record_lesson(session, user, body.prediction_id, body.attribution, note=body.note,
                                      reply_ok=body.reply_ok, rule_text=body.rule_text)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except teaching.TeachingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def _rule_out(r: Rule) -> dict[str, Any]:
    return {"id": r.id, "text": r.text, "decision": r.decision, "source": r.source, "status": r.status,
            "version": r.version, "examples": len(r.supporting_case_ids or []), "stats": r.stats,
            "evidence_until": r.evidence_until, "created_at": r.created_at, "updated_at": r.updated_at}


@router.get("/rules")
def list_rules(task_type_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    tt = _task_type(session, user, task_type_id)
    rules = session.scalars(select(Rule).where(Rule.apprenticeship_id == tt.apprenticeship_id).order_by(Rule.created_at, Rule.id))
    return [_rule_out(r) for r in rules]


class InferIn(BaseModel):
    task_type_id: str


@router.post("/rules/infer", status_code=status.HTTP_201_CREATED)
def infer_rules(body: InferIn, user: User = Depends(mentor), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    tt = _task_type(session, user, body.task_type_id)
    provider = None
    settings = get_settings()
    if settings.anthropic_api_key:
        from app.llm.provider import AnthropicProvider

        provider = AnthropicProvider(model=settings.apprentice_model, api_key=settings.anthropic_api_key)
    return [_rule_out(r) for r in rules_mod.infer(session, tt, user, provider)]


def _agent(session: Session, tt: TaskType) -> Agent:
    return session.get(Agent, session.get(Apprenticeship, tt.apprenticeship_id).agent_id)


class RuleIn(BaseModel):
    task_type_id: str
    text: str = Field(min_length=5, max_length=500)


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _task_type(session, user, body.task_type_id)
    rule = rules_mod.write(session, tt, user, body.text)
    session.flush()
    run = create_repredict(session, user, tt, _agent(session, tt), reason=f"new rule: {rule.text[:80]}")
    session.commit()
    return {**_rule_out(rule), "repredict_run_id": run.id if run else None}


class RulePatch(BaseModel):
    text: str | None = Field(default=None, min_length=5, max_length=500)
    status: Literal["proposed", "active", "retired"] | None = None


def _rule(session: Session, user: User, rule_id: str) -> tuple[Rule, TaskType]:
    rule = session.get(Rule, rule_id)
    tt = session.scalar(select(TaskType).where(TaskType.apprenticeship_id == rule.apprenticeship_id)) if rule else None
    if rule is None or tt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    _task_type(session, user, tt.id)  # org check
    return rule, tt


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: str, body: RulePatch, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    rule, tt = _rule(session, user, rule_id)
    affects = rules_mod.update(session, tt, rule, text=body.text, status=body.status)
    run = None
    if affects:
        what = "edited" if body.text else {"active": "accepted", "retired": "retired"}.get(body.status or "", "changed")
        run = create_repredict(session, user, tt, _agent(session, tt), reason=f"rule {what}: {rule.text[:80]}")
    session.commit()
    return {**_rule_out(rule), "repredict_run_id": run.id if run else None}


@router.get("/rules/{rule_id}/examples")
def rule_examples(rule_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rule, _ = _rule(session, user, rule_id)
    ids = rule.supporting_case_ids or []
    cases = {c.id: c for c in session.scalars(select(Case).where(Case.id.in_(ids)))} if ids else {}
    decisions: dict[str, str] = {}
    for a in session.scalars(select(HumanAction).where(HumanAction.case_id.in_(ids)).order_by(HumanAction.acted_at)) if ids else []:
        if a.payload.get("decision") and a.case_id not in decisions:
            decisions[a.case_id] = a.payload["decision"]
    return [{"case_id": cid, "received_at": cases[cid].received_at, "subject": (cases[cid].snapshot or {}).get("subject", ""),
             "inputs": (cases[cid].snapshot or {}).get("inputs", {}), "decision": decisions.get(cid)}
            for cid in ids if cid in cases]
