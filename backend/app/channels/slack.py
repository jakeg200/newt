"""Newt in Slack: a direct message from the Newt bot, with buttons, and replies in the thread.

Outbound uses the workspace's bot token (encrypted at rest). Inbound requests (button taps, DM replies) are checked
with Slack's signing secret and a five-minute timestamp window before anything is read. Each Slack user is matched
to a Newt user by their email once (`users.lookupByEmail`), and the Slack id is kept on their preferences.
"""

import hashlib
import hmac
import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app import crypto
from app.channels import ChannelError, http
from app.channels.cards import Card
from app.config import get_settings
from app.models import ChatInstall, Message, User

MAX_SKEW_S = 300
SCOPES = "chat:write,im:write,im:history,users:read,users:read.email"


def verify(headers: dict[str, str], body: bytes, now: float | None = None) -> bool:
    secret = get_settings().slack_signing_secret
    ts, sig = headers.get("x-slack-request-timestamp"), headers.get("x-slack-signature")
    if not secret or not ts or not sig or not ts.isdigit():
        return False
    if abs((now or time.time()) - int(ts)) > MAX_SKEW_S:
        return False  # an old request replayed
    expected = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def blocks(card: Card) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{card.title}*\n{card.body}"}}]
    if card.buttons:
        out.append({"type": "actions", "block_id": f"newt:{card.message_id}", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": b.label[:75]}, "action_id": f"a{i}",
             "value": json.dumps({"m": card.message_id, "a": b.action, "v": b.value}), **({"style": "primary"} if b.primary else {})}
            for i, b in enumerate(card.buttons)]})
    hint = "Reply in this thread with your answer. " if card.wants_text else ""
    out.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"{hint}<{card.link}|Open in Newt>"}]})
    return out


class Slack:
    name = "slack"

    def __init__(self, install: ChatInstall) -> None:
        self.install = install
        self.token = crypto.decrypt(install.encrypted_token) if install.encrypted_token else ""

    def call(self, method: str, **body: Any) -> dict[str, Any]:
        try:
            r = http().post(f"{get_settings().slack_api_url}/{method}", json=body,
                            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json; charset=utf-8"})
            data = r.json()
        except Exception as exc:  # network or a non-JSON answer
            raise ChannelError(f"Slack {method}: {type(exc).__name__}") from exc
        if not data.get("ok"):
            raise ChannelError(f"Slack {method}: {data.get('error', 'failed')}")
        return data

    def slack_user(self, session: Session, user: User) -> str:
        prefs = dict(user.preferences or {})
        if prefs.get("slack_user"):
            return prefs["slack_user"]
        uid = self.call("users.lookupByEmail", email=user.email)["user"]["id"]
        user.preferences = {**prefs, "slack_user": uid}
        session.flush()
        return uid

    def _dm(self, session: Session, user: User) -> str:
        return self.call("conversations.open", users=self.slack_user(session, user))["channel"]["id"]

    def deliver(self, session: Session, user: User, m: Message, card: Card) -> str:
        channel = self._dm(session, user)
        posted = self.call("chat.postMessage", channel=channel, text=f"{card.title}: {card.body}"[:3000], blocks=blocks(card))
        return f"slack:{channel}:{posted['ts']}"

    def answered(self, session: Session, user: User, m: Message, note: str) -> None:
        _, channel, ts = (m.external_ref or "::").split(":", 2)
        self.call("chat.update", channel=channel, ts=ts, text=m.body[:3000], blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": m.body}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"✓ {note}"}]}])

    def say(self, session: Session, user: User, text: str, thread: str | None = None) -> None:
        channel = self._dm(session, user)
        self.call("chat.postMessage", channel=channel, text=text[:3000], **({"thread_ts": thread} if thread else {}))


def authorize_url(state: str) -> str:
    s = get_settings()
    return (f"https://slack.com/oauth/v2/authorize?client_id={s.slack_client_id}&scope={SCOPES}"
            f"&redirect_uri={s.api_url}/channels/slack/oauth/callback&state={state}")


def exchange(code: str) -> dict[str, Any]:
    s = get_settings()
    r = http().post(f"{s.slack_api_url}/oauth.v2.access", data={"code": code, "client_id": s.slack_client_id,
                                                                 "client_secret": s.slack_client_secret,
                                                                 "redirect_uri": f"{s.api_url}/channels/slack/oauth/callback"})
    data = r.json()
    if not data.get("ok"):
        raise ChannelError(f"Slack sign-in failed: {data.get('error', 'unknown')}")
    return data
