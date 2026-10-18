"""Running Newt's actions in the firm's systems, confirming them, and staying on the work.

queue()     an action Newt is allowed to take (autonomous, or approved by the mentor) becomes a job
run()       the job: re-check the policy, hand the action to the executor, retry, or give up and hand back
callback()  a system confirms (signed) that it finished, or that it couldn't
complete    a case is completed only when every action on it is confirmed done
follow_up() if nothing has happened a few days after Newt finished, it chases, or asks whether to
"""

import hashlib
import hmac
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.actions import policy
from app.agents.context import utc
from app.config import get_settings
from app.execution import destinations, routines
from app.execution.executor import ExecResult, Executor, SimulatedExecutor, WebhookExecutor
from app.logs import get_logger
from app.models import (ActionLog, Apprenticeship, Case, HumanAction, Job, Message, Prediction, TaskType, User, utcnow)
from app.task_types import TaskTypeConfig

log = get_logger("execution")
MAX_ATTEMPTS = 3
BACKOFF_S = 30
# A process replay's director stands in for the firm's system (app/sim/director.py); never set in live work.
executor_override: ContextVar[Executor | None] = ContextVar("executor_override", default=None)


class ExecutionError(ValueError):
    pass


def queue(session: Session, rows: list[ActionLog]) -> None:
    """Hand allowed actions to the worker. Called once an action may run: autonomous, or approved."""
    for row in rows:
        if row.status == "blocked" or row.exec_status in ("queued", "running", "done"):
            continue
        row.exec_status = "queued"
        session.flush()
        session.add(Job(type="execute_action", payload={"action_id": row.id}))


def _payload(row: ActionLog, case: Case, decision: str | None) -> dict[str, Any]:
    return {"action_id": row.id, "action": row.action, "params": row.payload, "item_ref": case.source_ref, "case_id": case.id,
            "decision": decision, "callback_url": f"{get_settings().api_url}/execution/callback/{row.id}"}


def run(session: Session, action_id: str) -> str | None:
    row = session.get(ActionLog, action_id)
    if row is None or row.exec_status != "queued":
        return None
    case = session.get(Case, row.case_id)
    tt = session.get(TaskType, case.task_type_id)
    task = TaskTypeConfig.model_validate(tt.config)
    verdict = policy.check(policy.ProposedAction(row.action, row.payload), task, case.snapshot or {})
    if not verdict["ok"]:  # the policy is checked again at the moment of acting
        _fail(session, row, "the action policy stopped it: " + "; ".join(verdict["reasons"]))
        return "failed"
    dest = destinations.for_action(session, tt, row.action)
    row.exec_status, row.attempts, row.destination_id = "running", row.attempts + 1, dest.id if dest else None
    session.commit()
    decision = ((session.get(Prediction, row.prediction_id).output or {}).get("decision")) if row.prediction_id else None
    executor = executor_override.get() or (WebhookExecutor(dest.url, destinations.secret_of(dest)) if dest else SimulatedExecutor())
    result = executor.execute(_payload(row, case, decision))
    return _apply(session, row, result)


def _apply(session: Session, row: ActionLog, result: ExecResult) -> str:
    if result.status == "done":
        _done(session, row, result.ref, simulated=result.simulated)
        return "done"
    if result.status == "accepted":
        row.result = {**row.result, "accepted_at": utcnow().isoformat()}
        session.commit()
        return "running"
    if row.attempts < MAX_ATTEMPTS:
        row.exec_status = "queued"
        row.result = {**row.result, "last_error": result.detail}
        session.add(Job(type="execute_action", payload={"action_id": row.id}, run_at=utcnow() + timedelta(seconds=BACKOFF_S * 2 ** (row.attempts - 1))))
        session.commit()
        return "retrying"
    _fail(session, row, result.detail or "the system couldn't do it")
    return "failed"


def _done(session: Session, row: ActionLog, ref: str | None, *, simulated: bool) -> None:
    now = utcnow()
    row.exec_status, row.completed_at, row.external_ref = "done", now, ref
    row.executed_at = row.executed_at or now
    row.result = {**row.result, "simulated": simulated}
    session.flush()
    case = session.get(Case, row.case_id)
    pending = session.scalar(select(ActionLog.id).where(ActionLog.case_id == case.id, ActionLog.exec_status.in_(("queued", "running", "failed"))).limit(1))
    if pending is None and case.completed_at is None:
        case.completed_at = now
        _on_complete(session, case, row)
    session.commit()


def _on_complete(session: Session, case: Case, row: ActionLog) -> None:
    """Mark the conversation's draft as done, and schedule a follow-up if this kind of work needs one."""
    tt = session.get(TaskType, case.task_type_id)
    done = [r for r in session.scalars(select(ActionLog).where(ActionLog.case_id == case.id, ActionLog.exec_status == "done"))]
    what = [destinations.describe(policy.ProposedAction(r.action, r.payload)) for r in done if not r.payload.get("follow_up")]
    simulated = any(r.result.get("simulated") for r in done)
    for m in session.scalars(select(Message).where(Message.kind.in_(("draft", "handback")), Message.task_type_id == tt.id)):
        if m.payload.get("prediction_id") == row.prediction_id:
            m.payload = {**m.payload, "completed": {"at": utc(case.completed_at).isoformat(), "what": what, "simulated": simulated}}
    decision = ((session.get(Prediction, row.prediction_id).output or {}).get("decision")) if row.prediction_id else None
    days = routines.follow_up_days(session, tt, decision)
    if days and not row.payload.get("follow_up"):
        session.add(Job(type="follow_up", payload={"case_id": case.id, "since": utc(case.completed_at).isoformat()},
                        run_at=utc(case.completed_at) + timedelta(days=days)))


def _mentor(session: Session, tt: TaskType) -> User:
    return session.get(User, session.get(Apprenticeship, tt.apprenticeship_id).mentor_id)


def _tell(session: Session, user: User, tt: TaskType, kind: str, body: str, payload: dict[str, Any], key: str) -> None:
    if session.scalar(select(Message.id).where(Message.user_id == user.id, Message.dedupe_key == key).limit(1)):
        return
    from app.colleague import etiquette

    when = etiquette.deliver_at(utcnow(), etiquette.prefs_from(user.preferences), kind="work")
    m = Message(task_type_id=tt.id, user_id=user.id, direction="newt", kind=kind, body=body, payload=payload,
                dedupe_key=key, deliver_after=when)
    session.add(m)
    from app import channels

    channels.queue_delivery(session, m, user)


def _fail(session: Session, row: ActionLog, reason: str) -> None:
    """Couldn't finish: the case comes back to the mentor with the reason, like an honest new hire would."""
    row.exec_status = "failed"
    row.result = {**row.result, "error": reason[:300], "failed_at": utcnow().isoformat()}
    case = session.get(Case, row.case_id)
    tt = session.get(TaskType, case.task_type_id)
    task = TaskTypeConfig.model_validate(tt.config)
    case.status = "open"  # back in the person's hands
    if row.prediction_id:
        p = session.get(Prediction, row.prediction_id)
        hb = (p.output or {}).get("hand_back") or {}
        p.output = {**(p.output or {}), "hand_back": {**hb, "hand_back": True, "reasons": [*hb.get("reasons", []), f"couldn't finish: {reason}"]}}
    subject = (case.snapshot or {}).get("subject") or "a case"
    told = session.scalar(select(Message.id).where(Message.task_type_id == tt.id, Message.kind == "handback", Message.status == "open",
                                                   Message.dedupe_key.like(f"failed:{case.id}:%")).limit(1))
    if told is None:  # one message per case, however many of its actions failed
        n = session.scalar(select(func.count()).select_from(Message).where(Message.dedupe_key.like(f"failed:{case.id}:%"))) or 0
        _tell(session, _mentor(session, tt), tt, "handback",
              f"I couldn't finish {subject}: {reason}. Can you take it, or shall I try again?",
              {"prediction_id": row.prediction_id, "case": {"id": case.id, "subject": subject, "inputs": (case.snapshot or {}).get("inputs", {})},
               "reasons": [f"couldn't finish: {reason}"], "options": task.decision, "retry": case.id},
              key=f"failed:{case.id}:{n}")
    session.commit()
    log.warning("action %s on case %s failed: %s", row.id, case.id, reason[:120])


def retry(session: Session, case_id: str) -> None:
    """Try a case's failed actions again (the mentor said so)."""
    rows = list(session.scalars(select(ActionLog).where(ActionLog.case_id == case_id, ActionLog.exec_status == "failed")))
    if not rows:
        raise ExecutionError("nothing to retry")
    for row in rows:
        row.attempts, row.exec_status = 0, None
    case = session.get(Case, case_id)
    case.status = "decided"
    queue(session, rows)
    session.commit()


def callback(session: Session, action_id: str, raw: bytes, signature: str | None, body: dict[str, Any]) -> str:
    """A system confirms an action (signed with the destination's secret)."""
    row = session.get(ActionLog, action_id)
    if row is None or row.destination_id is None:
        raise LookupError("action not found")
    dest = session.get(destinations.Destination, row.destination_id)
    expected = "sha256=" + hmac.new(destinations.secret_of(dest).encode(), raw, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise PermissionError("bad signature")
    if row.exec_status not in ("running", "queued"):
        return row.exec_status or "unknown"
    if body.get("status") == "failed":
        _fail(session, row, str(body.get("detail") or "the system said it couldn't do it")[:300])
        return "failed"
    _done(session, row, str(body.get("ref") or "")[:200] or None, simulated=False)
    return "done"


# Persistence: staying on the work --------------------------------------------------------------

def _responsible_for_follow_ups(session: Session, tt: TaskType) -> bool:
    resp = (session.get(Apprenticeship, tt.apprenticeship_id).settings or {}).get("responsibilities", {}).get(tt.id, {})
    return bool(resp.get("follow_ups"))


def moved_on(session: Session, case: Case, since: datetime) -> bool:
    """Has anything happened on this work since `since`, up to now? Someone acted on it, or a new message arrived in
    its thread (the supplier replied). Only up to now: a replay never sees what hadn't happened yet."""
    now = utcnow()
    if any(since < utc(a.acted_at) <= now for a in session.scalars(select(HumanAction).where(HumanAction.case_id == case.id))):
        return True
    thread = (case.match_keys or {}).get("thread")
    if not thread:
        return False
    return any((c.match_keys or {}).get("thread") == thread and since < utc(c.received_at) <= now
               for c in session.scalars(select(Case).where(Case.task_type_id == case.task_type_id, Case.id != case.id,
                                                           Case.received_at > since)))


def follow_up(session: Session, case_id: str, since: str) -> str:
    """Days after Newt finished: if nothing has happened, a senior Newt chases on its own; otherwise it asks."""
    case = session.get(Case, case_id)
    if case is None:
        return "gone"
    if moved_on(session, case, datetime.fromisoformat(since)):
        return "moved on"
    tt = session.get(TaskType, case.task_type_id)
    subject = (case.snapshot or {}).get("subject") or "a case"
    if _responsible_for_follow_ups(session, tt):
        chase(session, case)
        _tell(session, _mentor(session, tt), tt, "ack", f"No reply on {subject}, so I've chased it. I'll keep an eye on it.",
              {"case": {"id": case.id, "subject": subject}}, key=f"chased:{case.id}:{since}")
        session.commit()
        return "chased"
    _tell(session, _mentor(session, tt), tt, "followup", f"No reply on {subject} since I finished it. Shall I chase?",
          {"case": {"id": case.id, "subject": subject}, "since": since}, key=f"followup:{case.id}:{since}")
    session.commit()
    return "asked"


def chase(session: Session, case: Case) -> ActionLog | None:
    """A polite follow-up on the same item, through the same policy and executor as everything else."""
    tt = session.get(TaskType, case.task_type_id)
    task = TaskTypeConfig.model_validate(tt.config)
    kind = "send_reply" if tt.status == "autonomous" and "send_reply" in task.allowed_actions else (
        "draft_reply" if "draft_reply" in task.allowed_actions else None)
    output = task.capture.reply_text_output or (task.text_outputs[0] if task.text_outputs else None)
    if kind is None or output is None:
        return None
    subject = (case.snapshot or {}).get("subject") or "this"
    action = policy.ProposedAction(kind, {"to": [(case.snapshot or {}).get("from")], "output": output, "follow_up": True,
                                          "body": f"Hello, just following up on our earlier message about {subject}. "
                                                  "Could you let us know where this stands? Thank you."})
    verdict = policy.check(action, task, case.snapshot or {})
    row = ActionLog(case_id=case.id, prediction_id=None, mode=tt.status, action=action.type, payload=action.params,
                    policy_check=verdict, status="executed" if verdict["ok"] else "blocked", executed_at=None)
    session.add(row)
    session.flush()
    if verdict["ok"]:
        queue(session, [row])
    return row
