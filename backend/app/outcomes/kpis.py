"""Outcome KPIs: what the role delivered each week, against the targets the team set.

Only work confirmed done in the firm's systems counts as finished by Newt (`Case.completed_at`). Cases a person
decided count towards the total, so the share Newt carries is honest. Metrics are generic; which ones a role cares
about, and the targets, come from the task-type config, with the manager's overrides on top. Nothing here measures
a person.
"""

import statistics
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import utc
from app.models import Apprenticeship, Case, GraduationEvent, HumanAction, TaskType, utcnow
from app.task_types import KpiSpec, TaskTypeConfig

DEFAULT_KPIS = [KpiSpec(metric="completed_by_newt"), KpiSpec(metric="share_by_newt", target=0.5),
                KpiSpec(metric="median_hours_to_complete", direction="down"), KpiSpec(metric="hours_returned")]
LABELS = {"completed_by_newt": "Finished by Newt", "completed_total": "Finished in total", "share_by_newt": "Share Newt finished",
          "median_hours_to_complete": "Hours to finish", "backlog_open": "Waiting", "hours_returned": "Hours given back", "value": "Value"}


def week_windows(now: datetime, weeks: int) -> list[tuple[datetime, datetime]]:
    """Rolling 7-day windows ending now, oldest first."""
    return [(now - timedelta(days=7 * (i + 1)), now - timedelta(days=7 * i)) for i in reversed(range(weeks))]


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def on_track(value: float | None, target: float | None, direction: str) -> bool | None:
    if value is None or target is None:
        return None
    return value >= target if direction == "up" else value <= target


def trend(this: float | None, last: float | None) -> float | None:
    return None if this is None or last is None else round(this - last, 4)


def _week(completed: list[tuple[datetime, datetime]], decided_by_people: list[datetime], start: datetime, end: datetime,
          minutes: float | None, hourly: float | None) -> dict[str, Any]:
    newt = [(r, c) for r, c in completed if start <= c < end]
    people = [a for a in decided_by_people if start <= a < end]
    total = len(newt) + len(people)
    hours = round(len(newt) * minutes / 60, 1) if minutes else None
    return {"start": start.isoformat(), "end": end.isoformat(), "completed_by_newt": len(newt), "completed_total": total,
            "share_by_newt": round(len(newt) / total, 4) if total else None,
            "median_hours_to_complete": median([(c - r).total_seconds() / 3600 for r, c in newt]),
            "hours_returned": hours, "value": round(hours * hourly, 2) if hours is not None and hourly else None}


def specs(tt: TaskType, settings: dict[str, Any]) -> list[KpiSpec]:
    task = TaskTypeConfig.model_validate(tt.config)
    overrides = (settings.get("kpi_targets") or {}).get(tt.id, {})
    return [s.model_copy(update={"target": overrides.get(s.metric, s.target)}) for s in (task.kpis or DEFAULT_KPIS)]


def outcomes(session: Session, tt: TaskType, now: datetime | None = None, weeks: int = 8) -> dict[str, Any]:
    now = now or utcnow()
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    settings = app_.settings or {}
    cases = list(session.scalars(select(Case).where(Case.task_type_id == tt.id, Case.is_backtest.is_(False))))
    completed = [(utc(c.received_at), utc(c.completed_at)) for c in cases if c.completed_at]
    done_ids = {c.id for c in cases if c.completed_at}
    people = [utc(a.acted_at) for a, c in session.execute(select(HumanAction, Case).join(Case, Case.id == HumanAction.case_id).where(
        Case.task_type_id == tt.id, Case.is_backtest.is_(False), HumanAction.source != "audit")).all() if c.id not in done_ids]
    series = [_week(completed, people, s, e, settings.get("minutes_per_case"), settings.get("hourly_cost")) for s, e in week_windows(now, weeks)]
    backlog = sum(1 for c in cases if c.status == "open")
    this, last = series[-1], series[-2] if len(series) > 1 else {}
    kpis = []
    for s in specs(tt, settings):
        value = backlog if s.metric == "backlog_open" else this.get(s.metric)
        kpis.append({"metric": s.metric, "label": s.label or LABELS[s.metric], "target": s.target, "direction": s.direction,
                     "this_week": value, "last_week": None if s.metric == "backlog_open" else last.get(s.metric),
                     "trend": None if s.metric == "backlog_open" else trend(value, last.get(s.metric)),
                     "on_track": on_track(value, s.target, s.direction),
                     "series": [w.get(s.metric) for w in series] if s.metric != "backlog_open" else None})
    events = [{"at": utc(e.signed_at).isoformat(), "from": e.from_status, "to": e.to_status}
              for e in session.scalars(select(GraduationEvent).where(GraduationEvent.task_type_id == tt.id).order_by(GraduationEvent.signed_at))]
    events += [{"at": v["at"], "from": "autonomous", "to": v.get("to", "senior")} for v in (settings.get("career") or {}).get(tt.id, [])]
    events += [{"at": i["at"], "from": "", "to": "initiative", "title": i.get("title")}
               for i in (settings.get("initiatives") or {}).get(tt.id, []) if i.get("status") == "running"]
    from app.execution.destinations import connected

    return {"weeks": series, "kpis": kpis, "backlog_open": backlog, "promotions": sorted(events, key=lambda e: e["at"]),
            "simulated": not connected(session, tt), "since_start": {"completed_by_newt": len(completed)}}
