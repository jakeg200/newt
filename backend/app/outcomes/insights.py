"""What drives the work: where exceptions come from, so an outcome-owning Newt can fix causes, not just cases.

Generic: the role's config names the dimensions to group by (e.g. the supplier, read from the subject with a
pattern). The "usual" outcome is the most common decision; everything else is an exception. A driver is a value
whose cases end in exceptions much more often than everyone else's.

Initiatives are what an owner Newt proposes about a driver ("ask Contoso to quote PO numbers"). Newt never holds
counterparties' addresses, so it drafts the message for a person to send, then tracks the driver's exception rate
before and after. Attribution stays honest: it reports the change in that driver, nothing grander.
"""

import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import ContextBuilder, utc
from app.models import Apprenticeship, TaskType, User, utcnow
from app.task_types import InsightDimension, TaskTypeConfig

MIN_CASES = 5
MIN_LIFT = 1.5


def dimension_value(snapshot: dict[str, Any], dim: InsightDimension) -> str | None:
    if dim.source == "subject":
        raw = snapshot.get("subject")
    elif dim.source == "sender":
        raw = snapshot.get("from")
    else:
        raw = (snapshot.get("inputs") or {}).get(dim.source)
    if not raw:
        return None
    text = str(raw)
    if dim.pattern:
        m = re.search(dim.pattern, text)
        return m.group(1).strip() if m and m.groups() else None
    return text.strip()[:60]


def find_drivers(items: list[tuple[dict[str, Any], str]], dims: list[InsightDimension], minutes: float = 0,
                 weeks: float = 1.0) -> dict[str, Any]:
    """`items` are (snapshot, decision) pairs. Pure, so it can be tested on exact data."""
    if not items:
        return {"usual": None, "base_rate": None, "drivers": [], "cases": 0}
    usual = Counter(d for _, d in items).most_common(1)[0][0]
    base = sum(d != usual for _, d in items) / len(items)
    out = []
    for dim in dims:
        groups: dict[str, list[str]] = defaultdict(list)
        for snap, decision in items:
            v = dimension_value(snap, dim)
            if v:
                groups[v].append(decision)
        for value, ds in groups.items():
            exc = [d for d in ds if d != usual]
            if len(ds) < MIN_CASES or not exc or not base:
                continue
            rate = len(exc) / len(ds)
            lift = rate / base
            if lift < MIN_LIFT:
                continue
            out.append({"key": f"{dim.name}:{value}", "dimension": dim.name, "value": value, "cases": len(ds), "exceptions": len(exc),
                        "rate": round(rate, 3), "lift": round(lift, 2), "top_exception": Counter(exc).most_common(1)[0][0],
                        "hours_per_week": round(len(exc) * minutes / 60 / weeks, 1) if minutes else None})
    out.sort(key=lambda r: (-r["exceptions"], -r["lift"]))
    return {"usual": usual, "base_rate": round(base, 3), "drivers": out[:8], "cases": len(items)}


def drivers(session: Session, tt: TaskType, now: datetime | None = None, days: int = 365) -> dict[str, Any]:
    task = TaskTypeConfig.model_validate(tt.config)
    now = now or utcnow()
    decided = [d for d in ContextBuilder(session, tt).decided.values() if utc(d.case.received_at) >= now - timedelta(days=days)]
    minutes = (session.get(Apprenticeship, tt.apprenticeship_id).settings or {}).get("minutes_per_case") or 0
    return find_drivers([(d.case.snapshot or {}, d.decision) for d in decided], task.insight_dimensions, minutes, max(1.0, days / 7))


def _initiatives(session: Session, tt: TaskType) -> list[dict[str, Any]]:
    return list(((session.get(Apprenticeship, tt.apprenticeship_id).settings or {}).get("initiatives") or {}).get(tt.id, []))


def _save(session: Session, tt: TaskType, items: list[dict[str, Any]]) -> None:
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    settings = dict(app_.settings or {})
    all_ = {k: list(v) for k, v in (settings.get("initiatives") or {}).items()}
    all_[tt.id] = items
    app_.settings = {**settings, "initiatives": all_}


def propose(session: Session, tt: TaskType, intern: str) -> dict[str, Any] | None:
    """The most worthwhile driver nobody has acted on yet, as an initiative to agree."""
    seen = {i["key"] for i in _initiatives(session, tt)}
    d = drivers(session, tt)
    for r in d["drivers"]:
        if r["key"] in seen:
            continue
        exc = r["top_exception"].replace("_", " ")
        draft = (f"Hello, we've noticed that {round(r['rate'] * 100)}% of the items we receive from you need extra handling "
                 f"({exc}). Could we agree a fix together, so they go straight through? Thank you.")
        return {"key": r["key"], "title": f"Fix the cause with {r['value']}",
                "why": (f"{r['exceptions']} of {r['cases']} {r['value']} cases end in {exc}: {r['lift']}× the usual rate"
                        + (f", about {r['hours_per_week']} h a week." if r["hours_per_week"] else ".")),
                "dimension": r["dimension"], "value": r["value"], "baseline_rate": r["rate"], "draft": draft}
    return None


def accept(session: Session, user: User, tt: TaskType, proposal: dict[str, Any], accepted: bool) -> dict[str, Any]:
    item = {**proposal, "id": str(uuid.uuid4()), "status": "running" if accepted else "declined", "by": user.id,
            "at": utcnow().isoformat()}
    _save(session, tt, [*_initiatives(session, tt), item])
    session.commit()
    return item


def progress(session: Session, tt: TaskType) -> list[dict[str, Any]]:
    """Each running initiative: the driver's exception rate since it started, against its baseline."""
    task = TaskTypeConfig.model_validate(tt.config)
    dims = {d.name: d for d in task.insight_dimensions}
    decided = list(ContextBuilder(session, tt).decided.values())
    usual = Counter(d.decision for d in decided).most_common(1)[0][0] if decided else None
    out = []
    for i in _initiatives(session, tt):
        if i["status"] != "running" or i["dimension"] not in dims:
            out.append({**i, "since": None})
            continue
        start = datetime.fromisoformat(i["at"])
        after = [d for d in decided if utc(d.case.received_at) >= start and dimension_value(d.case.snapshot or {}, dims[i["dimension"]]) == i["value"]]
        rate = round(sum(d.decision != usual for d in after) / len(after), 3) if after else None
        out.append({**i, "since": {"cases": len(after), "rate": rate,
                                   "change": None if rate is None else round(rate - i["baseline_rate"], 3)}})
    return out
