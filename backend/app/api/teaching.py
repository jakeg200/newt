from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user, require_role

from app.capture.service import org_task_type
from app.config import get_settings
from app.db import get_session

from app.learning import improve
from app.learning import rules as rules_mod
from app.learning import teaching
from app.models import Case, HumanAction, Improvement, Rule, TaskType, User

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


class RuleIn(BaseModel):
    task_type_id: str
    text: str = Field(min_length=5, max_length=500)


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _task_type(session, user, body.task_type_id)
    imp = improve.propose(session, tt, user, "add_rule", text=body.text)
    session.commit()
    return {**_rule_out(session.get(Rule, imp.rule_id)), "improvement": improve.out(imp)}


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
    imp = None
    if body.text is not None and body.text.strip() != rule.text and rule.status == "active":
        imp = improve.propose(session, tt, user, "edit_rule", rule=rule, text=body.text)
    elif body.status == "active" and rule.status != "active":
        imp = improve.propose(session, tt, user, "activate_rule", rule=rule, signal="inferred" if rule.source == "inferred" else "taught")
    elif body.status == "retired" and rule.status == "active":
        imp = improve.propose(session, tt, user, "retire_rule", rule=rule)
    else:  # not live, so nothing to test: edits to proposals, retiring a proposal
        rules_mod.update(session, tt, rule, text=body.text, status=body.status)
    session.commit()
    return {**_rule_out(rule), "improvement": improve.out(imp) if imp else None}


@router.get("/task-types/{task_type_id}/improvements")
def list_improvements(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return improve.log_of(session, _task_type(session, user, task_type_id))


def _improvement(session: Session, user: User, improvement_id: str) -> Improvement:
    imp = session.get(Improvement, improvement_id)
    if imp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "change not found")
    _task_type(session, user, imp.task_type_id)  # org check
    return imp


@router.get("/improvements/{improvement_id}")
def get_improvement(improvement_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    return improve.out(_improvement(session, user, improvement_id))


class PromoteIn(BaseModel):
    keep_anyway: bool = False


@router.post("/improvements/{improvement_id}/promote")
def promote_improvement(improvement_id: str, body: PromoteIn | None = None, user: User = Depends(mentor),
                        session: Session = Depends(get_session)) -> dict[str, Any]:
    imp = _improvement(session, user, improvement_id)
    try:
        return improve.out(improve.promote(session, user, imp, keep_anyway=(body or PromoteIn()).keep_anyway))
    except improve.ImproveError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/improvements/{improvement_id}/reject")
def reject_improvement(improvement_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    imp = _improvement(session, user, improvement_id)
    try:
        return improve.out(improve.reject(session, user, imp))
    except improve.ImproveError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


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
