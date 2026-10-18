"""Capacity planning: how much of a role Newt can safely carry, and what's left for people.

From the role's weekly volume, the share of its work certified at the firm's risk limit (the same `choose_tau` the
graduation gate uses), and the manager's minutes per case: hours freed per week, and what stays human work. The
what-if shows the same at other risk limits, so a manager can see the trade-off before changing anything. It
plans; it never changes the gate.
"""

from collections import Counter
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import utc
from app.eval.stats import choose_tau
from app.graduation import engine
from app.models import Apprenticeship, Case, TaskType, utcnow
from app.task_types import TaskTypeConfig

WHAT_IF = (0.01, 0.02, 0.05, 0.10)


def weekly_volume(session: Session, tt: TaskType, weeks: int = 12) -> float:
    cases = list(session.scalars(select(Case.received_at).where(Case.task_type_id == tt.id, Case.connection_id.is_not(None))))
    if not cases:
        return 0.0
    times = sorted(utc(c) for c in cases)
    span_weeks = max(1.0, (times[-1] - times[0]).days / 7)
    recent = [t for t in times if t >= utcnow() - timedelta(weeks=weeks)]
    return round(len(recent) / weeks, 1) if len(recent) >= weeks else round(len(times) / span_weeks, 1)


def plan(session: Session, tt: TaskType) -> dict[str, Any]:
    task = TaskTypeConfig.model_validate(tt.config)
    scores, errors = engine.scores_and_errors(session, tt)
    volume = weekly_volume(session, tt)
    minutes = (session.get(Apprenticeship, tt.apprenticeship_id).settings or {}).get("minutes_per_case")

    def at(alpha: float) -> dict[str, Any]:
        th = choose_tau(scores, errors, alpha)
        share = th.coverage if th.tau is not None else 0.0
        handled = volume * share
        return {"alpha": alpha, "share": round(share, 3), "cases_per_week": round(handled, 1),
                "hours_per_week": round(handled * minutes / 60, 1) if minutes else None, "error_bound": round(th.ucb, 4),
                "certified": th.tau is not None}

    current = at(task.alpha)
    return {"volume_per_week": volume, "alpha": task.alpha, "current": current, "what_if": [at(a) for a in WHAT_IF],
            "human_cases_per_week": round(volume - current["cases_per_week"], 1), "evidence_cases": len(scores),
            "minutes_per_case": minutes}


def human_work(session: Session, tt: TaskType, days: int = 90) -> list[dict[str, Any]]:
    """What still comes to people: the reasons work is handed back, most common first."""
    from app.models import Prediction

    rows = session.execute(select(Prediction.output).join(Case, Case.id == Prediction.case_id).where(
        Case.task_type_id == tt.id, Prediction.run_id.is_(None), Prediction.created_at >= utcnow() - timedelta(days=days))).all()
    reasons: Counter[str] = Counter()
    for (out,) in rows:
        hb = (out or {}).get("hand_back") or {}
        if hb.get("hand_back"):
            for r in hb.get("reasons") or ["unsure"]:
                reasons[str(r).split(":")[0][:60]] += 1
    return [{"reason": r, "cases": n} for r, n in reasons.most_common(5)]
