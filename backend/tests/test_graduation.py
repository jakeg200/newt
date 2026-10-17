"""The full journey: shadow → supervised → autonomous, with hand-backs, blind audits, demotion,
drift, re-probation after a model swap (M5 acceptance: under 10 minutes), and the track record."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.agents import registry
from app.graduation import engine
from app.models import ActionLog, Audit, BacktestRun, Case, GraduationEvent, Prediction, TaskType, utcnow

from tests.graduation_fixtures import PatternAgent, backtest, drain, live_items, mentor_decides, push, setup_team


@pytest.fixture
def team(client, session):
    ctx = setup_team(client, session)
    yield ctx
    registry.set_runner_override(None)


def _shadow_to_eligible(team, session, live: int = 60):
    backtest(team, session)
    items = live_items(live)
    push(team, {"items": items})
    drain(session)  # sealed live predictions
    sealed = session.scalars(select(Prediction).where(Prediction.run_id.is_(None))).all()
    assert len(sealed) == live
    mentor_decides(team, items)
    drain(session)  # the mentor acted: predictions revealed and scored


def _evaluation(team):
    return team["client"].get(f"/task-types/{team['tt']}/evaluation", headers=team["mentor"]).json()


def test_shadow_evidence_and_the_bar(team, session):
    backtest(team, session)
    ev = _evaluation(team)
    assert ev["status"] == "shadow" and ev["cases"] == 300 and ev["live_cases"] == 0
    assert not ev["eligible"] and {c["name"]: c["ok"] for c in ev["checks"]}["live"] is False
    assert ev["cases_needed"] == 149  # zero errors at 2%
    _shadow_to_eligible(team, session)
    ev = _evaluation(team)
    assert ev["live_cases"] == 60 and ev["live_above"] >= 50
    assert ev["eligible"], ev["checks"]
    assert ev["ucb"] <= 0.02 and ev["coverage"] >= 0.4 and ev["tau"] is not None
    assert "criteria" in ev and ev["criteria"]  # the classifier's view of the mentor's criteria


def test_full_journey(team, session, client):
    _shadow_to_eligible(team, session)
    url = f"/task-types/{team['tt']}/graduate"
    assert client.post(url, json={"to": "supervised"}, headers=team["manager"]).status_code == 403  # the mentor signs this one
    signed = client.post(url, json={"to": "supervised"}, headers=team["mentor"]).json()
    assert signed["status"] == "supervised" and signed["tau"] is not None
    assert client.post(url, json={"to": "autonomous"}, headers=team["manager"]).json()["detail"].startswith("0 supervised cases")

    # Supervised practice: the agent drafts; the mentor approves in one tap.
    items = live_items(70)
    push(team, {"items": items})
    drain(session)
    drafts = client.get(f"/supervised?task_type_id={team['tt']}", headers=team["mentor"]).json()
    hard = [i for i in items if "approval limit" in i["inputs"]["invoice_text"]]
    assert len(drafts) == len(items) - len(hard)  # over-limit invoices are always handed back
    handbacks = client.get(f"/handbacks?task_type_id={team['tt']}", headers=team["mentor"]).json()
    assert len(handbacks) == len(hard) and all(any("always hand back" in r for r in h["reasons"]) for h in handbacks)
    for d in drafts:
        assert client.post(f"/supervised/{d['prediction_id']}/approve", json={}, headers=team["mentor"]).json()["untouched"]
    blocked = session.scalars(select(ActionLog).where(ActionLog.status == "blocked")).all()
    assert blocked and all(b.action == "set_field" for b in blocked)  # this task type doesn't allow set_field

    # Autonomy: needs 50+ supervised cases, the manager's signature, and the bar still met.
    assert client.post(url, json={"to": "autonomous"}, headers=team["mentor"]).status_code == 403
    auto = client.post(url, json={"to": "autonomous"}, headers=team["manager"]).json()
    assert auto.get("status") == "autonomous", auto

    items = live_items(40)
    push(team, {"items": items})
    drain(session)
    executed = session.scalars(select(ActionLog).where(ActionLog.mode == "autonomous", ActionLog.status == "executed")).all()
    assert executed and {a.action for a in executed} <= {"set_status", "draft_reply"}
    audits = client.get(f"/audits?task_type_id={team['tt']}", headers=team["mentor"]).json()
    assert audits and all(set(a) == {"audit_id", "case"} for a in audits)  # blind: no agent answer
    digest = client.get(f"/autonomy/digest?task_type_id={team['tt']}", headers=team["manager"]).json()
    assert digest["cases_handled"] > 0 and "recent" not in digest

    # A passing audit keeps the stage.
    a = audits[0]
    case = session.get(Case, a["case"]["id"])
    from tests.graduation_fixtures import answer
    right = answer({"subject": case.snapshot["subject"], "inputs": case.snapshot["inputs"]})
    res = client.post(f"/audits/{a['audit_id']}", json={"decision": right["decision"], "fields": right["fields"]}, headers=team["mentor"]).json()
    assert res["result"] == "pass" and session.get(TaskType, team["tt"]).status == "autonomous"

    # The track record, as JSON and PDF.
    record = client.get(f"/task-types/{team['tt']}/track-record", headers=team["manager"]).json()
    assert record["status"] == "autonomous" and set(record["signoffs"]) == {"mentor", "manager"}
    assert record["cases"]["live"] >= 50 and record["error_upper_bound_95"] <= 0.02 and record["audits"]["passed"] == 1
    pdf = client.get(f"/task-types/{team['tt']}/track-record.pdf", headers=team["manager"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"


def _graduate(team, session, client, to="supervised"):
    _shadow_to_eligible(team, session)
    assert client.post(f"/task-types/{team['tt']}/graduate", json={"to": "supervised"}, headers=team["mentor"]).status_code == 200
    return session.get(TaskType, team["tt"])


def test_audit_rules_demote_to_supervised_then_shadow(team, session, client):
    tt = _graduate(team, session, client)
    grad = engine.last_graduation(session, tt)
    grad.evidence = {**grad.evidence, "n_above": 150, "errors_above": 0}  # graduated right at the bar
    tt.status = "autonomous"
    session.commit()
    case_ids = session.scalars(select(Case.id).where(Case.task_type_id == tt.id).limit(60)).all()
    now = utcnow()
    for i in range(49):  # 46 passes, 3 fails spread through them
        session.add(Audit(case_id=case_ids[i], task_type_id=tt.id, result="fail" if i in (10, 25, 40) else "pass",
                          completed_at=now + timedelta(seconds=i)))
    session.commit()
    out = engine.review(session, tt)
    # 3 in 49 isn't proof of >2% (lower bound 1.7%), but 150 + 49 cases with 3 errors no longer clears 2%.
    assert out["lower_recent"] < 0.02 < out["upper"] and out["demoted_to"] == "supervised"

    tt.status = "autonomous"
    session.add(Audit(case_id=case_ids[50], task_type_id=tt.id, result="fail", completed_at=now + timedelta(seconds=60)))
    session.commit()
    out = engine.review(session, tt)
    assert out["lower_recent"] > 0.02 and out["demoted_to"] == "shadow"  # four errors in the last 50 audits
    assert session.get(TaskType, tt.id).status == "demoted"


def test_drift_sends_a_graduated_task_back_to_shadow(team, session, client):
    tt = _graduate(team, session, client)
    weird = live_items(25, text="Quarterly carbon offset certificate renewal for the Lisbon warehouse solar array",
                       subject="Sustainability certificate renewal")
    push(team, {"items": weird})
    drain(session)
    out = client.post(f"/task-types/{tt.id}/drift-check", headers=team["mentor"]).json()
    assert out["drifted"] and out["status"] == "demoted", out
    assert out["result"]["recent_unfamiliar"] > out["result"]["baseline_unfamiliar"] + 0.15


def test_model_swap_recertifies_on_the_frozen_record_in_minutes(team, session, client):
    tt = _graduate(team, session, client)
    frozen = engine.frozen_case_ids(session, tt)
    assert 0 < len(frozen) <= engine.FROZEN_MAX
    swap = client.post(f"/agents/{team['agent_id']}/swap", json={"model": "pattern-agent-2", "version": "2"}, headers=team["manager"]).json()
    assert swap["reprobation_runs"] and client.post(f"/agents/{team['agent_id']}/swap", json={"model": "x", "version": "3"},
                                                      headers=team["mentor"]).status_code == 403
    started = datetime.now(timezone.utc)
    drain(session)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    run = session.get(BacktestRun, swap["reprobation_runs"][0])
    result = run.stats["reprobation"]
    assert result["passed"] and result["cases"] == len(frozen) and elapsed < 600
    assert session.get(TaskType, tt.id).status == "supervised"
    assert session.scalar(select(GraduationEvent).where(GraduationEvent.evidence["recertified"].as_boolean().is_(True))) is not None

    # A worse model fails re-probation and goes back to shadow.
    registry.set_runner_override(lambda agent: PatternAgent(model="worse", wrong_every=4))
    bad = client.post(f"/agents/{team['agent_id']}/swap", json={"model": "worse", "version": "1"}, headers=team["manager"]).json()
    drain(session)
    assert not session.get(BacktestRun, bad["reprobation_runs"][0]).stats["reprobation"]["passed"]
    assert session.get(TaskType, tt.id).status == "demoted"


def test_a_rule_change_triggers_reprobation_when_graduated(team, session, client):
    tt = _graduate(team, session, client)
    before = session.scalar(select(func.count()).select_from(BacktestRun))
    client.post("/rules", json={"task_type_id": tt.id, "text": 'When an item mentions "credit note", choose query supplier.'},
                headers=team["mentor"])
    kinds = [r.params.get("kind") for r in session.scalars(select(BacktestRun).order_by(BacktestRun.created_at))][before:]
    assert set(kinds) == {"repredict", "reprobation"}


def test_cannot_graduate_without_the_bar(team, session, client):
    backtest(team, session)
    resp = client.post(f"/task-types/{team['tt']}/graduate", json={"to": "supervised"}, headers=team["mentor"])
    assert resp.status_code == 400 and "of 50 needed" in resp.json()["detail"]


def test_board(team, session, client):
    backtest(team, session)
    rows = client.get("/board", headers=team["manager"]).json()
    row = next(r for r in rows if r["id"] == team["tt"])
    assert row["status"] == "shadow" and row["evaluation"]["cases"] == 300 and row["supervised_needed"] == 50
