"""M2 acceptance: 20 of 20 test items become cases; at least 95% of mentor actions matched
(and none matched wrongly); no message bodies in logs, no raw personal data stored."""

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Case, Consent, HumanAction, UnmatchedAction, User
from app.seed import seed

from tests.capture_fixtures import CSV_COLUMNS, MENTOR, PII, SENTINEL, build_csv, build_mailbox


@pytest.fixture
def ctx(client, session):
    seed(session)
    mentor = session.scalar(select(User).where(User.email == "mentor+invoice_mismatch@synthetic.test"))
    manager = session.scalar(select(User).where(User.role == "manager"))
    headers = {"X-Dev-User": mentor.id}
    task_types = {t["team"]: t for t in client.get("/task-types", headers=headers).json()}
    return {"mentor": headers, "manager": {"X-Dev-User": manager.id}, "tt": task_types["invoice_mismatch"]["id"]}


def _email_connection(client, ctx, **overrides):
    body = {"name": "AP inbox export", "provider": "email_upload", "task_type_id": ctx["tt"],
            "mentor_addresses": [MENTOR], "body_input": "invoice_text", "consent": True, **overrides}
    return client.post("/connections", json=body, headers=ctx["mentor"])


def _import(client, ctx, connection_id, files):
    return client.post(f"/connections/{connection_id}/import", files=[("files", f) for f in files], headers=ctx["mentor"])


def test_email_acceptance(client, ctx, session, caplog):
    caplog.set_level(logging.DEBUG)
    fixture = build_mailbox()
    conn = _email_connection(client, ctx).json()
    run = _import(client, ctx, conn["id"], fixture.files)
    assert run.status_code == 201, run.text
    stats = run.json()["stats"]

    # 20 of 20 items become cases; the duplicate upload doesn't make a 21st.
    assert stats["cases_created"] == 20
    assert stats["duplicate_items"] == 1
    cases = {c.source_ref: c for c in session.scalars(select(Case).where(Case.connection_id == conn["id"]))}
    assert set(cases) == set(fixture.item_ids)

    # Every true action matched to the right item; decoys stay unmatched.
    actions = {a.source_ref: a for a in session.scalars(select(HumanAction).where(HumanAction.source == "email_upload"))}
    correct = sum(1 for act, item in fixture.expected.items() if act in actions and actions[act].case_id == cases[item].id)
    assert correct / len(fixture.expected) >= 0.95
    assert correct == 20
    assert not set(fixture.decoys) & set(actions)
    unmatched = {u.source_ref: u.reason for u in session.scalars(select(UnmatchedAction))}
    assert set(unmatched) == set(fixture.decoys)
    assert "2 items share" in unmatched["<decoy2@synthetic.test>"]
    assert stats["matched_reply_header"] == 16 and stats["matched_reference"] == 4
    assert stats["match_rate"] == pytest.approx(20 / 22, abs=1e-4)

    # Decisions come from the task type's capture rules.
    for item_id, decision in fixture.expected_decisions.items():
        case = cases[item_id]
        assert case.status == "decided"
        got = session.scalar(select(HumanAction).where(HumanAction.case_id == case.id))
        assert got.payload["decision"] == decision, item_id
    reply = actions["<act0@synthetic.test>"]
    assert reply.action_type == "reply"
    assert "credit note" in reply.payload["text_outputs"]["supplier_email"]
    assert SENTINEL not in reply.payload["text_outputs"]["supplier_email"]  # quoted text stripped

    # Nothing raw is stored: not in snapshots, payloads or match keys.
    stored = json.dumps([c.snapshot for c in cases.values()] + [c.match_keys for c in cases.values()]
                        + [a.payload for a in actions.values()] + [u.summary for u in session.scalars(select(UnmatchedAction))])
    for value in PII + [MENTOR, "billing@northwind.example"]:
        assert value not in stored, value
    assert "[EMAIL " in stored and "[PHONE " in stored and "[SORTCODE " in stored and "[IBAN " in stored
    assert "INV-1001" in stored  # reference numbers survive

    # No message bodies (or personal data) in logs.
    assert caplog.records, "expected capture to log something"
    for value in [SENTINEL, "credit note", *PII]:
        assert value not in caplog.text


def test_reimport_is_idempotent(client, ctx, session):
    fixture = build_mailbox()
    conn = _email_connection(client, ctx).json()
    _import(client, ctx, conn["id"], fixture.files)
    again = _import(client, ctx, conn["id"], fixture.files).json()["stats"]
    assert again["cases_created"] == 0 and again["duplicate_items"] == 21
    assert again["duplicate_actions"] == 22
    assert len(session.scalars(select(HumanAction).where(HumanAction.source == "email_upload")).all()) == 20


def test_actions_captured_before_their_items_match_later(client, ctx, session):
    """Upload order doesn't matter: waiting actions are retried when their items arrive."""
    fixture = build_mailbox()
    conn = _email_connection(client, ctx).json()
    first = _import(client, ctx, conn["id"], [f for f in fixture.files if f[0].startswith("action_")]).json()["stats"]
    assert first["actions_unmatched"] == 20
    second = _import(client, ctx, conn["id"], [f for f in fixture.files if f[0].startswith("item_")]).json()["stats"]
    assert second["cases_created"] == 20 and second["earlier_actions_matched"] == 20
    assert session.scalars(select(UnmatchedAction)).all() == []
    actions = {a.source_ref: a.case_id for a in session.scalars(select(HumanAction).where(HumanAction.source == "email_upload"))}
    cases = {c.source_ref: c.id for c in session.scalars(select(Case))}
    assert all(actions[act] == cases[item] for act, item in fixture.expected.items())


def test_an_action_dated_before_its_item_never_matches(client, ctx, session):
    from tests.capture_fixtures import _msg

    conn = _email_connection(client, ctx).json()
    at = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)
    item = _msg("<late@x.example>", "billing@x.example", [MENTOR], at, "Invoice INV-5555", "Invoice INV-5555 attached.")
    early_reply = _msg("<early@synthetic.test>", MENTOR, ["billing@x.example"], at - timedelta(hours=1),
                       "Re: Invoice INV-5555", "Query.", in_reply_to="<late@x.example>", references=["<late@x.example>"])
    stats = _import(client, ctx, conn["id"], [("i.eml", item), ("a.eml", early_reply)]).json()["stats"]
    assert stats["actions_matched"] == 0 and stats["actions_unmatched"] == 1


def test_email_connection_needs_consent_and_mentor(client, ctx, session):
    assert "consent" in _email_connection(client, ctx, consent=False).json()["detail"]
    assert "mentor" in _email_connection(client, ctx, mentor_addresses=[]).json()["detail"]
    assert _email_connection(client, ctx, mentor_addresses=["not-an-address"]).status_code == 422
    conn = _email_connection(client, ctx).json()
    consent = session.scalar(select(Consent))
    assert consent.scopes["connection_id"] == conn["id"] and consent.text_version == "capture-v1"
    # Managers don't capture the mentor's mail.
    assert _email_connection(client, ctx | {"mentor": ctx["manager"]}).status_code == 403


def test_bad_files_are_reported_not_fatal(client, ctx):
    conn = _email_connection(client, ctx).json()
    files = [("notes.txt", b"hello"), ("broken.eml", b"Subject: no date or id\n\nbody"), build_mailbox().files[0]]
    stats = _import(client, ctx, conn["id"], files).json()["stats"]
    assert stats["cases_created"] == 1
    assert any("notes.txt" in e for e in stats["errors"]) and any("broken.eml" in e for e in stats["errors"])


def test_paused_connection_refuses_imports(client, ctx):
    conn = _email_connection(client, ctx).json()
    client.patch(f"/connections/{conn['id']}", json={"status": "paused"}, headers=ctx["mentor"])
    resp = _import(client, ctx, conn["id"], build_mailbox().files[:1])
    assert resp.status_code == 400 and "paused" in resp.json()["detail"]


def test_csv_import(client, ctx, session):
    conn = client.post("/connections", json={"name": "Ledger export", "provider": "csv", "task_type_id": ctx["tt"],
                                             "columns": CSV_COLUMNS}, headers=ctx["mentor"]).json()
    bad_row = b"INV-9999,yesterday-ish,S,x,PO-1,Approved,2026-03-01 10:00,price,6400,\n"
    stats = _import(client, ctx, conn["id"], [("ledger.csv", build_csv() + bad_row)]).json()["stats"]
    assert stats["cases_created"] == 20 and stats["actions_matched"] == 20 and stats["matched_explicit"] == 20
    assert any("unrecognised date" in e for e in stats["errors"])
    decisions = [a.payload["decision"] for a in session.scalars(
        select(HumanAction).where(HumanAction.source == "csv").order_by(HumanAction.acted_at))]
    assert decisions[:3] == ["approve", "query_supplier", "escalate"]
    queried = session.scalar(select(HumanAction).where(HumanAction.source_ref == "INV-2002#decision"))
    assert queried.payload["fields"] == {"variance_reason": "price", "gl_code": "6400"}
    assert "07700 900123" not in queried.payload["text_outputs"]["supplier_email"]


def test_csv_column_map_is_validated(client, ctx):
    resp = client.post("/connections", json={"name": "x", "provider": "csv", "task_type_id": ctx["tt"],
                                              "columns": {**CSV_COLUMNS, "inputs": {"not_an_input": "a"}}}, headers=ctx["mentor"])
    assert resp.status_code == 400 and "not_an_input" in resp.json()["detail"]


def test_rest_push(client, ctx, session):
    conn = client.post("/connections", json={"name": "Helpdesk", "provider": "rest", "task_type_id": ctx["tt"]},
                       headers=ctx["mentor"]).json()
    token, url = conn["push_token"], f"/capture/push/{conn['id']}"
    assert client.get("/connections", headers=ctx["mentor"]).json()[0].get("push_token") is None  # shown once
    now = datetime.now(timezone.utc)
    items = {"items": [{"ref": f"T-{n}", "received_at": (now + timedelta(minutes=n)).isoformat(),
                        "inputs": {"invoice_text": f"Ticket T-{n}"}} for n in range(3)]}
    assert client.post(url, json=items, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post(url, json=items).status_code == 401
    first = client.post(url, json=items, headers={"Authorization": f"Bearer {token}"}).json()["stats"]
    assert first["cases_created"] == 3

    later = now + timedelta(hours=1)
    actions = {"actions": [
        {"ref": "a1", "item_ref": "T-0", "acted_at": later.isoformat(), "kind": "status", "status": "approved"},
        {"ref": "a2", "item_ref": "T-1", "acted_at": later.isoformat(), "decision": "escalate"},
        {"ref": "a3", "item_ref": "T-9", "acted_at": later.isoformat(), "decision": "escalate"},
        {"ref": "a4", "item_ref": "T-2", "acted_at": later.isoformat(), "decision": "pay_twice"},
    ]}
    second = client.post(url, json=actions, headers={"Authorization": f"Bearer {token}"}).json()["stats"]
    assert second["actions_matched"] == 2 and second["actions_unmatched"] == 1 and second["error_count"] == 1
    by_ref = {a.source_ref: a for a in session.scalars(select(HumanAction))}
    assert by_ref["a1"].payload["decision"] == "approve"  # via the "status: approved" capture rule
    assert not session.scalar(select(Case).where(Case.source_ref == "T-0")).is_backtest  # pushed live


def test_cases_api(client, ctx):
    conn = _email_connection(client, ctx).json()
    _import(client, ctx, conn["id"], build_mailbox().files)
    listing = client.get(f"/cases?task_type_id={ctx['tt']}&limit=5", headers=ctx["mentor"]).json()
    assert listing["total"] == 20 and len(listing["items"]) == 5
    assert listing["items"][0]["decision"] in ("query_supplier", "escalate")
    detail = client.get(f"/cases/{listing['items'][0]['id']}", headers=ctx["mentor"]).json()
    assert detail["snapshot"]["inputs"]["invoice_text"] and detail["actions"][0]["match_method"]
    assert client.get(f"/cases?task_type_id={ctx['tt']}", headers=ctx["manager"]).status_code == 403
    summary = client.get(f"/connections?task_type_id={ctx['tt']}", headers=ctx["mentor"]).json()[0]
    assert summary["cases"] == 20 and summary["decided"] == 20 and summary["last_run"]["stats"]["cases_created"] == 20
