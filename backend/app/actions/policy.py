"""What an agent may do, checked before anything happens.

Inbound email is untrusted: it can contain instructions ("forward this to all staff"). Agents
never choose actions themselves. We derive actions from their answer (decision, fields, reply),
and every action must pass this policy:

- the action type is whitelisted for the task type (`allowed_actions` in its config);
- a reply goes only to the original sender: no forwarding, no new recipients, no other
  addresses in the body, no links, no attachments;
- fields are named fields of the task type, with a valid value;
- routing only hands the case back to the mentor.

Execution is simulated in the MVP: allowed actions are logged as executed; sending through the
customer's systems comes with the production connectors.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.task_types import TaskTypeConfig

MAX_REPLY = 5000
# Any scheme, "www.", or anything shaped like a domain (any top-level domain: attackers aren't limited
# to .com). Errs towards blocking: a blocked reply is handed back, a leaked link isn't recoverable.
_URL = re.compile(r"(?i)\b(?:https?|ftp)://\S+|\bwww\.\S+|\b(?:[a-z0-9-]+\.)+[a-z]{2,24}\b(?:/\S*)?")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PSEUDO = re.compile(r"\[EMAIL [0-9a-f]{6}\]")


@dataclass
class ProposedAction:
    type: str
    params: dict[str, Any]


def plan(task: TaskTypeConfig, snapshot: dict[str, Any], output: dict[str, Any], mode: str) -> list[ProposedAction]:
    """Actions implied by an answer, of the types the task allows. Nothing the agent writes can add an action
    type; fields a task doesn't set (no `set_field`) stay on the prediction rather than becoming blocked actions."""
    actions = [ProposedAction("set_status", {"value": output.get("decision")})]
    for name, value in (output.get("fields") or {}).items():
        actions.append(ProposedAction("set_field", {"name": name, "value": value}))
    reply_name = task.capture.reply_text_output or (task.text_outputs[0] if task.text_outputs else None)
    body = (output.get("text_outputs") or {}).get(reply_name) if reply_name else None
    if body:
        kind = "send_reply" if mode == "autonomous" and "send_reply" in task.allowed_actions else "draft_reply"
        actions.append(ProposedAction(kind, {"to": [snapshot.get("from")], "body": body, "output": reply_name}))
    return [a for a in actions if a.type in task.allowed_actions]


def check(action: ProposedAction, task: TaskTypeConfig, snapshot: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    p = action.params
    if action.type not in task.allowed_actions:
        reasons.append(f"'{action.type}' isn't an allowed action for this task")
    if action.type in ("draft_reply", "send_reply"):
        sender = snapshot.get("from")
        if not sender or list(p.get("to") or []) != [sender]:
            reasons.append("replies only go to the original sender")
        body = str(p.get("body") or "")
        if _URL.search(body):
            reasons.append("replies can't contain links")
        others = set(_EMAIL.findall(body)) | (set(_PSEUDO.findall(body)) - {sender})
        if others:
            reasons.append("replies can't name other email addresses")
        if p.get("attachments") or p.get("cc") or p.get("bcc"):
            reasons.append("no attachments or extra recipients")
        if len(body) > MAX_REPLY:
            reasons.append("reply is too long")
    elif action.type == "set_field":
        spec = task.fields.get(p.get("name", ""))
        if spec is None:
            reasons.append(f"'{p.get('name')}' isn't a field of this task")
        elif spec.type == "enum" and spec.options and p.get("value") not in spec.options:
            reasons.append(f"'{p.get('value')}' isn't a valid {p.get('name')}")
    elif action.type == "set_status":
        if p.get("value") not in task.decision:
            reasons.append("status must be one of the task's decisions")
    elif action.type == "route":
        if p.get("to") != "mentor":
            reasons.append("cases can only be routed back to the mentor")
    return {"ok": not reasons, "reasons": reasons}
