"""Newt in Slack, Teams and email: delivered when etiquette says so, with the app's buttons; taps and replies come back
authenticated and go through the same code as the app."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
import pytest
from sqlalchemy import select

from app import admin, channels
from app.agents import registry
from app.channels import email as email_channel
from app.channels import teams
from app.channels.cards import card_for, choice_from_text, plain_text
from app.colleague import service
from app.config import get_settings
from app.models import Job, Message, TaskType, User

from tests.graduation_fixtures import setup_team

ALWAYS_ON = {"start": "00:00", "end": "23:59", "workdays": list(range(7))}


class FakeChat:
    """Slack's Web API and a Teams service URL, recording what Newt sent."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = json.loads(request.content) if request.content and request.headers.get("content-type", "").startswith("application/json") else {}
        self.calls.append((url, body))
        if url.endswith("/users.lookupByEmail"):
            return httpx.Response(200, json={"ok": True, "user": {"id": "U-SARAH"}})
        if url.endswith("/conversations.open"):
            return httpx.Response(200, json={"ok": True, "channel": {"id": "D-SARAH"}})
        if url.endswith("/chat.postMessage"):
            return httpx.Response(200, json={"ok": True, "ts": f"17000000{len(self.calls)}.0001"})
        if url.endswith("/chat.update"):
            return httpx.Response(200, json={"ok": True})
        if "login.test" in url:
            return httpx.Response(200, json={"access_token": "bot-token", "expires_in": 3600})
        if "teams.test" in url:
            return httpx.Response(201, json={"id": f"act-{len(self.calls)}"})
        return httpx.Response(404, json={"ok": False, "error": "unknown"})

    def sent(self, method: str) -> list[dict]:
        return [b for u, b in self.calls if u.endswith(method)]


@pytest.fixture
def chat(client, session, monkeypatch):
    s = get_settings()
    for k, v in {"slack_signing_secret": "slack-signing", "slack_api_url": "https://slack.test/api", "teams_app_id": "newt-bot",
                 "teams_app_password": "pw", "teams_token_url": "https://login.test/token", "smtp_host": "smtp.test",
                 "inbound_email_domain": "in.newt.test", "inbound_email_secret": "inbound-secret"}.items():
        monkeypatch.setattr(s, k, v)
    ctx = setup_team(client, session, history=60)
    registry.set_runner_override(None)
    fake = FakeChat()
    channels.set_http(httpx.Client(transport=httpx.MockTransport(fake)))
    mails = []
    email_channel.set_mailer(mails.append)
    teams.set_verifier(lambda auth: {"aud": "newt-bot"} if auth == "Bearer good" else None)
    client.patch("/me/preferences", json=ALWAYS_ON, headers=ctx["mentor"])
    mentor = session.get(User, ctx["mentor"]["X-Dev-User"])
    yield {**ctx, "fake": fake, "mails": mails, "user": mentor, "session": session}
    channels.set_http(None)
    email_channel.set_mailer(None)
    teams.set_verifier(None)


def ask(ctx, kind="question", payload=None, body="Invoice INV-1: approve or query?") -> Message:
    tt = ctx["session"].get(TaskType, ctx["tt"])
    m = service._say(ctx["session"], ctx["user"], tt, kind, body,
                     payload if payload is not None else {"type": "case", "options": ["approve", "query_supplier"]})
    ctx["session"].commit()
    return m


def deliver_all(session) -> None:
    for job in list(session.scalars(select(Job).where(Job.type == "deliver_message", Job.status == "queued"))):
        job.status = "done"
        session.commit()
        channels.deliver(session, job.payload["message_id"])


def slack_post(client, path: str, body: bytes, *, ts: int | None = None, secret: str = "slack-signing", **headers):
    ts = ts or int(time.time())
    sig = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return client.post(path, content=body, headers={"X-Slack-Request-Timestamp": str(ts), "X-Slack-Signature": sig, **headers})


# Cards ------------------------------------------------------------------------------------------------

def test_cards_carry_the_apps_actions_and_never_case_content(chat):
    m = ask(chat)
    card = card_for(m)
    assert [(b.action, b.value) for b in card.buttons] == [("decide", "approve"), ("decide", "query_supplier"), ("dismiss", None)]
    assert "Reply with the number" in plain_text(card) and f"message={m.id}" in card.link
    assert choice_from_text(card, "2\n\nOn Tue, Sarah wrote:") == card.buttons[1]
    assert choice_from_text(card, "Approve") == card.buttons[0] and choice_from_text(card, "hmm, not sure") is None
    why = ask(chat, payload={"type": "why", "lesson_id": "x"}, body="Why did you query it?")
    assert card_for(why).wants_text == "answer"


# Slack ------------------------------------------------------------------------------------------------

def test_slack_needs_connecting_then_delivers_when_due_with_buttons(chat, client, session):
    assert client.patch("/me/preferences", json={"channel": "slack"}, headers=chat["mentor"]).status_code == 400
    admin.connect_chat(session, _org_name(session, chat["user"]), "slack", "T-ACME", "xoxb-test")
    r = client.patch("/me/preferences", json={"channel": "slack"}, headers=chat["mentor"])
    assert r.status_code == 200 and r.json()["channel"] == "slack"
    m = ask(chat)
    job = session.scalar(select(Job).where(Job.type == "deliver_message"))
    assert job.payload["message_id"] == m.id and job.run_at is not None  # waits for the message's own time
    deliver_all(session)
    session.refresh(m)
    assert m.channel == "slack" and m.external_ref.startswith("slack:D-SARAH:")
    [posted] = chat["fake"].sent("/chat.postMessage")
    values = [json.loads(e["value"]) for b in posted["blocks"] if b["type"] == "actions" for e in b["elements"]]
    assert values[0] == {"m": m.id, "a": "decide", "v": "approve"}
    assert "INV-1" in posted["text"] and "invoice_text" not in json.dumps(posted)
    session.refresh(chat["user"])
    assert chat["user"].preferences["slack_user"] == "U-SARAH"
    # Changing other preferences keeps who they are in Slack.
    client.patch("/me/preferences", json={"questions_per_day": 3}, headers=chat["mentor"])
    session.refresh(chat["user"])
    assert chat["user"].preferences["slack_user"] == "U-SARAH"


def _org_name(session, user: User) -> str:
    from app.models import Org

    return session.get(Org, user.org_id).name


def connect_slack(chat, client, session) -> None:
    admin.connect_chat(session, _org_name(session, chat["user"]), "slack", "T-ACME", "xoxb-test")
    client.patch("/me/preferences", json={"channel": "slack"}, headers=chat["mentor"])


def test_a_tap_in_slack_is_the_same_as_a_tap_in_the_app(chat, client, session):
    connect_slack(chat, client, session)
    m = ask(chat)
    deliver_all(session)
    session.refresh(m)
    tap = {"type": "block_actions", "team": {"id": "T-ACME"}, "user": {"id": "U-SARAH"},
           "actions": [{"value": json.dumps({"m": m.id, "a": "dismiss", "v": None})}]}
    body = urlencode({"payload": json.dumps(tap)}).encode()
    assert slack_post(client, "/channels/slack/interactivity", body, secret="forged").status_code == 401
    assert slack_post(client, "/channels/slack/interactivity", body, ts=int(time.time()) - 3600).status_code == 401  # replayed
    r = slack_post(client, "/channels/slack/interactivity", body, **{"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    session.refresh(m)
    assert m.status == "dismissed"
    assert chat["fake"].sent("/chat.update")[-1]["blocks"][-1]["elements"][0]["text"] == "✓ Put aside"
    # Someone else's Slack account can't answer Sarah's message.
    other = {**tap, "user": {"id": "U-STRANGER"}}
    m2 = ask(chat)
    deliver_all(session)
    other["actions"] = [{"value": json.dumps({"m": m2.id, "a": "dismiss", "v": None})}]
    slack_post(client, "/channels/slack/interactivity", urlencode({"payload": json.dumps(other)}).encode())
    session.refresh(m2)
    assert m2.status == "open"


def test_slack_dms_and_thread_replies(chat, client, session):
    connect_slack(chat, client, session)
    ask(chat)
    deliver_all(session)  # links U-SARAH
    v = slack_post(client, "/channels/slack/events", json.dumps({"type": "url_verification", "challenge": "c-1"}).encode())
    assert v.json() == {"challenge": "c-1"}
    dm = {"type": "event_callback", "team_id": "T-ACME", "event": {"type": "message", "channel_type": "im", "channel": "D-SARAH",
                                                                      "user": "U-SARAH", "text": "how's it going?"}}
    before = len(chat["fake"].sent("/chat.postMessage"))
    slack_post(client, "/channels/slack/events", json.dumps(dm).encode())
    said = chat["fake"].sent("/chat.postMessage")[before:]
    assert said and session.scalar(select(Message).where(Message.kind == "standup", Message.user_id == chat["user"].id))
    # Retries from Slack are ignored, so nothing is said twice.
    slack_post(client, "/channels/slack/events", json.dumps(dm).encode(), **{"X-Slack-Retry-Num": "1"})
    assert len(chat["fake"].sent("/chat.postMessage")) == before + len(said)
    # A typed reply in the thread of a question that wants words is its answer, redacted.
    why = ask(chat, payload={"type": "bank", "key": "first_check", "team": "invoice_mismatch"}, body="What do you check first?")
    deliver_all(session)
    session.refresh(why)
    thread_ts = why.external_ref.split(":", 2)[2]
    reply = {**dm, "event": {**dm["event"], "thread_ts": thread_ts, "text": "The PO number. Call me on 07700 900123."}}
    slack_post(client, "/channels/slack/events", json.dumps(reply).encode())
    session.refresh(why)
    assert why.status == "answered" and "07700" not in json.dumps(why.payload)


# Teams ------------------------------------------------------------------------------------------------

def test_teams_links_once_then_delivers_cards_and_takes_answers(chat, client, session):
    admin.connect_chat(session, _org_name(session, chat["user"]), "teams", "tenant-1")
    code = client.get("/channels", headers=chat["mentor"]).json()["teams_code"]
    activity = {"type": "message", "serviceUrl": "https://teams.test/", "conversation": {"id": "conv-1"},
                "from": {"id": "29:1", "aadObjectId": "aad-sarah"}, "channelData": {"tenant": {"id": "tenant-1"}}}
    assert client.post("/channels/teams/messages", json={**activity, "text": f"link {code}"}).status_code == 401  # no token
    client.post("/channels/teams/messages", json={**activity, "text": "link WRONG123"}, headers={"Authorization": "Bearer good"})
    session.refresh(chat["user"])
    assert "teams" not in chat["user"].preferences
    client.post("/channels/teams/messages", json={**activity, "text": f"link {code}"}, headers={"Authorization": "Bearer good"})
    session.refresh(chat["user"])
    assert chat["user"].preferences["teams"]["conversation_id"] == "conv-1"
    assert client.patch("/me/preferences", json={"channel": "teams"}, headers=chat["mentor"]).status_code == 200
    m = ask(chat)
    deliver_all(session)
    session.refresh(m)
    card = next(b for u, b in chat["fake"].calls if u.endswith("/v3/conversations/conv-1/activities") and b.get("attachments"))
    actions = card["attachments"][0]["content"]["actions"]
    assert actions[0]["data"] == {"newt": {"m": m.id, "a": "decide", "v": "approve"}} and actions[-1]["type"] == "Action.OpenUrl"
    client.post("/channels/teams/messages", json={**activity, "value": {"newt": {"m": m.id, "a": "dismiss", "v": None}}},
                headers={"Authorization": "Bearer good"})
    session.refresh(m)
    assert m.status == "dismissed" and m.external_ref.startswith("teams:conv-1:")


# Email ------------------------------------------------------------------------------------------------

def test_email_replies_are_signed_from_the_right_person_and_quoted_text_is_ignored(chat, client, session):
    assert client.patch("/me/preferences", json={"channel": "email"}, headers=chat["mentor"]).status_code == 200
    m = ask(chat)
    deliver_all(session)
    [mail] = chat["mails"]
    reply_to = mail["Reply-To"]
    assert email_channel.message_id_from(reply_to) == m.id and "1. Approve" in mail.get_content()
    forged = reply_to.replace(reply_to.split(".")[-2][-4:], "0000")
    assert email_channel.message_id_from(forged) is None
    inbound = {"to": reply_to, "from": f"Sarah <{chat['user'].email}>", "text": "3\n\nOn Tue, Newt wrote:\n> 1. Approve"}
    assert client.post("/channels/email/inbound", json=inbound, headers={"X-Newt-Inbound": "nope"}).status_code == 401
    stranger = client.post("/channels/email/inbound", json={**inbound, "from": "mallory@evil.test"},
                           headers={"X-Newt-Inbound": "inbound-secret"}).json()
    assert stranger["status"] == "ignored"
    session.refresh(m)
    assert m.status == "open"
    ok = client.post("/channels/email/inbound", json=inbound, headers={"X-Newt-Inbound": "inbound-secret"}).json()
    assert ok["status"] == "done"
    session.refresh(m)
    assert m.status == "dismissed" and m.payload["answer"] == {"action": "dismiss", "value": None}


def test_work_already_dealt_with_in_the_app_is_not_sent(chat, client, session):
    client.patch("/me/preferences", json={"channel": "email"}, headers=chat["mentor"])
    m = ask(chat)
    client.post(f"/messages/{m.id}/reply", json={"action": "dismiss"}, headers=chat["mentor"])
    deliver_all(session)
    assert chat["mails"] == [] and session.get(Message, m.id).external_ref is None


def test_choosing_a_channel_brings_the_latest_waiting_work_along(chat, client, session):
    waiting = [ask(chat, body=f"Invoice INV-{n}: approve or query?") for n in range(7)]
    connect_slack(chat, client, session)  # chooses Slack
    deliver_all(session)
    sent = [m for m in waiting if session.get(Message, m.id).external_ref]
    assert len(sent) == channels.CATCH_UP and {m.id for m in sent} == {m.id for m in waiting[-channels.CATCH_UP:]}
