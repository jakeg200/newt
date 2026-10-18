"""The systems a team connects so Newt can do the work there (a webhook into their own tools, or Zapier/Make/n8n)."""

import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crypto
from app.actions.policy import ProposedAction
from app.agents.external import EndpointError, check_endpoint
from app.config import get_settings
from app.models import Destination, TaskType, User, utcnow
from app.task_types import TaskTypeConfig


class DestinationError(ValueError):
    pass


def out(d: Destination) -> dict[str, Any]:
    return {"id": d.id, "task_type_id": d.task_type_id, "name": d.name, "kind": d.kind, "url": d.url, "actions": d.actions,
            "status": d.status, "last_test": d.last_test, "created_at": d.created_at}


def for_action(session: Session, tt: TaskType, action: str) -> Destination | None:
    """The first active destination that carries out this kind of action, if any."""
    active = session.scalars(select(Destination).where(Destination.task_type_id == tt.id, Destination.status == "active")
                             .order_by(Destination.created_at))
    return next((d for d in active if action in (d.actions or [])), None)


def connected(session: Session, tt: TaskType) -> bool:
    return session.scalar(select(Destination.id).where(Destination.task_type_id == tt.id, Destination.status == "active").limit(1)) is not None


def create(session: Session, user: User, tt: TaskType, name: str, url: str, actions: list[str]) -> tuple[Destination, str]:
    task = TaskTypeConfig.model_validate(tt.config)
    try:
        url = check_endpoint(url, allow_http_localhost=get_settings().env == "dev")
    except EndpointError as exc:
        raise DestinationError(str(exc)) from exc
    unknown = sorted(set(actions) - set(task.allowed_actions))
    if unknown or not actions:
        raise DestinationError(f"actions must be some of this role's allowed actions: {task.allowed_actions}")
    secret = "newt_" + secrets.token_urlsafe(32)
    d = Destination(org_id=user.org_id, task_type_id=tt.id, name=name.strip() or "My system", url=url, actions=actions,
                    encrypted_secret=crypto.encrypt(secret))
    session.add(d)
    session.commit()
    return d, secret  # the secret is shown once


def secret_of(d: Destination) -> str:
    return crypto.decrypt(d.encrypted_secret)


def test(session: Session, d: Destination) -> dict[str, Any]:
    """Send a harmless test action so the team can see the connection work before Newt relies on it."""
    from app.execution.executor import WebhookExecutor

    payload = {"action_id": f"test-{secrets.token_hex(4)}", "test": True, "action": "test", "params": {},
               "item_ref": None, "case_id": None, "decision": None,
               "callback_url": f"{get_settings().api_url}/execution/callback/test"}
    r = WebhookExecutor(d.url, secret_of(d)).execute(payload)
    d.last_test = {"ok": r.status != "error", "detail": r.detail or ("received" if r.status == "accepted" else "done"),
                   "at": utcnow().isoformat()}
    session.commit()
    return d.last_test


def describe(action: ProposedAction) -> str:
    """What an action does, in plain words, for people reading Newt's messages."""
    p = action.params
    return {"set_status": f"set it to {str(p.get('value', '')).replace('_', ' ')}",
            "set_field": f"set {str(p.get('name', '')).replace('_', ' ')}",
            "draft_reply": "drafted the reply", "send_reply": "sent the reply", "route": "routed it to the mentor"}.get(action.type, action.type)
