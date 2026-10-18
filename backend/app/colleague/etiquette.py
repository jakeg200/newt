"""When Newt may interrupt someone, like a considerate colleague.

Work (a draft to approve, a case handed back) is the person's job anyway, so it arrives in working hours without
using the budget. Questions do use it: a few a day at most, only in working hours. Urgent things arrive at once in
working hours, and out of hours only if the person has said so. Low-priority things wait for the next stand-up.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

Urgency = Literal["low", "normal", "urgent"]
Kind = Literal["work", "question", "summary"]


@dataclass(frozen=True)
class Prefs:
    timezone: str = "Europe/London"
    start: time = time(9, 0)
    end: time = time(17, 30)
    workdays: tuple[int, ...] = (0, 1, 2, 3, 4)  # Monday = 0
    questions_per_day: int = 5
    urgent_out_of_hours: bool = False
    calls: bool = True  # may Newt ask for a quick call
    channel: str = "app"

    def as_dict(self) -> dict[str, Any]:
        return {"timezone": self.timezone, "start": self.start.strftime("%H:%M"), "end": self.end.strftime("%H:%M"),
                "workdays": list(self.workdays), "questions_per_day": self.questions_per_day,
                "urgent_out_of_hours": self.urgent_out_of_hours, "calls": self.calls, "channel": self.channel}


def _hhmm(value: Any, default: time) -> time:
    try:
        h, m = str(value).split(":")
        return time(int(h), int(m))
    except (ValueError, TypeError):
        return default


def prefs_from(raw: dict[str, Any] | None) -> Prefs:
    """Read a person's stored preferences, falling back to sensible defaults for anything missing or invalid."""
    raw, d = raw or {}, Prefs()
    tz = str(raw.get("timezone") or d.timezone)
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        tz = d.timezone
    start, end = _hhmm(raw.get("start"), d.start), _hhmm(raw.get("end"), d.end)
    if end <= start:
        start, end = d.start, d.end
    days = tuple(sorted({int(x) for x in raw.get("workdays", d.workdays) if str(x).isdigit() and 0 <= int(x) <= 6})) or d.workdays
    budget = raw.get("questions_per_day", d.questions_per_day)
    budget = max(0, min(20, int(budget))) if isinstance(budget, (int, float)) else d.questions_per_day
    channel = raw.get("channel") if raw.get("channel") in ("app", "email", "slack", "teams") else d.channel
    return Prefs(tz, start, end, days, budget, bool(raw.get("urgent_out_of_hours", False)), bool(raw.get("calls", True)), channel)


def _local(now: datetime, prefs: Prefs) -> datetime:
    return now.astimezone(ZoneInfo(prefs.timezone))


def working(now: datetime, prefs: Prefs) -> bool:
    local = _local(now, prefs)
    return local.weekday() in prefs.workdays and prefs.start <= local.time() < prefs.end


def next_start(now: datetime, prefs: Prefs, *, after_today: bool = False) -> datetime:
    """The next moment the working day begins (today if it hasn't started yet, unless `after_today`)."""
    local = _local(now, prefs)
    day = local.date()
    for offset in range(0 if not after_today else 1, 9):
        d = day + timedelta(days=offset)
        start = datetime.combine(d, prefs.start, tzinfo=ZoneInfo(prefs.timezone))
        if d.weekday() in prefs.workdays and start > local:
            return start.astimezone(now.tzinfo)
    return now + timedelta(days=1)


def local_day(now: datetime, prefs: Prefs) -> str:
    return _local(now, prefs).date().isoformat()


def deliver_at(now: datetime, prefs: Prefs, *, kind: Kind, urgency: Urgency = "normal", asked_today: int = 0) -> datetime:
    """When a message may reach the person. `asked_today` counts questions already delivered today."""
    in_hours = working(now, prefs)
    if urgency == "urgent":
        return now if in_hours or prefs.urgent_out_of_hours else next_start(now, prefs)
    if kind == "question" and asked_today >= prefs.questions_per_day:
        return next_start(now, prefs, after_today=True)  # today's budget is spent
    if urgency == "low":
        return now if in_hours and kind == "summary" else next_start(now, prefs, after_today=in_hours)
    return now if in_hours else next_start(now, prefs)
