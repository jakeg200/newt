"""Getting better safely: every change to how Newt works is replayed on past cases first, and the blast radius decides
whether it goes live by itself or waits for the mentor."""

import pytest
from sqlalchemy import func, select

from app.agents import registry
from app.agents.context import ContextBuilder
from app.learning import improve
from app.models import Apprenticeship, Improvement, Message, Prediction, Rule, TaskType

from tests.graduation_fixtures import backtest, drain, run_change_tests, setup_team
from tests.test_process_replay import D, threaded_history


@pytest.fixture
def team(client, session):
    ctx = setup_team(client, session, history=300)
    client.patch("/me/preferences", json={"start": "00:00", "end": "23:59", "workdays": list(range(7))}, headers=ctx["mentor"])
    registry.set_runner_override(None)  # the offline agent, which follows rules
    backtest(ctx, session, limit=100)
    yield ctx
    registry.set_runner_override(None)


def thread(ctx, who="mentor"):
    return ctx["client"].get(f"/messages?task_type_id={ctx['tt']}", headers=ctx[who]).json()["messages"]


def test_a_rule_under_test_is_invisible_and_the_replay_leaves_nothing_behind(team, client, session):
    tt = session.get(TaskType, team["tt"])
    version = session.get(Apprenticeship, tt.apprenticeship_id).rules_version
    r = client.post("/rules", json={"task_type_id": tt.id, "text": 'When an item mentions "units", choose escalate.'}, headers=team["mentor"]).json()
    assert r["status"] == "testing" and r["improvement"]["status"] == "testing"
    assert all(rule.status == "active" for rule in ContextBuilder(session, tt).rules)  # no agent sees it yet
    assert r["id"] not in {rule.id for rule in ContextBuilder(session, tt).rules}
    predictions = session.scalar(select(func.count()).select_from(Prediction))
    [imp] = run_change_tests(session)
    assert session.scalar(select(func.count()).select_from(Prediction)) == predictions  # answered twice, kept nothing
    assert imp.blast["cases"] > 20 and imp.blast["broke"] > 0  # the team queries these, so it breaks past cases
    assert imp.status == "ready" and session.get(Apprenticeship, tt.apprenticeship_id).rules_version == version  # waits
    card = next(m for m in thread(team) if m["kind"] == "improvement")
    assert "breaks" in card["body"] and card["payload"]["blast"]["examples"]["broke"]
    assert client.post(f"/improvements/{imp.id}/promote", json={}, headers=team["mentor"]).status_code == 409  # must say keep
    assert client.post(f"/improvements/{imp.id}/promote", json={"keep_anyway": True}, headers=team["manager"]).status_code == 403
    r = client.post(f"/messages/{card['id']}/reply", json={"action": "confirm", "value": "no"}, headers=team["mentor"])
    assert r.status_code == 200 and "Dropped" in r.json()[-1]["body"]
    session.expire_all()
    assert session.get(Rule, imp.rule_id).status == "retired" and session.get(Improvement, imp.id).status == "rejected"


def test_a_mentor_rule_that_breaks_nothing_goes_live_by_itself(team, client, session):
    tt = session.get(TaskType, team["tt"])
    version = session.get(Apprenticeship, tt.apprenticeship_id).rules_version
    said = client.post("/messages", json={"task_type_id": tt.id, "text": 'Always escalate when an item mentions "approval limit"'},
                       headers=team["mentor"]).json()
    assert "testing it on past cases" in said[1]["body"]
    [imp] = run_change_tests(session)
    assert imp.status == "promoted" and imp.blast["broke"] == 0 and imp.repredict_run_id
    assert session.get(Apprenticeship, tt.apprenticeship_id).rules_version == version + 1
    assert any(m["kind"] == "ack" and "So it's live" in m["body"] for m in thread(team))
    log = client.get(f"/task-types/{tt.id}/improvements", headers=team["manager"]).json()
    assert log[0]["id"] == imp.id and log[0]["sentence"].startswith("Tested on")


def test_keeping_a_change_that_breaks_cases_is_the_mentors_call(team, client, session):
    tt = session.get(TaskType, team["tt"])
    client.post("/rules", json={"task_type_id": tt.id, "text": 'When an item mentions "units", choose approve.'}, headers=team["mentor"])
    [imp] = run_change_tests(session)
    card = next(m for m in thread(team) if m["kind"] == "improvement")
    client.post(f"/messages/{card['id']}/reply", json={"action": "confirm", "value": "yes"}, headers=team["mentor"])
    session.expire_all()
    imp = session.get(Improvement, imp.id)
    assert imp.status == "promoted" and session.get(Rule, imp.rule_id).status == "active" and imp.decided_by


def test_changing_a_live_routine_replays_whole_processes(client, session):
    ctx = setup_team(client, session, history=200)
    threaded_history(ctx, {0: 5 * D, 1: 1 * D, 2: None})
    tt = session.get(TaskType, ctx["tt"])
    first = client.put(f"/task-types/{tt.id}/routines/query_supplier", json={"steps": ["draft_reply", "set_status"], "follow_up_days": 3},
                       headers=ctx["mentor"]).json()
    assert first["status"] == "approved"  # nothing live yet, so nothing to test
    tt.status, tt.tau = "supervised", 0.0
    session.commit()
    r = client.put(f"/task-types/{tt.id}/routines/query_supplier", json={"steps": ["set_status"], "follow_up_days": None},
                   headers=ctx["mentor"]).json()
    assert r["status"] == "testing" and r["steps"] == ["draft_reply", "set_status"]  # still the old routine
    [imp] = run_change_tests(session)
    assert imp.blast["unit"] == "processes" and imp.blast["cases"] >= 3
    assert imp.blast["broke"] >= 3 and imp.status == "ready"  # the team replied; without a reply Newt wouldn't
    registry.set_runner_override(None)


def test_newt_never_learns_from_a_change_it_hasnt_tested(team, client, session):
    """The improvement job is the only way a testing rule becomes active; draining other work doesn't."""
    tt = session.get(TaskType, team["tt"])
    r = client.post("/rules", json={"task_type_id": tt.id, "text": 'When an item mentions "credit note", choose query supplier.'},
                    headers=team["mentor"]).json()
    assert session.get(Rule, r["id"]).status == "testing"
    drain(session)  # the worker runs everything queued, including the replay
    session.expire_all()
    imp = session.get(Improvement, r["improvement"]["id"])
    assert imp.status in ("promoted", "ready") and imp.blast["cases"] > 0
    assert (session.get(Rule, r["id"]).status == "active") == (imp.status == "promoted")
    assert session.scalar(select(Message).where(Message.dedupe_key == f"improvement:{imp.id}")) is not None
    if imp.status == "ready":
        improve.reject(session, None, imp)
    with pytest.raises(improve.ImproveError):  # a decided change can't be decided again
        improve.reject(session, None, imp)
