"""Ingest a batch: redact, create cases, match the mentor's actions, record a run report.

Nothing raw is stored. Text is redacted, ids and addresses are hashed, and log lines carry ids
and counts only. An action that can't be matched yet (its item hasn't been captured) is kept in
that same redacted, hashed form and retried whenever new cases arrive.
"""

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capture.keys import hkey, ref_tokens
from app.capture.matcher import ActionKeys, CaseKeys, classify, match_action
from app.capture.redact import Redactor
from app.capture.types import Action, Batch, Item
from app.logs import get_logger
from app.models import CaptureRun, Case, Connection, HumanAction, TaskType, UnmatchedAction, utcnow
from app.task_types import TaskTypeConfig

log = get_logger("capture")

STAT_KEYS = (
    "items_received", "cases_created", "duplicate_items", "actions_received", "duplicate_actions",
    "actions_matched", "actions_unmatched", "actions_without_decision", "earlier_actions_matched",
)


def aware(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; everything stored is UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Prepared:
    """An action after redaction and hashing: safe to store, enough to match and record later."""

    source_ref: str
    acted_at: datetime
    kind: str
    item_ref: str | None
    in_reply_to: str | None
    references: list[str]
    thread: str | None
    refs: list[str]
    recipients: list[str]  # hashed
    decision: str | None
    label: str | None
    status: str | None
    payload: dict[str, Any] = field(default_factory=dict)  # redacted subject, fields, text outputs…
    text: str = ""  # redacted body

    def keys(self) -> ActionKeys:
        return ActionKeys(
            acted_at=self.acted_at, item_ref=self.item_ref, in_reply_to=self.in_reply_to,
            references=self.references, thread=self.thread, refs=set(self.refs),
        )

    def dump(self) -> dict[str, Any]:
        return {**asdict(self), "acted_at": self.acted_at.isoformat()}

    @classmethod
    def load(cls, data: dict[str, Any]) -> "Prepared":
        return cls(**{**data, "acted_at": aware(datetime.fromisoformat(data["acted_at"]))})


def prepare(action: Action, r: Redactor) -> Prepared:
    subject, text = r(action.subject), r(action.text)
    payload: dict[str, Any] = {
        "fields": {k: r(v) if isinstance(v, str) else v for k, v in action.fields.items()},
        "text_outputs": {k: r(v) for k, v in action.text_outputs.items()},
    }
    if subject:
        payload["subject"] = subject
    if action.recipients:
        payload["recipients"] = [r.address(a) for a in action.recipients]
    return Prepared(
        source_ref=action.source_ref[:500],
        acted_at=action.acted_at,
        kind=action.kind,
        item_ref=action.item_ref,
        in_reply_to=hkey("msg", action.in_reply_to),
        references=[k for k in (hkey("msg", ref) for ref in action.references) if k],
        thread=hkey("thread", action.thread_ref),
        refs=sorted(ref_tokens(subject, text)),
        recipients=[k for k in (hkey("addr", a) for a in action.recipients) if k],
        decision=action.decision,
        label=action.label,
        status=action.status,
        payload=payload,
        text=text,
    )


def _snapshot(item: Item, r: Redactor) -> dict[str, Any]:
    return {
        "subject": r(item.subject),
        "from": r.address(item.sender),
        "inputs": {name: r(text) for name, text in item.inputs.items()},
        "attachments": [r(a) for a in item.attachments],
        # Only messages from before the item arrived: no time travel.
        "history": [
            {"at": h.at.isoformat(), "from": r.address(h.sender), "text": r(h.text)}
            for h in item.history
            if h.at <= item.received_at
        ],
    }


def _case_keys(case: Case) -> CaseKeys:
    k = case.match_keys or {}
    return CaseKeys(
        case_id=case.id,
        source_ref=case.source_ref,
        received_at=aware(case.received_at),
        message_ids=set(k.get("message_ids", [])),
        thread=k.get("thread"),
        refs=set(k.get("refs", [])),
        decided=case.status == "decided",
    )


class _Matcher:
    def __init__(self, session: Session, connection: Connection, config: TaskTypeConfig, stats: Counter[str]) -> None:
        self.session, self.connection, self.config, self.stats = session, connection, config, stats
        self.cases = {c.id: c for c in session.scalars(select(Case).where(Case.connection_id == connection.id))}
        self.keys = {cid: _case_keys(c) for cid, c in self.cases.items()}

    def try_record(self, p: Prepared) -> tuple[bool, str | None]:
        result = match_action(p.keys(), list(self.keys.values()))
        if result.case_id is None:
            return False, result.reason
        case = self.cases[result.case_id]
        sender = (case.match_keys or {}).get("sender")
        if p.kind == "decision":
            action_type, decision = "decision", p.decision
        else:
            action_type, decision = classify(
                p.kind, to_sender=bool(sender) and sender in p.recipients, label=p.label, status=p.status,
                rules=self.config.capture.decision_rules,
            )
        payload = {"decision": decision, **p.payload, "text_outputs": dict(p.payload.get("text_outputs", {}))}
        if p.text and action_type == "reply" and self.config.capture.reply_text_output:
            payload["text_outputs"].setdefault(self.config.capture.reply_text_output, p.text)
        elif p.text:
            payload["note"] = p.text  # e.g. the mentor's covering note on a forward
        if p.label:
            payload["label"] = p.label
        if p.status:
            payload["status"] = p.status
        self.session.add(
            HumanAction(
                case_id=case.id, action_type=action_type, payload=payload, acted_at=p.acted_at,
                source=self.connection.provider, source_ref=p.source_ref, match_method=result.method,
            )
        )
        self.stats["actions_matched"] += 1
        self.stats[f"matched_{result.method}"] += 1
        if decision and case.status != "decided":
            case.status = "decided"
            self.keys[case.id].decided = True
        elif not decision:
            self.stats["actions_without_decision"] += 1
        return True, None


def ingest(session: Session, connection: Connection, batch: Batch, *, live_after: datetime | None = None) -> CaptureRun:
    """Items received before `live_after` (or all items, when it's None) are backtest cases."""
    task_type = session.get(TaskType, connection.task_type_id)
    if task_type is None:
        raise ValueError("connection has no task type")
    config = TaskTypeConfig.model_validate(task_type.config)
    run = CaptureRun(connection_id=connection.id)
    session.add(run)
    session.flush()
    stats: Counter[str] = Counter({k: 0 for k in STAT_KEYS})
    r = Redactor()

    known_refs = set(session.scalars(select(Case.source_ref).where(Case.connection_id == connection.id)))
    for item in sorted(batch.items, key=lambda i: i.received_at):
        stats["items_received"] += 1
        if item.source_ref[:500] in known_refs:
            stats["duplicate_items"] += 1
            continue
        snapshot = _snapshot(item, r)
        session.add(
            Case(
                task_type_id=task_type.id,
                connection_id=connection.id,
                source_ref=item.source_ref[:500],
                received_at=item.received_at,
                snapshot=snapshot,
                match_keys={
                    "message_ids": [k for k in (hkey("msg", m) for m in item.message_ids) if k],
                    "thread": hkey("thread", item.thread_ref),
                    "sender": hkey("addr", item.sender),
                    "refs": sorted(ref_tokens(snapshot["subject"], *snapshot["inputs"].values())),
                },
                is_backtest=live_after is None or item.received_at < live_after,
                status="open",
            )
        )
        known_refs.add(item.source_ref[:500])
        stats["cases_created"] += 1
    session.flush()

    matcher = _Matcher(session, connection, config, stats)

    # New cases may be what earlier unmatched actions were waiting for.
    if stats["cases_created"]:
        waiting = session.scalars(
            select(UnmatchedAction).where(UnmatchedAction.connection_id == connection.id).order_by(UnmatchedAction.acted_at)
        ).all()
        for row in waiting:
            if "prepared" not in row.summary:
                continue
            matched, _ = matcher.try_record(Prepared.load(row.summary["prepared"]))
            if matched:
                stats["earlier_actions_matched"] += 1
                session.delete(row)

    seen = set(session.scalars(select(HumanAction.source_ref).join(Case).where(Case.connection_id == connection.id)))
    seen |= set(session.scalars(select(UnmatchedAction.source_ref).where(UnmatchedAction.connection_id == connection.id)))
    for action in sorted(batch.actions, key=lambda a: a.acted_at):
        stats["actions_received"] += 1
        if action.source_ref[:500] in seen:
            stats["duplicate_actions"] += 1
            continue
        seen.add(action.source_ref[:500])
        prepared = prepare(action, r)
        matched, reason = matcher.try_record(prepared)
        if not matched:
            session.add(
                UnmatchedAction(
                    connection_id=connection.id,
                    run_id=run.id,
                    source_ref=prepared.source_ref,
                    acted_at=prepared.acted_at,
                    reason=reason or "unmatched",
                    summary={"kind": prepared.kind, "subject": prepared.payload.get("subject", "")[:200],
                             "refs": prepared.refs[:10], "prepared": prepared.dump()},
                )
            )
            stats["actions_unmatched"] += 1

    run.finished_at = utcnow()
    matched_now = stats["actions_matched"] - stats["earlier_actions_matched"]
    considered = matched_now + stats["actions_unmatched"]
    run.stats = {
        **stats,
        "match_rate": round(matched_now / considered, 4) if considered else None,
        "errors": batch.errors[:100],
        "error_count": len(batch.errors),
        "redactions": dict(r.counts),
    }
    session.commit()
    log.info(
        "capture run %s on connection %s: %d new cases, %d of %d actions matched, %d earlier actions matched, %d errors",
        run.id, connection.id, stats["cases_created"], matched_now, considered, stats["earlier_actions_matched"],
        len(batch.errors),
    )
    return run
