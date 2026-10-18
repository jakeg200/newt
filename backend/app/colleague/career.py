"""Newt's career: it joins as a new starter and earns every step on its record.

new starter  orientation: reading the handbook, nothing approved yet
intern       shadowing: sealed predictions, scored against the mentor
junior       supervised: drafts the work, the mentor approves each one
graduate     autonomous: does routine work alone, hands back the unusual, spot-checked
senior       graduate who has earned extra responsibilities (e.g. chasing on its own), granted by the manager

The gates for intern → junior → graduate are the existing evidence and sign-offs (`graduation/engine.py`).
Senior responsibilities are requested by Newt with its record and granted by a manager.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import utc
from app.graduation import engine
from app.models import Agent, Apprenticeship, Handbook, TaskType, User, utcnow

RANKS = ("new_starter", "intern", "junior", "graduate", "senior")
TITLES = {"new_starter": "New starter", "intern": "Intern", "junior": "Junior", "graduate": "Graduate", "senior": "Senior"}
SENIOR_AFTER_AUDITS = 3  # clean spot checks before Newt may ask for more responsibility


class CareerError(ValueError):
    pass


def responsibilities(session: Session, tt: TaskType) -> dict[str, Any]:
    return (session.get(Apprenticeship, tt.apprenticeship_id).settings or {}).get("responsibilities", {}).get(tt.id, {})


def rank(session: Session, tt: TaskType) -> str:
    if tt.status == "autonomous":
        return "senior" if responsibilities(session, tt).get("follow_ups") else "graduate"
    if tt.status == "supervised":
        return "junior"
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    org_id = session.get(Agent, app_.agent_id).org_id
    approved = session.scalar(select(Handbook.id).where(Handbook.org_id == org_id, Handbook.team == app_.team, Handbook.status == "approved").limit(1))
    return "intern" if approved else "new_starter"


def senior_ready(session: Session, tt: TaskType) -> dict[str, Any] | None:
    """Evidence for asking to take on follow-ups: a clean run of spot checks since graduating."""
    from app.execution.routines import current

    if tt.status != "autonomous" or responsibilities(session, tt).get("follow_ups"):
        return None
    if not any(r.get("follow_up_days") for r in current(session, tt).values()):
        return None
    grad = engine.last_graduation(session, tt)
    audits = engine.audits_since(session, tt, utc(grad.signed_at) if grad else None)
    passed, failed = sum(a.result == "pass" for a in audits), sum(a.result == "fail" for a in audits)
    if failed or passed < SENIOR_AFTER_AUDITS:
        return None
    return {"audits_passed": passed}


def grant(session: Session, user: User, tt: TaskType, responsibility: str) -> dict[str, Any]:
    if user.role not in ("manager", "admin"):
        raise PermissionError("new responsibilities are the manager's call")
    if responsibility != "follow_ups":
        raise CareerError("unknown responsibility")
    if senior_ready(session, tt) is None:
        raise CareerError("Newt hasn't earned this yet")
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    settings = dict(app_.settings or {})
    resp = {k: dict(v) for k, v in settings.get("responsibilities", {}).items()}
    resp.setdefault(tt.id, {})[responsibility] = {"granted_by": user.id, "at": utcnow().isoformat()}
    career = {k: list(v) for k, v in settings.get("career", {}).items()}
    career.setdefault(tt.id, []).append({"to": "senior", "responsibility": responsibility, "by": user.id, "at": utcnow().isoformat()})
    app_.settings = {**settings, "responsibilities": resp, "career": career}
    session.commit()
    return {"rank": rank(session, tt)}
