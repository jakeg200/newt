"""Capacity planning and the supervisor's view: the share of a role Newt can carry at a risk limit (the same maths as
the graduation gate), what-ifs, and what's left for people."""

import pytest

from app.agents import registry
from app.eval.stats import choose_tau
from app.graduation import engine
from app.models import TaskType
from app.outcomes import capacity

from tests.graduation_fixtures import backtest, setup_team


@pytest.fixture
def team(client, session):
    ctx = setup_team(client, session)
    backtest(ctx, session, limit=200)
    client.patch("/manager/settings/invoice_mismatch", json={"minutes_per_case": 6, "hourly_cost": 40}, headers=ctx["manager"])
    yield ctx
    registry.set_runner_override(None)


def test_plan_uses_the_graduation_maths(team, session):
    tt = session.get(TaskType, team["tt"])
    plan = capacity.plan(session, tt)
    scores, errors = engine.scores_and_errors(session, tt)
    th = choose_tau(scores, errors, plan["alpha"])
    assert plan["current"]["share"] == round(th.coverage if th.tau is not None else 0.0, 3)
    assert plan["volume_per_week"] > 0 and plan["current"]["hours_per_week"] is not None
    shares = [w["share"] for w in plan["what_if"]]
    assert shares == sorted(shares)  # a looser risk limit never carries less
    assert plan["human_cases_per_week"] == round(plan["volume_per_week"] - plan["current"]["cases_per_week"], 1)


def test_team_view_and_role_redesign(team, client):
    t = client.get("/team", headers=team["manager"]).json()
    mine = next(n for n in t["newts"] if n["id"] == team["tt"])
    assert mine["title"] and mine["evidence"]["n_above"] >= 0 and "drafts" in mine["needs_people"]
    assert t["role"]["newts"] >= 1 and 0 <= t["role"]["share"] <= 1
    cap = client.get(f"/task-types/{team['tt']}/capacity", headers=team["mentor"]).json()
    assert "what_if" in cap and "human_work" in cap
