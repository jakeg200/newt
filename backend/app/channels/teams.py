"""Newt in Microsoft Teams: a bot that messages people with Adaptive Cards.

Teams bots can only message someone after a conversation exists, so each person links once: Setup shows them a short
code, they send "link CODE" to the Newt bot, and their conversation reference (service URL, conversation id) is kept on
their preferences. Inbound activities carry a Bot Framework token, validated against Microsoft's published keys before
anything is read. The org's tenant is linked by an admin (`python -m app.admin connect-teams`).
"""

import hashlib
import hmac
import time
from typing import Any

import jwt
from sqlalchemy.orm import Session

from app.channels import ChannelError, http
from app.channels.cards import Card
from app.config import get_settings
from app.models import ChatInstall, Message, User

ISSUER = "https://api.botframework.com"
_token: dict[str, Any] = {}
_jwks: dict[str, Any] = {}
_verifier = None  # tests replace the token check


def set_verifier(fn) -> None:
    global _verifier
    _verifier = fn


def link_code(user: User) -> str:
    """A short code only this person can have: proves the Teams account sending it is theirs."""
    digest = hmac.new(get_settings().secret(), f"teams-link:{user.id}".encode(), hashlib.sha256).hexdigest()
    return digest[:8].upper()


def verify(authorization: str | None) -> dict[str, Any] | None:
    """The Bot Framework token on an inbound activity, checked; its claims, or None."""
    if _verifier is not None:
        return _verifier(authorization)
    s = get_settings()
    if not authorization or not authorization.startswith("Bearer ") or not s.teams_app_id:
        return None
    token = authorization[7:]
    try:
        if "client" not in _jwks:
            jwks_uri = http().get(s.teams_openid_url).json()["jwks_uri"]
            _jwks["client"] = jwt.PyJWKClient(jwks_uri)
        key = _jwks["client"].get_signing_key_from_jwt(token)
        return jwt.decode(token, key.key, algorithms=["RS256"], audience=s.teams_app_id, issuer=ISSUER)
    except Exception:
        return None


def adaptive_card(card: Card) -> dict[str, Any]:
    body: list[dict[str, Any]] = [{"type": "TextBlock", "text": card.title, "weight": "Bolder", "wrap": True},
                                  {"type": "TextBlock", "text": card.body, "wrap": True}]
    actions: list[dict[str, Any]] = [{"type": "Action.Submit", "title": b.label[:40],
                                      "data": {"newt": {"m": card.message_id, "a": b.action, "v": b.value}},
                                      **({"style": "positive"} if b.primary else {})} for b in card.buttons]
    if card.wants_text:
        body.append({"type": "Input.Text", "id": "answer", "isMultiline": True, "placeholder": "Your answer"})
        actions.insert(0, {"type": "Action.Submit", "title": "Send", "style": "positive",
                           "data": {"newt": {"m": card.message_id, "a": card.wants_text, "v": None}}})
    actions.append({"type": "Action.OpenUrl", "title": "Open in Newt", "url": card.link})
    return {"contentType": "application/vnd.microsoft.card.adaptive",
            "content": {"type": "AdaptiveCard", "version": "1.4", "body": body, "actions": actions}}


class Teams:
    name = "teams"

    def __init__(self, install: ChatInstall) -> None:
        self.install = install

    def _bearer(self) -> str:
        if _token.get("value") and _token.get("until", 0) > time.time() + 60:
            return _token["value"]
        s = get_settings()
        r = http().post(s.teams_token_url, data={"grant_type": "client_credentials", "client_id": s.teams_app_id,
                                                 "client_secret": s.teams_app_password,
                                                 "scope": "https://api.botframework.com/.default"})
        data = r.json()
        if "access_token" not in data:
            raise ChannelError("Teams sign-in failed")
        _token.update(value=data["access_token"], until=time.time() + int(data.get("expires_in", 3600)))
        return _token["value"]

    def _ref(self, user: User) -> dict[str, str]:
        ref = (user.preferences or {}).get("teams")
        if not ref:
            raise ChannelError("this person hasn't linked Teams yet")
        return ref

    def _post(self, ref: dict[str, str], activity: dict[str, Any], activity_id: str | None = None) -> dict[str, Any]:
        url = f"{ref['service_url'].rstrip('/')}/v3/conversations/{ref['conversation_id']}/activities" + (f"/{activity_id}" if activity_id else "")
        r = (http().put if activity_id else http().post)(url, json=activity, headers={"Authorization": f"Bearer {self._bearer()}"})
        if r.status_code >= 300:
            raise ChannelError(f"Teams answered HTTP {r.status_code}")
        return r.json() if r.content else {}

    def deliver(self, session: Session, user: User, m: Message, card: Card) -> str:
        ref = self._ref(user)
        posted = self._post(ref, {"type": "message", "attachments": [adaptive_card(card)]})
        return f"teams:{ref['conversation_id']}:{posted.get('id', '')}"

    def answered(self, session: Session, user: User, m: Message, note: str) -> None:
        ref = self._ref(user)
        activity_id = (m.external_ref or "").rsplit(":", 1)[-1]
        if activity_id:
            self._post(ref, {"type": "message", "text": f"{m.body}\n\n✓ {note}"}, activity_id)

    def say(self, session: Session, user: User, text: str, thread: str | None = None) -> None:
        self._post(self._ref(user), {"type": "message", "text": text})
