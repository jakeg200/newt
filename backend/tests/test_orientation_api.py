"""M1 acceptance: five real-format policy documents → a draft handbook where every item links
to its source passage → approval recorded by the manager, with versioning."""

import pytest
from sqlalchemy import select

from app.llm.provider import FakeProvider, set_provider
from app.models import Apprenticeship, Org, User
from app.orientation.offline import offline_responders
from app.seed import seed

from tests.helpers import five_policy_uploads

TEAM = "invoice_mismatch"


@pytest.fixture
def people(session):
    seed(session)
    users = {u.role: u for u in session.scalars(select(User)) if u.role == "manager" or TEAM in u.email}
    return {role: {"X-Dev-User": u.id} for role, u in users.items()}


@pytest.fixture
def fake():
    provider = FakeProvider(offline_responders())
    set_provider(provider)
    yield provider
    set_provider(None)


def _upload(client, headers, files=None):
    files = files or five_policy_uploads()
    return client.post(
        "/orientation/sources",
        data={"team": TEAM},
        files=[("files", (name, data)) for name, data in files],
        headers=headers,
    )


def _answer(client, headers):
    return client.put(
        f"/orientation/questionnaire?team={TEAM}",
        json={"answers": {
            "purpose": "We check and pay supplier invoices for Synthetic Co.",
            "first_check": "I always check the PO number and whether the supplier is a key account.",
            "always_escalate": "Always escalate bank detail changes to the Finance Controller.",
        }},
        headers=headers,
    )


def test_teams_listed_for_the_org(client, people):
    assert client.get("/orientation/teams", headers=people["mentor"]).json() == ["invoice_mismatch", "repair_request"]


def test_upload_five_documents_in_four_formats(client, people):
    resp = _upload(client, people["mentor"])
    assert resp.status_code == 201
    docs = resp.json()
    assert [d["doc_index"] for d in docs] == [1, 2, 3, 4, 5]
    assert all(d["passages"] >= 1 and not d["duplicate"] for d in docs)

    again = _upload(client, people["mentor"], five_policy_uploads()[:1]).json()
    assert again[0]["duplicate"] is True and again[0]["doc_index"] == 1

    listed = client.get(f"/orientation/sources?team={TEAM}", headers=people["mentor"]).json()
    assert len(listed) == 5
    labels = [p["label"] for p in client.get(f"/orientation/passages?team={TEAM}", headers=people["mentor"]).json()]
    assert labels[0] == "1.1" and any(label.startswith("5.") for label in labels)


def test_bad_file_reports_error_without_blocking_others(client, people):
    resp = _upload(client, people["mentor"], [("notes.exe", b"MZ"), five_policy_uploads()[0]])
    body = resp.json()
    assert "unsupported file type" in body[0]["error"]
    assert body[1]["doc_index"] == 1


def test_questionnaire_adapts_to_task_types_and_saves(client, people):
    questions = client.get(f"/orientation/questionnaire?team={TEAM}", headers=people["mentor"]).json()
    keys = [q["key"] for q in questions]
    assert "first_check" in keys
    assert "invoice_mismatch_under_5k.query_supplier" in keys  # from the task-type config
    assert _answer(client, people["mentor"]).json() == {"saved": 3}
    saved = {q["key"]: q["answer"] for q in client.get(f"/orientation/questionnaire?team={TEAM}", headers=people["mentor"]).json()}
    assert saved["first_check"].startswith("I always check")
    assert client.put(f"/orientation/questionnaire?team={TEAM}", json={"answers": {"nope": "x"}}, headers=people["mentor"]).status_code == 400
    assert _answer(client, people["manager"]).status_code == 403  # the mentor's questionnaire


def test_full_orientation_flow(client, people, fake, session):
    mentor, manager = people["mentor"], people["manager"]
    _upload(client, mentor)
    _answer(client, mentor)

    resp = client.post("/orientation/handbook/draft", json={"team": TEAM}, headers=mentor)
    assert resp.status_code == 201, resp.text
    draft = resp.json()
    assert draft["version"] == 1 and draft["status"] == "draft"

    # The prompt carried every source, labelled.
    prompt = fake.calls[0]["user"]
    assert '<source label="1.1"' in prompt and '<source label="Q.first_check"' in prompt

    # Every item links to a passage that exists.
    known = {p["label"] for p in client.get(f"/orientation/passages?team={TEAM}", headers=mentor).json()}
    content = draft["content"]
    items = [i for section in ("procedures", "decision_rules", "always_escalate", "glossary", "access_scopes", "escalation_contacts") for i in content[section]]
    assert len(items) >= 10
    assert all(i["sources"] and set(i["sources"]) <= known for i in items)
    assert content["purpose"]["sources"] == ["Q.purpose"]
    assert {g["term"] for g in content["glossary"]} >= {"PO", "GRN", "Accrual"}
    assert draft["meta"]["duration_s"] < 120
    assert draft["meta"]["issues"] == []

    # Only the manager approves.
    assert client.post(f"/orientation/handbook/{draft['id']}/approve", headers=mentor).status_code == 403
    approved = client.post(f"/orientation/handbook/{draft['id']}/approve", headers=manager).json()
    assert approved["status"] == "approved" and approved["approved_by"] == manager["X-Dev-User"] and approved["approved_at"]
    apprenticeship = session.scalar(select(Apprenticeship).where(Apprenticeship.team == TEAM))
    session.refresh(apprenticeship)
    assert apprenticeship.handbook_version == 1

    # Approved versions are frozen; changes go through a revision.
    assert client.patch(f"/orientation/handbook/{draft['id']}", json={"content": content}, headers=mentor).status_code == 400
    v2 = client.post(f"/orientation/handbook/{draft['id']}/revise", headers=mentor).json()
    assert v2["version"] == 2 and v2["status"] == "draft"

    # An item with no source blocks approval until it is cited or deleted.
    edited = {**v2["content"], "decision_rules": v2["content"]["decision_rules"] + [{"text": "Pay everything on Fridays.", "applies_to": "all", "sources": []}]}
    patched = client.patch(f"/orientation/handbook/{v2['id']}", json={"content": edited}, headers=mentor).json()
    new_id = patched["content"]["decision_rules"][-1]["id"]
    assert {"section": "decision_rules", "id": new_id, "problem": "no source"} in patched["meta"]["issues"]
    blocked = client.post(f"/orientation/handbook/{v2['id']}/approve", headers=manager)
    assert blocked.status_code == 400 and new_id in blocked.json()["detail"]

    # Deleting that item and adding another never hands the old id to the new item.
    without = {**patched["content"], "decision_rules": patched["content"]["decision_rules"][:-1]}
    client.patch(f"/orientation/handbook/{v2['id']}", json={"content": without}, headers=mentor)
    readded = {**without, "decision_rules": without["decision_rules"] + [{"text": "Pay on Fridays.", "applies_to": "all", "sources": ["1.1"]}]}
    final = client.patch(f"/orientation/handbook/{v2['id']}", json={"content": readded}, headers=mentor).json()
    assert final["content"]["decision_rules"][-1]["id"] != new_id
    assert final["meta"]["issues"] == []
    assert client.post(f"/orientation/handbook/{v2['id']}/approve", headers=manager).json()["status"] == "approved"

    versions = client.get(f"/orientation/handbook?team={TEAM}", headers=mentor).json()
    assert [(v["version"], v["status"]) for v in versions] == [(2, "approved"), (1, "superseded")]


def test_draft_needs_sources(client, people, fake):
    resp = client.post("/orientation/handbook/draft", json={"team": TEAM}, headers=people["mentor"])
    assert resp.status_code == 400 and "upload at least one document" in resp.json()["detail"]


def test_other_orgs_cannot_see_anything(client, people, fake, session):
    _upload(client, people["mentor"])
    _answer(client, people["mentor"])
    draft = client.post("/orientation/handbook/draft", json={"team": TEAM}, headers=people["mentor"]).json()

    other = Org(name="Other Co")
    session.add(other)
    session.flush()
    outsider = User(org_id=other.id, role="manager", email="m@other.test", name="Outsider")
    session.add(outsider)
    session.commit()
    headers = {"X-Dev-User": outsider.id}
    assert client.get(f"/orientation/handbook/{draft['id']}", headers=headers).status_code == 404
    assert client.post(f"/orientation/handbook/{draft['id']}/approve", headers=headers).status_code == 404
    assert client.get(f"/orientation/sources?team={TEAM}", headers=headers).status_code == 404
