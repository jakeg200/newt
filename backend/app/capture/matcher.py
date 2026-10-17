"""The action matcher: which case was the mentor acting on?

Evidence is tried strongest first, and an action is left unmatched rather than guessed:

1. explicit   - the source names the item (CSV and REST rows)
2. reply_header - In-Reply-To / References point at the item's message
3. thread     - same thread; the latest item before the action that isn't decided yet
4. reference  - shares a reference number (invoice, PO, ticket) with exactly one recent item

An action can never match an item that arrived after it.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

REFERENCE_WINDOW = timedelta(days=60)


@dataclass
class CaseKeys:
    case_id: str
    source_ref: str
    received_at: datetime
    message_ids: set[str] = field(default_factory=set)  # hashed
    thread: str | None = None  # hashed
    refs: set[str] = field(default_factory=set)
    decided: bool = False


@dataclass
class ActionKeys:
    acted_at: datetime
    item_ref: str | None = None
    in_reply_to: str | None = None  # hashed
    references: list[str] = field(default_factory=list)  # hashed, oldest first
    thread: str | None = None  # hashed
    refs: set[str] = field(default_factory=set)


@dataclass
class Match:
    case_id: str | None
    method: str | None = None
    reason: str | None = None


def _latest(cases: list[CaseKeys]) -> CaseKeys:
    return max(cases, key=lambda c: c.received_at)


def match_action(action: ActionKeys, cases: list[CaseKeys]) -> Match:
    eligible = [c for c in cases if c.received_at <= action.acted_at]

    if action.item_ref:
        hit = next((c for c in cases if c.source_ref == action.item_ref), None)
        if hit is None:
            return Match(None, reason="the item it refers to hasn't been captured")
        if hit.received_at > action.acted_at:
            return Match(None, reason="the action is dated before its item arrived")
        return Match(hit.case_id, "explicit")

    if action.in_reply_to:
        hits = [c for c in eligible if action.in_reply_to in c.message_ids]
        if hits:
            return Match(_latest(hits).case_id, "reply_header")
    for ref in reversed(action.references):  # nearest ancestor first
        hits = [c for c in eligible if ref in c.message_ids]
        if hits:
            return Match(_latest(hits).case_id, "reply_header")

    if action.thread:
        in_thread = [c for c in eligible if c.thread == action.thread]
        open_ = [c for c in in_thread if not c.decided]
        if open_ or in_thread:
            return Match(_latest(open_ or in_thread).case_id, "thread")

    if action.refs:
        recent = [c for c in eligible if action.acted_at - c.received_at <= REFERENCE_WINDOW]
        scored = sorted(((len(action.refs & c.refs), c) for c in recent if action.refs & c.refs), key=lambda t: -t[0])
        if scored:
            best = scored[0][0]
            top = [c for score, c in scored if score == best]
            if len(top) == 1:
                return Match(top[0].case_id, "reference")
            open_top = [c for c in top if not c.decided]
            if len(open_top) == 1:
                return Match(open_top[0].case_id, "reference")
            return Match(None, reason=f"{len(top)} items share its reference numbers")

    return Match(None, reason="no item matches its thread, headers or reference numbers")


def classify(kind: str, *, to_sender: bool, label: str | None, status: str | None, rules: list) -> tuple[str, str | None]:
    """Turn an observed action into (action_type, decision) using the task type's capture rules."""
    action_type = {"message": "reply" if to_sender else "forward"}.get(kind, kind)
    for rule in rules:
        if rule.action != action_type:
            continue
        if rule.action == "label" and (label or "").lower() != (rule.label or "").lower():
            continue
        if rule.action == "status" and (status or "").lower() != (rule.status or "").lower():
            continue
        return action_type, rule.decision
    return action_type, None
