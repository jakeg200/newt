"""Replaying multi-step work without the live systems.

When Newt worked a live case, its lookups into the firm's system were recorded on the prediction's trajectory.
Re-probation (model swaps, rule changes) and backtests replay the same cases with the tools answering lookups from
those recordings. A lookup that was never recorded answers "unavailable" and shows up as a step, so a changed agent
can't pass by asking the live system things the original never could have.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Prediction


def recording_of(trajectory: list[dict[str, Any]] | None) -> dict[str, Any]:
    """kind:ref -> record, for every lookup answered by the firm's system (or already replayed from a recording)."""
    out: dict[str, Any] = {}
    for s in trajectory or []:
        o = s.get("output") or {}
        if s.get("tool") == "lookup_record" and o.get("found") and o.get("source") in ("system", "recorded"):
            out[f"{s['input'].get('kind')}:{s['input'].get('ref')}"] = o["record"]
    return out


def recordings_for(session: Session, case_ids: list[str]) -> dict[str, dict[str, Any]]:
    """For each case, the lookups recorded on its live predictions (the most recent answer wins)."""
    out: dict[str, dict[str, Any]] = {}
    if not case_ids:
        return out
    rows = session.scalars(select(Prediction).where(Prediction.case_id.in_(case_ids), Prediction.run_id.is_(None),
                                                    Prediction.trajectory.is_not(None)).order_by(Prediction.created_at))
    for p in rows:
        out.setdefault(p.case_id, {}).update(recording_of(p.trajectory))
    return out
