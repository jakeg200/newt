"""Process replays: one clock, a director grounded in the recording, whole cases replayed end to end in a sandbox,
and processes scored against what the team did."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app import clock
from app.agents import registry
from app.eval import process
from app.models import ActionLog, Case, Job, Prediction, TaskType, utcnow
from app.sim import replay
from app.sim.scenario import build

from tests.graduation_fixtures import drain, live_items, push, setup_team

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
D = timedelta(days=1)


@pytest.fixture(autouse=True)
def _reset_runner():
    yield
    registry.set_runner_override(None)  # setup_team installs the pattern agent


# Scoring ----------------------------------------------------------------------------------------------

def team(**kw) -> process.TeamTimeline:
    base = {"received_at": T0, "decision": "query_supplier", "first_action_at": T0 + timedelta(hours=5), "replied": True,
            "chased": False, "counterparty": ()}
    return process.TeamTimeline(**{**base, **kw})


def newt(**kw) -> process.NewtTimeline:
    base = {"decision": "query_supplier", "handed_back": False, "steps_ok": True, "policy_ok": True, "replied": True,
            "done_at": T0 + timedelta(minutes=1), "chases": ()}
    return process.NewtTimeline(**{**base, **kw})


def test_chasing_is_judged_against_when_the_reply_really_came():
    late_reply = (T0 + 5 * D,)
    assert process.chase_verdict(newt(chases=(T0 + 3 * D,)), late_reply, 3) is None  # no reply by day 3: chase
    assert process.chase_verdict(newt(), late_reply, 3) == "didn't chase when no reply came"
    early_reply = (T0 + 1 * D,)
    assert process.chase_verdict(newt(), early_reply, 3) is None  # it came: nothing to chase
    assert process.chase_verdict(newt(chases=(T0 + 3 * D,)), early_reply, 3) == "chased after the reply had come"
    assert process.chase_verdict(newt(replied=False, chases=(T0 + D,)), (), None) == "chased with nothing to chase"


def test_a_process_is_like_the_team_only_when_every_part_matches():
    ok = process.score(team(counterparty=(T0 + D,)), newt(), 3)
    assert ok["verdict"] == "like_team" and ok["hours_sooner"] == 5.0
    bad = process.score(team(), newt(decision="approve", replied=False, steps_ok=False), 3)
    assert bad["verdict"] == "diverged" and len(bad["reasons"]) == 3
    assert process.score(team(), newt(handed_back=True, reasons=("over the limit",)), 3)["verdict"] == "handed_back"
    s = process.summarize([ok, bad, process.score(team(), newt(handed_back=True), 3)])
    assert s["like_team"] == 1 and s["handed_back"] == 1 and s["diverged"] == 1 and s["like_team_rate"] == 0.5
    assert s["divergences"]["a different decision"] == 1


# The clock --------------------------------------------------------------------------------------------

def test_one_clock_and_simulated_time_only_moves_forward():
    assert abs((utcnow() - datetime.now(timezone.utc)).total_seconds()) < 5
    with clock.simulated(T0) as clk:
        assert utcnow() == T0 and clock.simulating()
        assert Job(type="x", payload={}).run_at is None  # column defaults apply at insert, from the same clock
        clk.advance_to(T0 + 3 * D)
        clk.advance_to(T0)  # never backwards
        assert utcnow() == T0 + 3 * D
    assert not clock.simulating() and utcnow().year >= 2026


# Whole processes ---------------------------------------------------------------------------------------

def threaded_history(ctx, reply_after: dict[int, timedelta | None]) -> list[str]:
    """Query-supplier invoices from the past: the team decides, replies to the supplier, and the supplier's answer
    arrives in the thread after the given delay (or never)."""
    base = [i for i in live_items(80) if "units" in i["inputs"]["invoice_text"]][:len(reply_after)]
    items, actions = [], []
    for n, item in enumerate(base):
        at = T0 + n * timedelta(hours=1)
        thread = f"thread-{item['ref']}"
        items.append({**item, "received_at": at.isoformat(), "thread": thread})
        actions.append({"ref": f"{item['ref']}#d", "item_ref": item["ref"], "acted_at": (at + timedelta(hours=1)).isoformat(),
                        "decision": "query_supplier"})
        actions.append({"ref": f"{item['ref']}#r", "item_ref": item["ref"], "acted_at": (at + timedelta(hours=2)).isoformat(),
                        "kind": "reply", "text": "Hello, the quantity doesn't match the goods received. Could you check? Thank you."})
        delay = reply_after[n]
        if delay is not None:
            items.append({"ref": f"{item['ref']}-re", "received_at": (at + delay).isoformat(), "thread": thread,
                          "subject": f"Re: {item['subject']}", "sender": item["sender"],
                          "inputs": {"invoice_text": "We've corrected the quantity, please see the revised invoice.", "po_record": ""}})
    push(ctx, {"items": items, "actions": actions, "backtest": True})
    return [i["ref"] for i in base]


def test_a_scenario_is_the_recorded_timeline(client, session):
    ctx = setup_team(client, session, history=200)
    refs = threaded_history(ctx, {0: 5 * D, 1: None})
    tt = session.get(TaskType, ctx["tt"])
    cases = {c.source_ref: c for c in session.scalars(select(Case).where(Case.task_type_id == tt.id))}
    sc = build(session, tt, cases[refs[0]])
    assert sc.team.decision == "query_supplier" and sc.team.replied and sc.team.counterparty == (T0 + 5 * D,)
    assert sc.follow_up_days == 3 and sc.horizon >= T0 + 7 * D
    assert [e["what"] for e in sc.events] == ["arrived", "decided query supplier", "replied", "a reply came in the thread"]
    assert build(session, tt, cases[refs[1]]).team.counterparty == ()


def test_newt_runs_the_whole_process_and_never_sees_the_reply_early(client, session):
    ctx = setup_team(client, session, history=200)
    refs = threaded_history(ctx, {0: 5 * D, 1: 1 * D})  # slow supplier, quick supplier
    tt = session.get(TaskType, ctx["tt"])
    before = {m: session.scalar(select(func.count()).select_from(m)) for m in (ActionLog, Prediction, Job)}
    statuses = {c.id: c.status for c in session.scalars(select(Case))}

    r = client.post(f"/task-types/{tt.id}/process-replays", json={"limit": 2}, headers=ctx["mentor"])
    assert r.status_code == 201, r.text
    drain(session)
    out = client.get(f"/task-types/{tt.id}/process-replays/latest", headers=ctx["mentor"]).json()
    assert out["status"] == "done", out["error"]
    by_ref = {res["subject"]: res for res in out["results"]}
    subjects = {c.source_ref: (c.snapshot or {}).get("subject") for c in session.scalars(select(Case))}
    slow, quick = by_ref[subjects[refs[0]]], by_ref[subjects[refs[1]]]

    def newt_did(res):
        return [(e["day"], e["what"]) for e in res["timeline"] if e["who"] == "newt"]

    # Slow supplier: at day 3 the day-5 reply hasn't happened yet, so Newt chases; it never sees the future early.
    assert any(what == "chased" and 2.9 <= day <= 3.1 for day, what in newt_did(slow)), newt_did(slow)
    assert slow["verdict"] == "like_team", slow["reasons"]
    # Quick supplier: the reply came on day 1, so the day-3 follow-up sees it and doesn't chase.
    assert not any(what == "chased" for _, what in newt_did(quick)) and quick["verdict"] == "like_team", quick["reasons"]
    assert out["summary"]["like_team"] == 2 and out["simulated_days"] > 10

    # The sandbox was rolled back: no predictions, actions or jobs left behind, and no case changed.
    after = {m: session.scalar(select(func.count()).select_from(m)) for m in (ActionLog, Prediction, Job)}
    assert after[ActionLog] == before[ActionLog] and after[Prediction] == before[Prediction]
    assert after[Job] == before[Job] + 1  # only the replay's own job
    session.expire_all()
    assert {c.id: c.status for c in session.scalars(select(Case))} == statuses


def test_replay_results_show_cases_only_to_mentors(client, session):
    ctx = setup_team(client, session, history=200)
    threaded_history(ctx, {0: 2 * D})
    client.post(f"/task-types/{ctx['tt']}/process-replays", json={"limit": 1}, headers=ctx["manager"])
    drain(session)
    as_manager = client.get(f"/task-types/{ctx['tt']}/process-replays/latest", headers=ctx["manager"]).json()
    assert as_manager["status"] == "done" and as_manager["results"] is None and as_manager["summary"]["cases"] == 1
    assert client.get(f"/task-types/{ctx['tt']}/process-replays/latest", headers=ctx["mentor"]).json()["results"]
    assert replay.latest(session, session.get(TaskType, ctx["tt"])) is not None
    listed = client.get(f"/backtests?task_type_id={ctx['tt']}", headers=ctx["mentor"]).json()
    assert all(b["id"] != as_manager["id"] for b in listed)
