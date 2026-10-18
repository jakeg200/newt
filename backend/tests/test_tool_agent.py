"""A capable Newt: tools that respect the time window, multi-step trajectories, stricter scoring of how an answer was
reached, and replay of live lookups from recordings."""

import pytest
from sqlalchemy import select

from app.agents import registry
from app.agents.context import ContextBuilder, utc
from app.agents.offline import NearestCasesAgent
from app.agents.replay import recording_of, recordings_for
from app.agents.tool_agent import MAX_STEPS, ToolApprentice, WorkbenchPlanner
from app.agents.workbench import safe_eval
from app.eval.score import step_checks
from app.llm.provider import FakeProvider
from app.models import Case, Comparison, Prediction, TaskType
from app.task_types import TaskTypeConfig

from tests.graduation_fixtures import backtest, drain, live_items, push, setup_team


@pytest.fixture
def team(client, session):
    ctx = setup_team(client, session)
    yield ctx
    registry.set_runner_override(None)


def history_cases(session, tt_id):
    return sorted(session.scalars(select(Case).where(Case.task_type_id == tt_id, Case.is_backtest.is_(True))), key=lambda c: utc(c.received_at))


def test_tools_only_see_the_past(team, session):
    tt = session.get(TaskType, team["tt"])
    cases = history_cases(session, tt.id)
    mid = cases[len(cases) // 2]
    builder = ContextBuilder(session, tt)
    builder.enable_tools(live=False)
    wb = builder.build(mid).workbench
    found = wb.call("search_past_cases", {"query": wb.item_text, "k": 10})["cases"]
    later = {c.source_ref for c in cases if utc(c.received_at) >= utc(mid.received_at)}
    assert found and not ({f["ref"] for f in found} & later)  # nothing from after the item arrived
    assert wb.call("get_case", {"ref": cases[-1].source_ref})["found"] is False
    assert wb.call("get_case", {"ref": cases[0].source_ref})["found"] is True
    assert wb.call("lookup_record", {"kind": "purchase_order", "ref": "PO-1"})["source"] == "unavailable"  # never the live system
    assert wb.call("get_kitten", {})["error"]
    assert [s["tool"] for s in wb.steps] == ["search_past_cases", "get_case", "get_case", "lookup_record", "get_kitten"]


def test_live_lookups_are_redacted_and_recorded(team, session):
    tt = session.get(TaskType, team["tt"])
    case = history_cases(session, tt.id)[-1]
    builder = ContextBuilder(session, tt)
    builder.enable_tools(live=True, lookup=lambda kind, ref: {"ref": ref, "status": "open", "contact": "ap@supplier.example", "amount": 412.5})
    wb = builder.build(case).workbench
    out = wb.call("lookup_record", {"kind": "purchase_order", "ref": "PO-7"})
    assert out["source"] == "system" and "ap@supplier.example" not in str(out) and out["record"]["amount"] == 412.5
    assert recording_of(wb.steps) == {"purchase_order:PO-7": out["record"]}


def test_calculate_is_arithmetic_only():
    assert safe_eval("412.50 * 2 - 25") == 800.0
    for bad in ("__import__('os')", "a + 1", "9 ** 99"):
        with pytest.raises(ValueError):
            safe_eval(bad)


def test_offline_planner_works_the_case(team, session):
    tt = session.get(TaskType, team["tt"])
    case = next(c for c in reversed(history_cases(session, tt.id)) if (c.snapshot or {}).get("inputs", {}).get("po_record"))
    builder = ContextBuilder(session, tt)
    builder.enable_tools(live=False)
    r = WorkbenchPlanner(NearestCasesAgent()).predict(builder.build(case))
    assert [s["tool"] for s in r.trajectory] == ["search_past_cases", "lookup_record", "check_rule", "propose"]
    assert r.output and r.output["decision"] in TaskTypeConfig.model_validate(tt.config).decision


def _scripted(plan):
    """A model that follows a script: each turn returns the next list of tool calls."""
    def respond(messages):
        turn = sum(1 for m in messages if m["role"] == "assistant")
        return plan[turn] if turn < len(plan) else plan[-1]
    return FakeProvider(tool_responders={"work the case": respond})


def test_tool_loop_and_step_limit(team, session):
    tt = session.get(TaskType, team["tt"])
    case = history_cases(session, tt.id)[-1]
    builder = ContextBuilder(session, tt)
    builder.enable_tools(live=False)
    answer = {"decision": "escalate", "fields": {"variance_reason": "other", "gl_code": "6400"}, "text_outputs": {}, "rationale": "x",
              "missing_info": [], "self_reported_confidence": 0.8}
    agent = ToolApprentice(_scripted([[{"name": "search_past_cases", "input": {"query": "invoice"}}],
                                      [{"name": "check_rule", "input": {"text": "above limit"}}], [{"name": "propose", "input": answer}]]),
                           fallback=NearestCasesAgent())
    r = agent.predict(builder.build(case))
    assert r.output["decision"] == "escalate" and [s["tool"] for s in r.trajectory] == ["search_past_cases", "check_rule", "propose"]
    endless = ToolApprentice(_scripted([[{"name": "search_past_cases", "input": {"query": "x"}}]]), fallback=NearestCasesAgent())
    r = endless.predict(builder.build(case))
    assert r.output is None and "never gave an answer" in r.error and len(r.trajectory) == MAX_STEPS


def test_step_checks():
    task = TaskTypeConfig.model_validate({
        "name": "t", "trigger": "x", "inputs": ["a", "po"], "decision": ["approve", "escalate"], "alpha": 0.02, "min_cases": 10,
        "tools": ["search_past_cases", "lookup_record"], "lookups": [{"input": "po", "kind": "purchase_order"}],
        "required_steps": {"approve": ["lookup_record"]}})
    assert step_checks(task, None, "approve") == {"checked": False, "ok": True}
    lucky = [{"tool": "search_past_cases"}, {"tool": "propose"}]
    assert step_checks(task, lucky, "approve")["missing"] == ["lookup_record"]
    assert step_checks(task, lucky, "escalate")["ok"]
    assert step_checks(task, [{"tool": "send_money"}], "escalate")["disallowed"] == ["send_money"]


def test_right_answer_without_evidence_is_not_agreement(team, session):
    """An agent that approves without looking up the purchase order doesn't earn agreement, even when right."""
    def careless(messages):
        return [{"name": "propose", "input": {"decision": "approve", "fields": {"variance_reason": "price", "gl_code": "6400"},
                                              "text_outputs": {}, "rationale": "", "missing_info": [], "self_reported_confidence": 0.9}}]
    registry.set_runner_override(lambda agent: ToolApprentice(FakeProvider(tool_responders={"work the case": careless}), fallback=NearestCasesAgent()))
    run = backtest(team, session, limit=60)
    assert run["status"] == "done"
    comps = session.scalars(select(Comparison).join(Prediction).where(Prediction.run_id == run["id"])).all()
    lucky = [c for c in comps if c.decision_match and c.steps.get("checked")]
    assert lucky and all(not c.agreement and c.steps["missing"] == ["lookup_record"] for c in lucky)


def test_replay_answers_lookups_from_recordings(team, session):
    """A live lookup is recorded; replaying the same case answers from the recording, not the live system."""
    tt = session.get(TaskType, team["tt"])
    tt.status = "shadow"
    session.commit()
    registry.set_runner_override(lambda agent: WorkbenchPlanner(NearestCasesAgent()))
    from app.execution import executor

    asked = []
    original = executor.lookup_via
    executor.lookup_via = lambda s, t: (lambda kind, ref: asked.append(ref) or {"ref": ref, "status": "open", "amount": 100.0})
    try:
        push(team, {"items": live_items(3)})
        drain(session)
    finally:
        executor.lookup_via = original
    live = [p for p in session.scalars(select(Prediction).where(Prediction.run_id.is_(None))) if p.trajectory]
    assert live and asked
    rec = recordings_for(session, [p.case_id for p in live])
    case = session.get(Case, next(cid for cid, r in rec.items() if r))
    builder = ContextBuilder(session, tt)
    builder.enable_tools(live=False, recordings=rec)
    wb = builder.build(case).workbench
    key = next(iter(rec[case.id]))
    kind, ref = key.split(":", 1)
    assert wb.call("lookup_record", {"kind": kind, "ref": ref})["source"] == "recorded"
    assert wb.call("lookup_record", {"kind": kind, "ref": "NEVER-SEEN"})["source"] == "unavailable"
