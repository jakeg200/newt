"""Where Newt reaches people: connecting Slack and Teams, and what comes back from them and from email.

Every inbound request is authenticated before its body is read for anything: Slack's signing secret, the Bot
Framework token for Teams, a shared secret plus a signed reply address for email. Whatever people write is data: it
becomes a reply to one of Newt's messages, or a chat message, through the same code as the app.
"""

import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import channels, crypto
from app.auth import current_user, require_role
from app.capture.sources.email_source import strip_quoted
from app.channels import email as email_channel
from app.channels import slack, teams
from app.channels.cards import card_for, choice_from_text
from app.colleague import service
from app.colleague.service import ConversationError
from app.config import get_settings
from app.db import get_session
from app.logs import get_logger
from app.models import ChatInstall, Message, TaskType, User

router = APIRouter(tags=["channels"])
log = get_logger("channels")
manager = require_role("manager", "admin")
STATE_MAX_AGE_S = 600


@router.get("/channels")
def my_channels(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    avail = channels.available(session, user.org_id)
    s = get_settings()
    return {"available": avail, "mine": channels.channel_of(user),
            "can_install": {"slack": bool(s.slack_client_id), "teams": bool(s.teams_app_id)},
            "linked": {"slack": bool((user.preferences or {}).get("slack_user")), "teams": bool((user.preferences or {}).get("teams"))},
            "teams_code": teams.link_code(user) if avail["teams"] else None}


# Slack: install ---------------------------------------------------------------------------------

def _state(user: User, at: int | None = None) -> str:
    at = at or int(time.time())
    sig = hmac.new(get_settings().secret(), f"slack-install:{user.id}:{at}".encode(), hashlib.sha256).hexdigest()[:24]
    return f"{user.id}.{at}.{sig}"


def _state_user(session: Session, state: str) -> User | None:
    try:
        uid, at, _ = state.split(".")
        if time.time() - int(at) > STATE_MAX_AGE_S:
            return None
    except ValueError:
        return None
    user = session.get(User, uid)
    return user if user and hmac.compare_digest(_state(user, int(at)), state) else None


@router.get("/channels/slack/install")
def slack_install(user: User = Depends(manager)) -> dict[str, str]:
    if not get_settings().slack_client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Slack isn't set up for this Newt yet (see docs/NEEDS_JAKE.md)")
    return {"url": slack.authorize_url(_state(user))}


@router.get("/channels/slack/oauth/callback")
def slack_callback(code: str, state: str, session: Session = Depends(get_session)) -> RedirectResponse:
    user = _state_user(session, state)
    if user is None or user.role not in ("manager", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "that sign-in link has expired; start again from Setup")
    try:
        data = slack.exchange(code)
    except channels.ChannelError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    team = data.get("team") or {}
    inst = channels.install_for(session, user.org_id, "slack") or ChatInstall(org_id=user.org_id, provider="slack", external_id="")
    inst.external_id, inst.encrypted_token, inst.installed_by = team.get("id", ""), crypto.encrypt(data["access_token"]), user.id
    inst.config = {"team_name": team.get("name"), "bot_user": data.get("bot_user_id")}
    session.add(inst)
    session.commit()
    return RedirectResponse(f"{get_settings().web_url}/setup?connected=slack")


# Slack: inbound ---------------------------------------------------------------------------------

def _slack_user(session: Session, team_id: str, slack_id: str) -> tuple[User, ChatInstall] | None:
    inst = session.scalar(select(ChatInstall).where(ChatInstall.provider == "slack", ChatInstall.external_id == team_id))
    if inst is None:
        return None
    for u in session.scalars(select(User).where(User.org_id == inst.org_id)):
        if (u.preferences or {}).get("slack_user") == slack_id:
            return u, inst
    return None


async def _slack_body(request: Request) -> bytes:
    body = await request.body()
    if not slack.verify({k.lower(): v for k, v in request.headers.items()}, body):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad signature")
    return body


@router.post("/channels/slack/interactivity")
async def slack_interactivity(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    body = await _slack_body(request)
    from urllib.parse import parse_qs

    payload = json.loads(parse_qs(body.decode()).get("payload", ["{}"])[0])
    found = _slack_user(session, (payload.get("team") or {}).get("id", ""), (payload.get("user") or {}).get("id", ""))
    if found is None:
        return {"text": "I don't know who you are yet. Ask your manager to connect you in Newt."}
    user, inst = found
    for act in payload.get("actions", []):
        try:
            v = json.loads(act.get("value") or "{}")
        except json.JSONDecodeError:
            continue
        m = session.get(Message, v.get("m"))
        if m is None or m.user_id != user.id:
            continue  # only your own messages
        thread = (m.external_ref or "::").split(":", 2)[2] or None
        sl = slack.Slack(inst)
        try:
            channels.handle_reply(session, user, m, v.get("a", ""), v.get("v"), echo=lambda text: sl.say(session, user, text, thread))
        except (ConversationError, PermissionError, LookupError) as exc:
            sl.say(session, user, str(exc), thread)
    session.commit()
    return {}


@router.post("/channels/slack/events")
async def slack_events(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    body = await _slack_body(request)
    data = json.loads(body or b"{}")
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    if request.headers.get("x-slack-retry-num"):
        return {}  # we answered the first time; a retry would double the message
    event = data.get("event") or {}
    if event.get("type") != "message" or event.get("bot_id") or event.get("subtype") or event.get("channel_type") != "im":
        return {}
    found = _slack_user(session, data.get("team_id", ""), event.get("user", ""))
    if found is None:
        return {}
    user, inst = found
    sl = slack.Slack(inst)
    text, thread = event.get("text") or "", event.get("thread_ts")
    if thread:
        m = session.scalar(select(Message).where(Message.external_ref == f"slack:{event.get('channel')}:{thread}"))
        if m is not None and m.user_id == user.id and m.status == "open" and card_for(m).wants_text:
            channels.handle_reply(session, user, m, "answer", text, echo=lambda t: sl.say(session, user, t, thread))
            session.commit()
            return {}
    tt = channels.default_task_type(session, user)
    if tt is not None:
        said = service.post(session, user, tt, text)
        for s in said[1:]:
            sl.say(session, user, s["body"], thread)
    session.commit()
    return {}


# Teams ------------------------------------------------------------------------------------------

@router.post("/channels/teams/messages")
async def teams_messages(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    if teams.verify(request.headers.get("authorization")) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad token")
    activity = await request.json()
    if activity.get("type") != "message":
        return {}
    tenant = ((activity.get("channelData") or {}).get("tenant") or {}).get("id") or (activity.get("conversation") or {}).get("tenantId", "")
    inst = session.scalar(select(ChatInstall).where(ChatInstall.provider == "teams", ChatInstall.external_id == tenant))
    if inst is None:
        return {}
    sender = (activity.get("from") or {}).get("aadObjectId") or (activity.get("from") or {}).get("id", "")
    ref = {"service_url": activity.get("serviceUrl", ""), "conversation_id": (activity.get("conversation") or {}).get("id", ""), "aad": sender}
    users = list(session.scalars(select(User).where(User.org_id == inst.org_id)))
    text = (activity.get("text") or "").strip()
    if text.lower().startswith("link "):
        code = text.split(None, 1)[1].strip().upper()
        user = next((u for u in users if hmac.compare_digest(teams.link_code(u), code)), None)
        if user is not None:
            user.preferences = {**(user.preferences or {}), "teams": ref}
            session.commit()
            teams.Teams(inst).say(session, user, "Linked. I'll message you here from now on, if you choose Teams in Newt.")
        return {}
    user = next((u for u in users if ((u.preferences or {}).get("teams") or {}).get("aad") == sender), None)
    if user is None:
        return {}
    tm = teams.Teams(inst)
    submitted = (activity.get("value") or {}).get("newt")
    if submitted:
        m = session.get(Message, submitted.get("m"))
        if m is not None and m.user_id == user.id:
            value = submitted.get("v") if submitted.get("a") != "answer" else (activity.get("value") or {}).get("answer")
            try:
                channels.handle_reply(session, user, m, submitted.get("a", ""), value, echo=lambda t: tm.say(session, user, t))
            except (ConversationError, PermissionError, LookupError) as exc:
                tm.say(session, user, str(exc))
    elif text:
        tt = channels.default_task_type(session, user)
        if tt is not None:
            for s in service.post(session, user, tt, text)[1:]:
                tm.say(session, user, s["body"])
    session.commit()
    return {}


# Email ------------------------------------------------------------------------------------------

def _field(data: dict[str, Any], *names: str) -> str:
    for n in names:
        v = data.get(n)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, list) and v:
            return ", ".join(x.get("Email", "") if isinstance(x, dict) else str(x) for x in v)
    return ""


@router.post("/channels/email/inbound")
async def email_inbound(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    secret = get_settings().inbound_email_secret
    given = request.headers.get("x-newt-inbound") or ""
    if not secret or not hmac.compare_digest(secret, given):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad secret")
    data = await request.json()
    mid = email_channel.message_id_from(_field(data, "to", "To", "ToFull", "recipient"))
    m = session.get(Message, mid) if mid else None
    if m is None:
        return {"status": "ignored"}
    user = session.get(User, m.user_id)
    if not email_channel.same_person(_field(data, "from", "From", "sender"), user):
        log.warning("email reply to message %s from someone else, ignored", m.id)
        return {"status": "ignored"}
    text = strip_quoted(_field(data, "text", "TextBody", "plain", "stripped-text")).strip()
    if not text:
        return {"status": "empty"}
    card = card_for(m)
    em = email_channel.Email()
    echo = lambda t: em.say(session, user, t)  # noqa: E731
    try:
        choice = choice_from_text(card, text)
        if m.status == "open" and choice is not None:
            channels.handle_reply(session, user, m, choice.action, choice.value, echo=echo)
        elif m.status == "open" and card.wants_text:
            channels.handle_reply(session, user, m, card.wants_text, text, echo=echo)
        else:
            tt = session.get(TaskType, m.task_type_id)
            for s in service.post(session, user, tt, text)[1:]:
                echo(s["body"])
    except (ConversationError, PermissionError, LookupError) as exc:
        echo(str(exc))
    session.commit()
    return {"status": "done"}
