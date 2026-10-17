import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.capture import service
from app.capture.keys import ref_tokens
from app.capture.matcher import ActionKeys, CaseKeys, classify, match_action
from app.capture.redact import Redactor
from app.capture.sources import gmail
from app.capture.sources.email_source import strip_quoted
from app.models import Case, HumanAction, User
from app.seed import seed
from app.task_types import CaptureRule

from tests.capture_fixtures import MENTOR, _msg

T0 = datetime(2026, 3, 2, 9, tzinfo=timezone.utc)


# Redaction ---------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("mail jo.bloggs@example.co.uk now", "EMAIL"),
        ("call 07700 900123", "PHONE"),
        ("call +44 20 7946 0958", "PHONE"),
        ("sort code 20-45-77", "SORTCODE"),
        ("account number 41234567", "ACCOUNT"),
        ("IBAN GB33BUKB20201555555555", "IBAN"),
        ("card 4111 1111 1111 1111", "CARD"),
        ("NI AB 12 34 56 C", "NINO"),
    ],
)
def test_personal_data_is_pseudonymised(text, kind):
    out = Redactor()(text)
    assert f"[{kind} " in out
    assert not any(ch.isdigit() for ch in out.split("[")[0][-3:])  # value gone, not just tagged


@pytest.mark.parametrize(
    "text",
    ["Invoice INV-20481", "PO-4512 for £4,950.00", "on 01/03/2026 at 09:30", "ticket 0004512345",
     "card-like 4111 1111 1111 1112"],  # fails the Luhn check, so it's not a card
)
def test_business_references_survive(text):
    assert Redactor()(text) == text


def test_pseudonyms_are_stable_and_distinct():
    r = Redactor()
    a, b, c = r("a@x.example"), r("A@X.example"), r("b@x.example")
    assert a == b != c
    assert r.counts["EMAIL"] == 3


def test_reference_tokens_skip_placeholders_and_noise():
    text = Redactor()("Re INV-1001 / PO-7700, £1,200.00, 2026, 01/03/2026, ring 07700 900123")
    assert ref_tokens(text) == {"INV-1001", "PO-7700"}


def test_quoted_history_is_stripped():
    body = "Thanks, querying now.\n\nOn Mon, 2 Mar 2026, Jo <jo@x.example> wrote:\n> original text\n> more"
    assert strip_quoted(body) == "Thanks, querying now."
    assert strip_quoted("Line one\n> quoted\nLine two") == "Line one\nLine two"


# Matcher -----------------------------------------------------------------------------------

def _case(cid, hours=0, **kw):
    return CaseKeys(case_id=cid, source_ref=cid, received_at=T0 + timedelta(hours=hours), **kw)


def test_reply_header_beats_everything():
    cases = [_case("a", message_ids={"m1"}, thread="t", refs={"INV-1"}), _case("b", 1, thread="t", refs={"INV-1"})]
    m = match_action(ActionKeys(acted_at=T0 + timedelta(hours=2), in_reply_to="m1", thread="t"), cases)
    assert (m.case_id, m.method) == ("a", "reply_header")


def test_thread_prefers_latest_open_item():
    cases = [_case("a", thread="t"), _case("b", 1, thread="t", decided=True), _case("c", 5, thread="t")]
    m = match_action(ActionKeys(acted_at=T0 + timedelta(hours=3), thread="t"), cases)
    assert (m.case_id, m.method) == ("a", "thread")  # c arrived after the action; b is already decided


def test_reference_needs_a_unique_best_candidate():
    cases = [_case("a", refs={"PO-1", "INV-1"}), _case("b", refs={"PO-1", "INV-2"})]
    at = T0 + timedelta(hours=1)
    assert match_action(ActionKeys(acted_at=at, refs={"INV-2"}), cases).case_id == "b"
    ambiguous = match_action(ActionKeys(acted_at=at, refs={"PO-1"}), cases)
    assert ambiguous.case_id is None and "2 items" in ambiguous.reason


def test_reference_window_and_time_travel():
    cases = [_case("old", refs={"INV-1"}), _case("future", 10, refs={"INV-2"})]
    assert match_action(ActionKeys(acted_at=T0 + timedelta(days=90), refs={"INV-1"}), cases).case_id is None
    assert match_action(ActionKeys(acted_at=T0 + timedelta(hours=1), refs={"INV-2"}), cases).case_id is None


def test_explicit_reference_must_exist_and_precede():
    cases = [_case("a", 5)]
    assert match_action(ActionKeys(acted_at=T0 + timedelta(hours=6), item_ref="a"), cases).method == "explicit"
    assert "before its item" in match_action(ActionKeys(acted_at=T0, item_ref="a"), cases).reason
    assert "hasn't been captured" in match_action(ActionKeys(acted_at=T0, item_ref="zz"), cases).reason


def test_classify_uses_rules_in_order():
    rules = [CaptureRule(action="label", label="Approved", decision="approve"),
             CaptureRule(action="reply", decision="query"), CaptureRule(action="forward", decision="escalate")]
    assert classify("message", to_sender=True, label=None, status=None, rules=rules) == ("reply", "query")
    assert classify("message", to_sender=False, label=None, status=None, rules=rules) == ("forward", "escalate")
    assert classify("label", to_sender=False, label="approved", status=None, rules=rules) == ("label", "approve")
    assert classify("label", to_sender=False, label="Spam", status=None, rules=rules) == ("label", None)


# Gmail and OAuth (Google mocked) ------------------------------------------------------------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _google(messages: dict[str, bytes], thread_messages: dict[str, list[str]], calls: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.host == "oauth2.googleapis.com":
            form = parse_qs(request.content.decode())
            if form["grant_type"] == ["authorization_code"]:
                return httpx.Response(200, json={"refresh_token": "rt-1", "access_token": "at", "scope": gmail.SCOPE})
            return httpx.Response(200, json={"access_token": "at-1"})
        assert request.headers["Authorization"] == "Bearer at-1"
        path = request.url.path.removeprefix("/gmail/v1/users/me")
        if path == "/labels":
            return httpx.Response(200, json={"labels": [{"id": "L1", "name": "AP/Mismatch"}, {"id": "L2", "name": "Personal"}]})
        if path == "/threads":
            assert request.url.params["labelIds"] == "L1"  # never reads outside the label
            return httpx.Response(200, json={"threads": [{"id": t} for t in thread_messages]})
        if path.startswith("/threads/"):
            tid = path.split("/")[-1]
            return httpx.Response(200, json={"id": tid, "messages": [{"id": m} for m in thread_messages[tid]]})
        if path.startswith("/messages/"):
            return httpx.Response(200, json={"raw": _b64(messages[path.split("/")[-1]])})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def gmail_setup(client, session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "google_client_id", "cid")
    monkeypatch.setattr(get_settings(), "google_client_secret", "csecret")
    seed(session)
    mentor = session.scalar(select(User).where(User.email == "mentor+invoice_mismatch@synthetic.test"))
    headers = {"X-Dev-User": mentor.id}
    tt = next(t for t in client.get("/task-types", headers=headers).json() if t["team"] == "invoice_mismatch")
    conn = client.post("/connections", json={"name": "Sarah's inbox", "provider": "gmail", "task_type_id": tt["id"],
                                             "mentor_addresses": [MENTOR], "label": "AP/Mismatch", "consent": True},
                       headers=headers).json()
    return headers, conn


def test_gmail_oauth_then_sync_matches_by_thread(client, session, gmail_setup):
    headers, conn = gmail_setup
    assert conn["status"] == "pending"
    url = client.get(f"/connections/{conn['id']}/oauth/start", headers=headers).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == [gmail.SCOPE] and q["access_type"] == ["offline"]

    calls: list[str] = []
    item = _msg("<i1@sup.example>", "billing@sup.example", [MENTOR], T0, "Invoice INV-7001", "Invoice INV-7001 attached.")
    # The mentor's reply has no threading headers: only Gmail's thread id ties it to the item.
    reply = _msg("<r1@synthetic.test>", MENTOR, ["billing@sup.example"], T0 + timedelta(hours=1), "Re: your email", "Please resend.")
    google = _google({"m1": item, "m2": reply}, {"T1": ["m1", "m2"]}, calls)

    connection = service.oauth_finish(session, "auth-code", q["state"][0], http=google)
    assert connection.status == "active" and connection.encrypted_tokens and "rt-1" not in connection.encrypted_tokens
    assert service.decrypt(connection.encrypted_tokens) == "rt-1"

    run = service.sync_gmail(session, connection, http=google)
    assert run.stats["cases_created"] == 1 and run.stats["matched_thread"] == 1
    action = session.scalar(select(HumanAction).where(HumanAction.source == "gmail"))
    assert action.payload["decision"] == "query_supplier"
    assert session.scalar(select(Case).where(Case.connection_id == connection.id)).is_backtest  # mail from before connecting


def test_oauth_state_is_tamper_proof():
    state = service.sign_state("conn", "user")
    assert service.verify_state(state) == ("conn", "user")
    with pytest.raises(service.CaptureError):
        service.verify_state(state.replace("conn", "other"))


def test_gmail_requires_a_label_and_sign_in(client, session, gmail_setup):
    headers, conn = gmail_setup
    assert "sign in" in client.post(f"/connections/{conn['id']}/sync", headers=headers).json()["detail"]
    tt = conn["task_type_id"]
    resp = client.post("/connections", json={"name": "x", "provider": "gmail", "task_type_id": tt,
                                             "mentor_addresses": [MENTOR], "consent": True}, headers=headers)
    assert "label" in resp.json()["detail"]
