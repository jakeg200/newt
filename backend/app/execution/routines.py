"""Routines: for each decision, which actions Newt carries out and whether it follows up.

Newt proposes a routine from the role's config and what the mentor actually does (do they usually reply when they
choose this?). The mentor approves or edits it, like agreeing how a new hire should handle something. Without an
approved routine Newt proposes every allowed action (the policy still checks each one). Changing an approved routine
is a procedure change, so a graduated Newt re-certifies.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Apprenticeship, Case, HumanAction, TaskType, User, utcnow
from app.task_types import TaskTypeConfig

REPLY_ACTIONS = ("draft_reply", "send_reply")
REPLY_SHARE = 0.3  # propose a reply when the mentor replied on at least this share of cases with that decision


class RoutineError(ValueError):
    pass


def _reply_shares(session: Session, tt: TaskType) -> dict[str, float]:
    seen: dict[str, list[bool]] = {}
    rows = session.execute(select(HumanAction.payload).join(Case, Case.id == HumanAction.case_id).where(
        Case.task_type_id == tt.id, HumanAction.source != "audit")).all()
    for (payload,) in rows:
        d = payload.get("decision")
        if d:
            seen.setdefault(d, []).append(bool(payload.get("text_outputs")))
    return {d: sum(v) / len(v) for d, v in seen.items() if v}


def proposed(session: Session, tt: TaskType) -> dict[str, dict[str, Any]]:
    task = TaskTypeConfig.model_validate(tt.config)
    shares = _reply_shares(session, tt)
    reply = next((a for a in REPLY_ACTIONS if a in task.allowed_actions), None)
    defaults = ((session.get(Apprenticeship, tt.apprenticeship_id).settings or {}).get("routine_defaults") or {}).get(tt.id, {})
    out = {}
    for d in task.decision:
        if d in defaults and not shares:  # a role pack's starting point, until the team's own history says otherwise
            out[d] = {"steps": list(defaults[d]["steps"]), "follow_up_days": defaults[d].get("follow_up_days"), "status": "proposed",
                      "from_pack": True}
            continue
        steps = [a for a in ("set_status", "set_field") if a in task.allowed_actions]
        if reply and shares.get(d, 0.0) >= REPLY_SHARE:
            steps.append(reply)
        out[d] = {"steps": steps, "follow_up_days": task.follow_up_days.get(d), "status": "proposed", "reply_share": round(shares.get(d, 0.0), 2)}
    return out


def current(session: Session, tt: TaskType) -> dict[str, dict[str, Any]]:
    approved = (session.get(Apprenticeship, tt.apprenticeship_id).settings or {}).get("routines", {}).get(tt.id, {})
    return {d: ({**r, "status": "approved"} if d in approved else r) for d, r in proposed(session, tt).items()} | \
           {d: {**r, "status": "approved"} for d, r in approved.items()}


def steps_for(session: Session, tt: TaskType, decision: str | None) -> set[str] | None:
    """The approved steps for a decision, or None when there's no approved routine (then every allowed action)."""
    r = (session.get(Apprenticeship, tt.apprenticeship_id).settings or {}).get("routines", {}).get(tt.id, {}).get(decision or "")
    return set(r["steps"]) if r else None


def follow_up_days(session: Session, tt: TaskType, decision: str | None) -> int | None:
    r = current(session, tt).get(decision or "")
    return r.get("follow_up_days") if r else None


def validate(tt: TaskType, decision: str, steps: list[str], follow_up: int | None) -> TaskTypeConfig:
    task = TaskTypeConfig.model_validate(tt.config)
    if decision not in task.decision:
        raise RoutineError(f"decision must be one of {task.decision}")
    unknown = sorted(set(steps) - set(task.allowed_actions))
    if unknown:
        raise RoutineError(f"{', '.join(unknown)} isn't allowed for this role")
    if follow_up is not None and not 1 <= follow_up <= 60:
        raise RoutineError("follow-up must be between 1 and 60 days")
    return task


def is_live(session: Session, tt: TaskType, decision: str) -> bool:
    """An approved routine Newt is already working by: changing it changes live work, so it's tested first."""
    approved = (session.get(Apprenticeship, tt.apprenticeship_id).settings or {}).get("routines", {}).get(tt.id, {})
    return decision in approved and tt.status in ("supervised", "autonomous")


def approve(session: Session, user: User, tt: TaskType, decision: str, steps: list[str], follow_up: int | None,
            recertify: bool = True) -> dict[str, Any]:
    task = validate(tt, decision, steps, follow_up)
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    settings = dict(app_.settings or {})
    routines = {k: dict(v) for k, v in settings.get("routines", {}).items()}
    mine = dict(routines.get(tt.id, {}))
    previous = mine.get(decision)
    mine[decision] = {"steps": [s for s in task.allowed_actions if s in steps], "follow_up_days": follow_up,
                      "version": (previous or {}).get("version", 0) + 1, "approved_by": user.id, "approved_at": utcnow().isoformat()}
    routines[tt.id] = mine
    app_.settings = {**settings, "routines": routines}
    if recertify and previous and tt.status in ("supervised", "autonomous"):
        from app.graduation.engine import on_procedure_change

        on_procedure_change(session, tt, user, f"routine changed: {decision}")
    session.commit()
    return {**mine[decision], "status": "approved"}
