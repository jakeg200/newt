"""From decisions to outcomes: what drives exceptions, owner promotion gates, and initiatives an owner Newt proposes,
agreed by a manager and tracked honestly."""

import pytest
from sqlalchemy import select

from app.agents import registry
from app.colleague import career
from app.models import Apprenticeship, TaskType, User
from app.outcomes import insights
from app.task_types import InsightDimension

from tests.graduation_fixtures import setup_team

SUPPLIER = InsightDimension(name="supplier", source="subject", pattern="^(.+?) invoice")
ALWAYS_ON = {"start": "00:00", "end": "23:59", "workdays": [0, 1, 2, 3, 4, 5, 6]}


def test_dimension_values():
    assert insights.dimension_value({"subject": "Contoso Facilities invoice INV-1"}, SUPPLIER) == "Contoso Facilities"
    assert insights.dimension_value({"subject": "no match here"}, SUPPLIER) is None
    assert insights.dimension_value({"inputs": {"trade": "plumbing"}}, InsightDimension(name="trade", source="trade")) == "plumbing"


def test_drivers_find_who_causes_exceptions():
    items = [({"subject": f"Contoso invoice {i}"}, "query_supplier" if i < 8 else "approve") for i in range(10)]
    items += [({"subject": f"Northwind invoice {i}"}, "approve") for i in range(30)]
    items += [({"subject": f"Fabrikam invoice {i}"}, "query_supplier" if i < 2 else "approve") for i in range(20)]
    d = insights.find_drivers(items, [SUPPLIER], minutes=6, weeks=4)
    assert d["usual"] == "approve" and d["base_rate"] == round(10 / 60, 3)
    top = d["drivers"][0]
    assert top["value"] == "Contoso" and top["exceptions"] == 8 and top["top_exception"] == "query_supplier" and top["lift"] > 4
    assert top["hours_per_week"] == 0.2
    assert all(r["value"] != "Fabrikam" for r in d["drivers"])  # 10% isn't unusual against a 17% base


@pytest.fixture
def team(client, session):
    ctx = setup_team(client, session)
    client.patch("/me/preferences", json=ALWAYS_ON, headers=ctx["manager"])
    yield ctx
    registry.set_runner_override(None)


def test_owner_needs_to_be_earned(team, session):
    tt = session.get(TaskType, team["tt"])
    manager = session.scalar(select(User).where(User.role == "manager"))
    assert career.owner_ready(session, tt) is None  # not even senior yet
    with pytest.raises(career.CareerError):
        career.grant(session, manager, tt, "owner")


def test_an_owner_proposes_initiatives_the_manager_agrees(team, client, session, monkeypatch):
    tt = session.get(TaskType, team["tt"])
    tt.status = "autonomous"
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    app_.settings = {**(app_.settings or {}), "responsibilities": {tt.id: {"follow_ups": {}, "owner": {"kpi": "share_by_newt"}}}}
    session.commit()
    assert career.rank(session, tt) == "owner"
    monkeypatch.setattr(insights, "drivers", lambda s, t, **kw: {"usual": "approve", "base_rate": 0.2, "cases": 60, "drivers": [
        {"key": "supplier:Contoso", "dimension": "supplier", "value": "Contoso", "cases": 10, "exceptions": 8, "rate": 0.8, "lift": 4.0,
         "top_exception": "query_supplier", "hours_per_week": 1.5}]})
    msgs = client.get(f"/messages?task_type_id={team['tt']}", headers=team["manager"]).json()["messages"]
    idea = next(m for m in msgs if m["kind"] == "initiative")
    assert "Contoso" in idea["body"] and "@" not in idea["payload"]["draft"]
    r = client.post(f"/messages/{idea['id']}/reply", json={"action": "confirm", "value": "yes"}, headers=team["manager"]).json()
    assert "draft" in r[-1]["body"]
    progress = insights.progress(session, tt)
    assert progress and progress[0]["status"] == "running" and progress[0]["baseline_rate"] == 0.8
    o = client.get(f"/task-types/{team['tt']}/outcomes", headers=team["manager"]).json()
    assert any(p["to"] == "initiative" for p in o["promotions"])
    assert client.get(f"/task-types/{team['tt']}/insights", headers=team["manager"]).json()["rank"] == "owner"
