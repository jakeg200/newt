"""M4 acceptance: a lesson takes under 3 seconds; judge-vs-mentor agreement is shown; editing a
rule re-predicts the backlog and shows how many cases changed."""

import time
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agents.context import ContextBuilder, LeakageError, Piece, check
from app.eval.judge import LLMJudge, SimilarityJudge, judge_outputs
from app.learning.rules import infer_offline, parse
from app.llm.provider import FakeProvider
from app.models import BacktestRun, Case, Comparison, Prediction, Rule, TaskType, User
from app.seed import seed
from app.task_types import TaskTypeConfig
from app.worker import run_once

from tests.backtest_fixtures import COLUMNS, ledger_csv, ledger_rows


@pytest.fixture
def taught(client, session):
    """360 decided invoices captured, and a 300-case backtest with the offline agent and judge."""
    seed(session)
    mentor = session.scalar(select(User).where(User.email == "mentor+invoice_mismatch@synthetic.test"))
    manager = session.scalar(select(User).where(User.role == "manager"))
    h = {"X-Dev-User": mentor.id}
    tt = next(t for t in client.get("/task-types", headers=h).json() if t["team"] == "invoice_mismatch")
    conn = client.post("/connections", json={"name": "Ledger", "provider": "csv", "task_type_id": tt["id"], "columns": COLUMNS}, headers=h).json()
    client.post(f"/connections/{conn['id']}/import", files=[("files", ("l.csv", ledger_csv(ledger_rows())))], headers=h)
    run = client.post("/backtests", json={"task_type_id": tt["id"], "limit": 300}, headers=h).json()
    assert run_once(session)
    return {"mentor": h, "manager": {"X-Dev-User": manager.id}, "tt": tt["id"], "run": run["id"]}


def _queue(client, ctx, limit=20):
    return client.get(f"/teaching/queue?task_type_id={ctx['tt']}&limit={limit}", headers=ctx["mentor"]).json()


def test_replies_are_judged_where_the_decision_matched(client, session, taught):
    stats = client.get(f"/backtests/{taught['run']}", headers=taught["mentor"]).json()["stats"]
    assert stats["text_judged"] > 50 and stats["text_acceptable"] <= stats["text_judged"]
    skipped = session.scalars(select(Comparison).where(Comparison.decision_match.is_(False))).all()
    assert all(c.text_judgement.get("status") in (None, "skipped") for c in skipped)


def test_queue_holds_only_what_needs_the_mentor(client, session, taught):
    q = _queue(client, taught, limit=100)
    comps = session.scalars(select(Comparison).join(Prediction).where(Prediction.run_id == taught["run"])).all()
    disagreements = sum(1 for c in comps if not c.agreement)
    assert q["by_kind"]["disagreement"] == disagreements
    assert q["total"] < len(comps) / 3  # agreements are counted, not reviewed
    card = q["cards"][0]
    assert card["kind"] == "disagreement"
    assert card["mentor"]["decision"] and card["agent"]["decision"] and "field_scores" in card["comparison"]


def test_lesson_takes_under_three_seconds_and_rescores(client, session, taught):
    before = client.get(f"/teaching/summary?task_type_id={taught['tt']}", headers=taught["mentor"]).json()
    card = _queue(client, taught)["cards"][0]
    started = time.monotonic()
    resp = client.post("/lessons", json={"prediction_id": card["prediction_id"], "attribution": "both_fine",
                                         "note": "Either is fine for this supplier."}, headers=taught["mentor"])
    wall_ms = (time.monotonic() - started) * 1000
    assert resp.status_code == 201 and wall_ms < 3000 and resp.json()["elapsed_ms"] < 3000
    assert "agreement" in resp.json()["effect"]
    assert card["prediction_id"] not in [c["prediction_id"] for c in _queue(client, taught, limit=100)["cards"]]

    after = client.get(f"/teaching/summary?task_type_id={taught['tt']}", headers=taught["mentor"]).json()
    assert after["agreement"] > before["agreement"] and after["lessons"] == 1
    assert after["queue"] == before["queue"] - 1

    nxt = _queue(client, taught)["cards"][0]
    client.post("/lessons", json={"prediction_id": nxt["prediction_id"], "attribution": "mentor_changed"}, headers=taught["mentor"])
    comp = session.scalar(select(Comparison).where(Comparison.prediction_id == nxt["prediction_id"]))
    session.refresh(comp)
    assert comp.excluded and comp.effective_agreement is None
    final = client.get(f"/teaching/summary?task_type_id={taught['tt']}", headers=taught["mentor"]).json()
    assert final["excluded"] == 1 and final["by_attribution"] == {"both_fine": 1, "mentor_changed": 1}


def test_judge_agreement_is_measured_on_lessons(client, session, taught):
    judged = session.scalars(select(Comparison).join(Prediction).where(Prediction.run_id == taught["run"])).all()
    judged = [c for c in judged if c.text_judgement.get("status") == "judged"][:20]
    assert len(judged) == 20
    for i, comp in enumerate(judged):
        reply_ok = comp.text_judgement["acceptable"] if i else not comp.text_judgement["acceptable"]  # one disagreement
        client.post("/lessons", json={"prediction_id": comp.prediction_id, "attribution": "both_fine" if reply_ok else "intern_wrong",
                                      "reply_ok": reply_ok}, headers=taught["mentor"])
        if i == 18:
            j = client.get(f"/teaching/summary?task_type_id={taught['tt']}", headers=taught["mentor"]).json()["judge"]
            assert j["compared"] == 19 and not j["trusted"]  # not enough lessons yet
    judge = client.get(f"/teaching/summary?task_type_id={taught['tt']}", headers=taught["manager"]).json()["judge"]
    assert judge == {"compared": 20, "agree": 19, "rate": 0.95, "judge": "offline-similarity", "trusted": True,
                     "trust_bar": {"rate": 0.9, "min_lessons": 20}}


def test_rule_edit_repredicts_backlog_and_counts_changes(client, session, taught):
    proposed = client.post("/rules/infer", json={"task_type_id": taught["tt"]}, headers=taught["mentor"]).json()
    texts = {r["text"]: r for r in proposed}
    limit_rule = next(r for t, r in texts.items() if "approval limit" in t)
    assert limit_rule["decision"] == "escalate" and limit_rule["status"] == "proposed" and limit_rule["examples"] > 0

    accepted = client.patch(f"/rules/{limit_rule['id']}", json={"status": "active"}, headers=taught["mentor"]).json()
    assert accepted["repredict_run_id"] and run_once(session)
    first = session.get(BacktestRun, accepted["repredict_run_id"])
    assert first.status == "done" and first.params["kind"] == "repredict" and len(first.params["case_ids"]) == 50

    edited = client.patch(f"/rules/{limit_rule['id']}", json={
        "text": 'When an item mentions "approval limit", choose query supplier.'}, headers=taught["mentor"]).json()
    assert edited["decision"] == "query_supplier" and edited["source"] == "mentor" and edited["version"] == 2
    assert run_once(session)
    run = session.get(BacktestRun, edited["repredict_run_id"])
    backlog = session.scalars(select(Case).where(Case.id.in_(run.params["case_ids"]))).all()
    mention = [c for c in backlog if "approval limit" in c.snapshot["inputs"]["invoice_text"]
               and c.id not in (session.get(Rule, limit_rule["id"]).supporting_case_ids or [])]
    assert run.stats["changed"] == len(mention) > 0
    assert all(ch["after"] == "query_supplier" for ch in run.stats["changes"])

    summary = client.get(f"/teaching/summary?task_type_id={taught['tt']}", headers=taught["mentor"]).json()
    assert summary["latest_repredict"]["changed"] == len(mention)
    assert summary["rules"]["active"] == 1
    newest = session.scalars(select(Prediction).where(Prediction.run_id == run.id)).first()
    assert newest.rules_version == 2  # accepted, then edited


def test_retiring_a_rule_also_repredicts(client, session, taught):
    rule = client.post("/rules", json={"task_type_id": taught["tt"], "text": 'When an item mentions "units", choose escalate.'},
                       headers=taught["mentor"]).json()
    assert rule["status"] == "active" and rule["repredict_run_id"]
    run_once(session)
    retired = client.patch(f"/rules/{rule['id']}", json={"status": "retired"}, headers=taught["mentor"]).json()
    assert retired["repredict_run_id"]
    run_once(session)
    assert session.get(BacktestRun, retired["repredict_run_id"]).stats["changed"] > 0


def test_lesson_can_carry_a_new_rule(client, session, taught):
    card = _queue(client, taught)["cards"][0]
    resp = client.post("/lessons", json={"prediction_id": card["prediction_id"], "attribution": "couldnt_know",
                                         "rule_text": 'When an item mentions "credit note", choose query supplier.'},
                       headers=taught["mentor"]).json()
    assert resp["repredict_run_id"] and "rule is active" in resp["effect"]
    rule = session.scalar(select(Rule).where(Rule.source == "mentor"))
    assert rule.supporting_case_ids == [card["case"]["id"]]  # never applied to the case it came from


# Rules: inference, interpretation, no leaks -----------------------------------------------

def test_offline_inference_finds_the_mentors_patterns(session, taught):
    builder = ContextBuilder(session, session.get(TaskType, taught["tt"]))
    proposals = {p.text: p for p in infer_offline(list(builder.decided.values()), builder.task)}
    joined = " | ".join(proposals)
    assert '"price variance", choose approve' in joined
    assert '"goods received", choose query supplier' in joined
    assert '"approval limit", choose escalate' in joined
    for p in proposals.values():
        assert p.stats["precision"] >= 0.9 and p.examples and p.evidence_until


def test_rule_parser():
    task = TaskTypeConfig.model_validate({"name": "t", "trigger": "x", "inputs": ["a"], "decision": ["approve", "query_supplier", "escalate"],
                                          "alpha": 0.02, "min_cases": 1})
    r = parse('When an item mentions "approval limit", choose query supplier.', task)
    assert r.decision == "query_supplier" and r.phrases == ["approval limit"]
    assert r.matches("Invoice total £8,000 is above the £5,000 approval limit") and not r.matches("Price variance")
    free = parse("Escalate anything from a key account supplier", task)
    assert free.decision == "escalate" and free.matches("Invoice from our key account supplier Northwind")
    assert parse("Be nice to suppliers", task).decision is None


def test_rules_never_leak_into_backtests(client, session, taught):
    client.post("/rules/infer", json={"task_type_id": taught["tt"]}, headers=taught["mentor"])
    for r in session.scalars(select(Rule)):
        r.status = "active"
    session.commit()
    builder = ContextBuilder(session, session.get(TaskType, taught["tt"]))
    for case in session.scalars(select(Case).where(Case.connection_id.is_not(None))):
        ctx = builder.build(case)
        check(ctx, builder.forbidden(case))  # inferred rules appear only after their evidence existed
        for p in ctx.of("rule"):
            assert case.id not in p.content["supporting_case_ids"]
    early = min(session.scalars(select(Case).where(Case.connection_id.is_not(None))), key=lambda c: c.received_at)
    ctx = builder.build(early)
    assert ctx.of("rule") == []
    rule = session.scalars(select(Rule)).first()
    ctx.pieces.append(Piece("rule", rule.id, None, {"text": rule.text, "source": "inferred", "supporting_case_ids": [],
                                                     "evidence_until": (ctx.as_of + timedelta(days=1)).isoformat()}))
    with pytest.raises(LeakageError, match="after the item arrived"):
        check(ctx, [])


# Judge -------------------------------------------------------------------------------------

def test_judges():
    sim = SimilarityJudge()
    good = sim.judge(item={}, output_name="email", mentor_text="Please send a credit note for invoice INV-1",
                     agent_text="Please send a credit note for invoice INV-2")
    bad = sim.judge(item={}, output_name="email", mentor_text="Please send a credit note", agent_text="We have paid the invoice today")
    assert good.acceptable and not bad.acceptable
    out = judge_outputs(sim, {}, {"email": "Please send a credit note"}, {}, ["email"])
    assert out["outputs"]["email"]["verdict"] == "missing" and not out["acceptable"]

    provider = FakeProvider({"judge": lambda *a: {"verdict": "needs_changes", "reasons": ["wrong amount"]}})
    v = LLMJudge(provider).judge(item={"subject": "x"}, output_name="email", mentor_text="a", agent_text="b")
    assert v.verdict == "needs_changes" and not v.acceptable and provider.calls[0]["cache_system"]


def test_permissions(client, taught):
    assert client.get(f"/teaching/queue?task_type_id={taught['tt']}", headers=taught["manager"]).status_code == 403
    assert client.get(f"/rules?task_type_id={taught['tt']}", headers=taught["manager"]).status_code == 403
    assert client.get(f"/teaching/summary?task_type_id={taught['tt']}", headers=taught["manager"]).status_code == 200
