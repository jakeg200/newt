"""Scoring whole processes, not single decisions.

A process replay runs one past case from arrival to the end of its follow-ups, with Newt in the team's place. Here
Newt's timeline is compared with what the team actually did and what the world did back (replies in the thread):

  decision      the same decision as the team
  evidence      the steps the role requires were taken (step checks)
  policy        nothing it tried was blocked
  reply         it replied when the team replied, and didn't when they didn't
  chase         it chased when no reply came within the role's follow-up days, and never after the reply had come

A case Newt handed back isn't a divergence: it's the honest outcome, counted on its own like coverage.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any

CHASE_SLACK = timedelta(days=1)  # a chase this long after the deadline still counts as on time


@dataclass(frozen=True)
class TeamTimeline:
    received_at: datetime
    decision: str | None
    first_action_at: datetime | None  # when the team first acted on it
    replied: bool
    chased: bool  # replied again with no counterparty reply in between
    counterparty: tuple[datetime, ...] = ()  # replies arriving in the thread, in order


@dataclass(frozen=True)
class NewtTimeline:
    decision: str | None
    handed_back: bool
    steps_ok: bool
    policy_ok: bool
    replied: bool
    done_at: datetime | None  # its own part finished (every first action confirmed)
    chases: tuple[datetime, ...] = ()
    reasons: tuple[str, ...] = field(default_factory=tuple)  # hand-back reasons, if any


def chase_verdict(newt: NewtTimeline, counterparty: tuple[datetime, ...], follow_up_days: int | None) -> str | None:
    """None when chasing was right (or didn't apply); otherwise what was wrong with it."""
    if newt.done_at is None or not newt.replied or not follow_up_days:
        return "chased with nothing to chase" if newt.chases else None
    deadline = newt.done_at + timedelta(days=follow_up_days)
    reply = next((c for c in sorted(counterparty) if c > newt.done_at), None)
    if reply is not None and any(ch >= reply for ch in newt.chases):
        return "chased after the reply had come"
    if (reply is None or reply > deadline) and not any(ch <= deadline + CHASE_SLACK for ch in newt.chases):
        return "didn't chase when no reply came"
    return None


def score(team: TeamTimeline, newt: NewtTimeline, follow_up_days: int | None) -> dict[str, Any]:
    """One process: like the team, handed back, or diverged (with the reasons)."""
    if newt.handed_back:
        return {"verdict": "handed_back", "reasons": list(newt.reasons), "hours_sooner": None}
    reasons: list[str] = []
    if newt.decision != team.decision:
        reasons.append(f"decided {newt.decision or 'nothing'}, the team decided {team.decision or 'nothing'}")
    if not newt.steps_ok:
        reasons.append("skipped evidence the role requires")
    if not newt.policy_ok:
        reasons.append("tried something the policy stopped")
    if newt.replied and not team.replied:
        reasons.append("replied when the team didn't")
    elif team.replied and not newt.replied:
        reasons.append("didn't reply when the team did")
    chase = chase_verdict(newt, team.counterparty, follow_up_days)
    if chase:
        reasons.append(chase)
    sooner = None
    if newt.done_at and team.first_action_at:
        sooner = round((team.first_action_at - newt.done_at).total_seconds() / 3600, 1)
    return {"verdict": "diverged" if reasons else "like_team", "reasons": reasons, "hours_sooner": sooner}


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """The aggregate: how many processes Newt ran like the team, what went differently, and how much sooner it acted."""
    n = len(results)
    like = [r for r in results if r["verdict"] == "like_team"]
    handed = sum(1 for r in results if r["verdict"] == "handed_back")
    reasons: dict[str, int] = {}
    for r in results:
        if r["verdict"] == "diverged":
            for reason in r["reasons"]:
                key = reason.split(",")[0] if reason.startswith("decided ") else reason
                key = "a different decision" if key.startswith("decided ") else key
                reasons[key] = reasons.get(key, 0) + 1
    sooner = [r["hours_sooner"] for r in like if r["hours_sooner"] is not None]
    carried = n - handed
    return {"cases": n, "like_team": len(like), "handed_back": handed, "diverged": n - handed - len(like),
            "like_team_rate": round(len(like) / carried, 3) if carried else None,
            "divergences": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
            "median_hours_sooner": round(median(sooner), 1) if sooner else None}
