"""A past case as a process: what arrived, what the team did and when, and what the world did back.

Everything comes from the recording: the team's captured actions on the case, and later messages in the same thread
(the supplier's reply) at the times they really arrived. Nothing is made up.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import utc
from app.eval.process import TeamTimeline
from app.execution import routines
from app.models import Case, HumanAction, TaskType
from app.task_types import TaskTypeConfig

HORIZON_PAD = timedelta(days=2)
MAX_HORIZON = timedelta(days=60)
POOL = 2000  # recent decided cases to choose scenarios from
WHAT = {"decision": "decided", "reply": "replied", "forward": "forwarded", "status": "set the status", "label": "labelled"}


@dataclass
class Scenario:
    case_id: str
    subject: str
    received_at: datetime
    team: TeamTimeline
    follow_up_days: int | None
    horizon: datetime
    events: list[dict[str, Any]] = field(default_factory=list)  # the team's and the world's, for the timeline


def _thread_replies(session: Session, case: Case) -> list[datetime]:
    thread = (case.match_keys or {}).get("thread")
    if not thread:
        return []
    later = session.scalars(select(Case).where(Case.task_type_id == case.task_type_id, Case.id != case.id,
                                               Case.received_at > case.received_at))
    return sorted(utc(c.received_at) for c in later if (c.match_keys or {}).get("thread") == thread)


def _chased(replies: list[datetime], counterparty: list[datetime]) -> bool:
    """The team wrote again before anything came back: a chase."""
    return any(not any(a < c <= b for c in counterparty) for a, b in zip(replies, replies[1:]))


def build(session: Session, tt: TaskType, case: Case) -> Scenario | None:
    actions = sorted((a for a in session.scalars(select(HumanAction).where(HumanAction.case_id == case.id))
                      if a.source != "audit"), key=lambda a: utc(a.acted_at))
    decision = next(((a.payload or {}).get("decision") for a in actions if (a.payload or {}).get("decision")), None)
    if decision is None:
        return None
    received = utc(case.received_at)
    reply_output = TaskTypeConfig.model_validate(tt.config).capture.reply_text_output
    # A reply is a reply action, or a decision that carried the reply's text (ledgers and queues report it that way).
    replies = [utc(a.acted_at) for a in actions if a.action_type == "reply"
               or (reply_output and ((a.payload or {}).get("text_outputs") or {}).get(reply_output))]
    world = _thread_replies(session, case)
    days = routines.follow_up_days(session, tt, decision)
    last = max([received, *(utc(a.acted_at) for a in actions), *world])
    horizon = min(last + timedelta(days=days or 0) + HORIZON_PAD, received + MAX_HORIZON)
    events = [{"at": received, "who": "world", "what": "arrived"}]
    for a in actions:
        what = WHAT.get(a.action_type, a.action_type)
        if a.action_type == "decision":
            what = f"decided {(a.payload or {}).get('decision', '').replace('_', ' ')}"
        elif a.action_type == "status" and (a.payload or {}).get("status"):
            what = f"set the status to {(a.payload or {})['status']}"
        events.append({"at": utc(a.acted_at), "who": "team", "what": what})
    events += [{"at": c, "who": "world", "what": "a reply came in the thread"} for c in world if c <= horizon]
    team = TeamTimeline(received_at=received, decision=decision, first_action_at=utc(actions[0].acted_at) if actions else None,
                        replied=bool(replies), chased=_chased(replies, world), counterparty=tuple(world))
    return Scenario(case.id, (case.snapshot or {}).get("subject", ""), received, team, days, horizon,
                    sorted(events, key=lambda e: e["at"]))


def scenarios(session: Session, tt: TaskType, limit: int) -> list[Scenario]:
    """Recent decided cases, those with a real process (a reply, a thread) first, then plain decisions."""
    cases = list(session.scalars(select(Case).where(Case.task_type_id == tt.id, Case.status.in_(("decided", "handled")))
                                 .order_by(Case.received_at.desc()).limit(POOL)))
    replied = set(session.scalars(select(HumanAction.case_id).join(Case, Case.id == HumanAction.case_id)
                                  .where(Case.task_type_id == tt.id, HumanAction.action_type == "reply")))
    rich = [c for c in cases if c.id in replied or (c.match_keys or {}).get("thread")]
    plain = [c for c in cases if c not in rich]
    out: list[Scenario] = []
    for c in rich + plain:
        if len(out) >= limit:
            break
        sc = build(session, tt, c)
        if sc is not None:
            out.append(sc)
    return sorted(out, key=lambda s: s.received_at)
