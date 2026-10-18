"""Newt where people already work: Slack, Teams or email, besides the app.

Each person picks a channel (`User.preferences.channel`). Newt's messages are still written, stored and timed by the
colleague service and its etiquette; a channel only delivers them. When a message is due (its `deliver_after`), a
`deliver_message` job posts it, with the same buttons as the app. A tap or a typed reply comes back through that
channel's inbound endpoint (`app/api/channels.py`), is checked (signature, sender), and goes through the same
`colleague.service.reply` / `post` as the app. The app stays the record: everything shows there too.

What leaves for the channel is the message text Newt wrote (from redacted case data) and its buttons, never case inputs.
"""

from collections.abc import Callable
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.cards import Card, card_for
from app.config import get_settings
from app.logs import get_logger
from app.models import ChatInstall, Job, Message, TaskType, User

log = get_logger("channels")
CHANNELS = ("app", "email", "slack", "teams")
IDENTITY_KEYS = ("slack_user", "teams")  # kept on a person's preferences once linked
# Messages that reach someone on their own; replies to what they just did stay where they did it.
PROACTIVE = ("question", "draft", "handback", "followup", "promotion", "initiative", "improvement", "standup", "weekly")
NEEDS_ACTION = ("question", "draft", "handback", "followup", "promotion", "initiative", "improvement")


class ChannelError(RuntimeError):
    pass


class Channel(Protocol):
    name: str

    def deliver(self, session: Session, user: User, m: Message, card: Card) -> str | None: ...

    def answered(self, session: Session, user: User, m: Message, note: str) -> None: ...

    def say(self, session: Session, user: User, text: str, thread: str | None = None) -> None: ...


_http: httpx.Client | None = None


def set_http(client: httpx.Client | None) -> None:
    """Tests and the demo route Slack and Teams calls through their own client."""
    global _http
    _http = client


def http() -> httpx.Client:
    return _http or httpx.Client(timeout=10.0)


def install_for(session: Session, org_id: str, provider: str) -> ChatInstall | None:
    return session.scalar(select(ChatInstall).where(ChatInstall.org_id == org_id, ChatInstall.provider == provider)
                          .order_by(ChatInstall.created_at.desc()).limit(1))


def available(session: Session, org_id: str) -> dict[str, bool]:
    s = get_settings()
    return {"app": True, "email": bool(s.smtp_host and s.inbound_email_domain),
            "slack": install_for(session, org_id, "slack") is not None,
            "teams": bool(s.teams_app_id) and install_for(session, org_id, "teams") is not None}


def channel_of(user: User) -> str:
    c = (user.preferences or {}).get("channel") or "app"
    return c if c in CHANNELS else "app"


def adapter(session: Session, user: User, name: str) -> Channel | None:
    if name == "slack":
        from app.channels.slack import Slack

        inst = install_for(session, user.org_id, "slack")
        return Slack(inst) if inst else None
    if name == "teams":
        from app.channels.teams import Teams

        inst = install_for(session, user.org_id, "teams")
        return Teams(inst) if inst and get_settings().teams_app_id else None
    if name == "email":
        from app.channels.email import Email

        return Email() if get_settings().smtp_host else None
    return None


def queue_delivery(session: Session, m: Message, user: User) -> None:
    """Called wherever Newt writes a message: if the person reads Newt elsewhere, deliver it there when it's due."""
    if m.direction != "newt" or channel_of(user) == "app":
        return
    if m.kind not in PROACTIVE and not (m.kind == "ack" and m.dedupe_key):
        return
    session.flush()
    session.add(Job(type="deliver_message", payload={"message_id": m.id}, run_at=m.deliver_after))


CATCH_UP = 5  # moving to a channel brings the latest waiting work along, not a flood


def catch_up(session: Session, user: User) -> int:
    """Someone just chose a channel: what's still waiting for them there goes there too (the most recent few)."""
    if channel_of(user) == "app":
        return 0
    waiting = list(session.scalars(select(Message).where(Message.user_id == user.id, Message.direction == "newt",
                                                         Message.status == "open", Message.kind.in_(NEEDS_ACTION),
                                                         Message.external_ref.is_(None))
                                   .order_by(Message.deliver_after.desc()).limit(CATCH_UP)))
    queued = {(p or {}).get("message_id") for p in session.scalars(select(Job.payload).where(Job.type == "deliver_message",
                                                                                           Job.status == "queued"))}
    n = 0
    for m in reversed(waiting):
        if m.id in queued:
            continue
        session.add(Job(type="deliver_message", payload={"message_id": m.id}))
        n += 1
    return n


def deliver(session: Session, message_id: str) -> str:
    """The job: post a due message to its person's channel. Stale work (already dealt with in the app) isn't sent."""
    m = session.get(Message, message_id)
    if m is None:
        return "gone"
    if m.kind in NEEDS_ACTION and m.status != "open":
        return "already dealt with"
    if m.external_ref:
        return "already sent"
    user = session.get(User, m.user_id)
    name = channel_of(user)
    channel = adapter(session, user, name)
    if channel is None:
        return f"{name} isn't connected"
    tt = session.get(TaskType, m.task_type_id)
    from app.colleague.service import intern_name

    m.external_ref = channel.deliver(session, user, m, card_for(m, intern_name(session, tt)))
    m.channel = name
    session.commit()
    log.info("message %s delivered by %s", m.id, name)
    return "sent"


def handle_reply(session: Session, user: User, m: Message, action: str, value: str | None, note: str | None = None,
                 echo: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    """A tap or typed answer from a channel: the same reply as the app, then the channel's message is marked answered
    and Newt's response is said back where the person is."""
    from app.colleague import service

    said = service.reply(session, user, m.id, action, value, note)
    channel = adapter(session, user, m.channel) if m.channel else None
    if channel is not None and m.external_ref:
        try:
            channel.answered(session, user, m, _answered_note(action, value))
        except ChannelError:
            log.warning("couldn't mark message %s answered in %s", m.id, m.channel)
    for s in said:
        if s.get("direction") == "newt" and s.get("id") != m.id and echo:
            echo(s["body"])
    return said


def _answered_note(action: str, value: str | None) -> str:
    if action == "dismiss":
        return "Put aside"
    if action == "answer":
        return "Answered"
    return "Answered: " + (value.replace("_", " ") if value else action.replace("_", " "))


def default_task_type(session: Session, user: User) -> TaskType | None:
    """Which role a free-text message from a channel is about: the one Newt last wrote to them about."""
    last = session.scalar(select(Message).where(Message.user_id == user.id).order_by(Message.created_at.desc()).limit(1))
    if last:
        return session.get(TaskType, last.task_type_id)
    from app.models import Apprenticeship

    app_ = session.scalar(select(Apprenticeship).where(Apprenticeship.mentor_id == user.id).limit(1))
    return session.scalar(select(TaskType).where(TaskType.apprenticeship_id == app_.id).limit(1)) if app_ else None
