"""The manager dashboard: cases handled, hours returned, cost line; nothing about the mentor."""

import json

import pytest
from sqlalchemy import select

from app.agents import registry
from app.models import TaskType

from tests.graduation_fixtures import drain, live_items, push, setup_team


@pytest.fixture
def team(client, session):
    ctx = setup_team(client, session)
    yield ctx
    registry.set_runner_override(None)


def test_dashboard_counts_work_and_value(team, session, client):
    tt = session.get(TaskType, team["tt"])
    tt.status, tt.tau = "supervised", 0.5
    session.commit()
    items = live_items(12)
    push(team, {"items": items})
    drain(session)
    drafts = client.get(f"/supervised?task_type_id={tt.id}", headers=team["mentor"]).json()
    for d in drafts:
        client.post(f"/supervised/{d['prediction_id']}/approve", json={}, headers=team["mentor"])

    board = client.get("/manager/dashboard", headers=team["manager"]).json()
    ap = next(t for t in board["teams"] if t["team"] == "invoice_mismatch")
    assert ap["cases_handled"] == len(drafts) > 0
    assert ap["hours_returned"] is None  # needs the manager's minutes per case
    assert ap["stages"]["supervised"] == 1

    assert client.patch("/manager/settings/invoice_mismatch", json={"minutes_per_case": 6}, headers=team["mentor"]).status_code == 403
    client.patch("/manager/settings/invoice_mismatch", json={"minutes_per_case": 6, "hourly_cost": 45, "currency": "GBP",
                                                             "usd_rate": 0.8}, headers=team["manager"])
    ap = next(t for t in client.get("/manager/dashboard", headers=team["manager"]).json()["teams"] if t["team"] == "invoice_mismatch")
    assert ap["hours_returned"] == round(len(drafts) * 6 / 60, 1)
    assert ap["value_of_hours"] == round(ap["hours_returned"] * 45, 2)
    assert ap["net"] == round(ap["value_of_hours"] - ap["running_cost"], 2)
    assert ap["settings"]["currency"] == "GBP"

    # Nothing about the mentor as a person.
    text = json.dumps(ap).lower()
    for word in ("mentor", "untouched", "override", "review_time", "sarah"):
        assert word not in text, word


def test_me_flags_synthetic_orgs(client, session, team):
    me = client.get("/me", headers=team["manager"]).json()
    assert me["synthetic"] is True and me["org"] == "Synthetic Co"


def test_each_team_names_its_intern(client, team):
    tt = client.get("/task-types", headers=team["mentor"]).json()
    assert tt[0]["intern_name"] == "Newt"  # the default
    url = "/manager/settings/invoice_mismatch"
    assert client.patch(url, json={"intern_name": "Rosie"}, headers=team["mentor"]).status_code == 403
    assert client.patch(url, json={"intern_name": "<b>x</b>"}, headers=team["manager"]).status_code == 422
    assert client.patch(url, json={"intern_name": "Rosie"}, headers=team["manager"]).json()["intern_name"] == "Rosie"
    assert client.get("/task-types", headers=team["mentor"]).json()[0]["intern_name"] == "Rosie"
