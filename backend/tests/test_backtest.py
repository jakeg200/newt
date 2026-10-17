"""M3 acceptance: a 300-case backtest in under 30 minutes with cost reported; the leakage test
fails on injected future data; a mock external agent runs through the same scoring."""

import hashlib
import hmac
import json
import re
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app import crypto
from app.agents import registry
from app.agents.builtin import BuiltinApprentice, aggregate
from app.agents.context import ContextBuilder, LeakageError, Piece, check
from app.agents.external import EndpointError, ExternalAgent, check_endpoint
from app.llm.provider import FakeProvider
from app.models import Agent, BacktestRun, Case, Comparison, Job, Prediction, TaskType, User
from app.seed import seed
from app.worker import claim, run_once

from tests.backtest_fixtures import COLUMNS, SUPPLIERS, ledger_csv, ledger_rows


@pytest.fixture
def history(client, session):
    seed(session)
    mentor = session.scalar(select(User).where(User.email == "mentor+invoice_mismatch@synthetic.test"))
    manager = session.scalar(select(User).where(User.role == "manager"))
    h = {"X-Dev-User": mentor.id}
    tt = next(t for t in client.get("/task-types", headers=h).json() if t["team"] == "invoice_mismatch")
    conn = client.post("/connections", json={"name": "Ledger", "provider": "csv", "task_type_id": tt["id"],
                                             "columns": COLUMNS}, headers=h).json()
    run = client.post(f"/connections/{conn['id']}/import", files=[("files", ("ledger.csv", ledger_csv(ledger_rows())))],
                      headers=h).json()
    assert run["stats"]["cases_created"] == 360 and run["stats"]["actions_matched"] == 360
    yield {"mentor": h, "manager": {"X-Dev-User": manager.id}, "tt": tt["id"]}
    registry.set_runner_override(None)


def _run(client, session, history, **body):
    resp = client.post("/backtests", json={"task_type_id": history["tt"], **body}, headers=history["mentor"])
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "queued"
    assert run_once(session)  # the worker picks up the job
    return client.get(f"/backtests/{resp.json()['id']}", headers=history["mentor"]).json()


def test_300_case_backtest_with_cost_reported(client, session, history):
    est = client.get(f"/backtests/estimate?task_type_id={history['tt']}&limit=300", headers=history["mentor"]).json()
    assert est["cases_available"] == 360 and est["cases"] == 300 and "est_cost_usd" in est

    run = _run(client, session, history, limit=300)
    stats = run["stats"]
    assert run["status"] == "done", run["error"]
    assert stats["cases"] == 300 and run["progress"] == {"done": 300, "total": 300}
    assert stats["duration_s"] < 30 * 60
    assert "cost_usd" in stats and run["cost_usd"] == stats["cost_usd"]  # reported (0 for the offline baseline)
    assert stats["agreement_rate"] > 0.75  # the history has structure; nearest cases find it
    assert set(stats["confusion"]) <= {"approve", "query_supplier", "escalate"}
    assert stats["fields"]["variance_reason"]["cases"] > 0
    assert session.scalar(select(func.count()).select_from(Prediction).where(Prediction.run_id == run["id"])) == 300
    # The 300 most recent of 360: the 60 earliest are history the agent can learn from, never predicted.
    predicted = {p.case_id for p in session.scalars(select(Prediction).where(Prediction.run_id == run["id"]))}
    earliest = session.scalars(select(Case).where(Case.connection_id.is_not(None)).order_by(Case.received_at).limit(60))
    assert not predicted & {c.id for c in earliest}


def _keyword_answer(item: dict) -> dict:
    """A rule-following agent: right on the pattern, wrong on the mentor's ~5% exceptions."""
    text = item["inputs"]["invoice_text"]
    if "units" in text:
        decision, reason = "query_supplier", "quantity"
    elif "purchase order" in text:
        decision, reason = "escalate", "missing_po"
    elif "approval limit" in text:
        decision, reason = "escalate", "other"
    elif "duplicate" in text:
        decision, reason = "query_supplier", "duplicate"
    else:
        decision, reason = "approve", "price"
    gl = next(code for name, code in SUPPLIERS if item["subject"].startswith(name))
    return {"decision": decision, "fields": {"variance_reason": reason, "gl_code": gl}}


def test_builtin_apprentice_uses_cached_handbook_prompt_and_self_consistency(client, session, history):
    calls = []

    def respond(task, system, user, schema):
        item = json.loads(user.split("<item>")[1].split("</item>")[0])
        calls.append(item["inputs"]["invoice_text"])
        return {**_keyword_answer(item), "text_outputs": {"supplier_email": ""}, "rationale": "pattern",
                "missing_info": [], "self_reported_confidence": 0.8}

    provider = FakeProvider({"prediction": respond})
    registry.set_runner_override(lambda agent: BuiltinApprentice(provider, samples=3))
    run = _run(client, session, history, limit=30)
    assert run["status"] == "done", run["error"]
    assert len(provider.calls) == 90  # 30 cases × 3 samples
    assert all(c["cache_system"] for c in provider.calls)
    assert len({c["system"] for c in provider.calls}) == 1  # identical system prompt, so it caches
    assert "<similar_past_cases>" in provider.calls[0]["user"]
    assert run["stats"]["agreement_rate"] > 0.85
    assert run["stats"]["confidence_buckets"][0]["cases"] == 30  # all three samples agreed


def test_majority_vote_sets_confidence():
    chosen, confidence, decisions = aggregate([{"decision": "a", "fields": {"x": 1}}, {"decision": "b"}, {"decision": "a", "fields": {"x": 2}}])
    assert chosen["fields"] == {"x": 1} and confidence == pytest.approx(2 / 3) and decisions == ["a", "b", "a"]


# Time-travel guard -------------------------------------------------------------------------

def test_leakage_fails_the_run_on_injected_future_data(client, session, history, monkeypatch):
    original = ContextBuilder.build

    def leaky(self, case):
        ctx = original(self, case)
        later = max(self.decided.values(), key=lambda d: d.decided_at)  # decided after almost everything
        ctx.pieces.append(Piece("similar_case", later.case.id, later.decided_at, {"mentor_decision": later.decision}))
        return ctx

    monkeypatch.setattr(ContextBuilder, "build", leaky)
    run = _run(client, session, history, limit=20)
    assert run["status"] == "failed" and "Time-travel guard" in run["error"]
    assert session.scalar(select(func.count()).select_from(Prediction).where(Prediction.run_id == run["id"])) == 0


def test_leakage_fails_when_the_mentors_own_reply_is_in_the_item(client, session, history, monkeypatch):
    original = ContextBuilder.build

    def leaky(self, case):
        ctx = original(self, case)
        mentor = self.mentor_decision(case)
        if mentor and mentor.text_outputs:
            ctx.of("item")[0].content["inputs"]["invoice_text"] += " " + next(iter(mentor.text_outputs.values()))
        return ctx

    monkeypatch.setattr(ContextBuilder, "build", leaky)
    run = _run(client, session, history, limit=60)
    assert run["status"] == "failed" and "own response" in run["error"]


def test_real_contexts_pass_the_guard(session, history):
    tt = session.get(TaskType, history["tt"])
    builder = ContextBuilder(session, tt)
    cases = session.scalars(select(Case).where(Case.task_type_id == tt.id, Case.connection_id.is_not(None))).all()
    for case in cases:
        ctx = builder.build(case)
        check(ctx, builder.forbidden(case))
        assert all(p.observed_at < ctx.as_of for p in ctx.of("similar_case"))
    first = min(cases, key=lambda c: c.received_at)
    assert builder.build(first).of("similar_case") == []  # nothing was decided before the first item


def test_guard_rejects_each_kind_of_leak(session, history):
    tt = session.get(TaskType, history["tt"])
    builder = ContextBuilder(session, tt)
    case = session.scalars(select(Case).where(Case.connection_id.is_not(None)).order_by(Case.received_at.desc())).first()
    ctx = builder.build(case)
    check(ctx, builder.forbidden(case))

    ctx.pieces.append(Piece("history", case.id, ctx.as_of + timedelta(seconds=1), {"text": "later"}))
    with pytest.raises(LeakageError, match="after the item arrived"):
        check(ctx, [])
    ctx.pieces.pop()
    ctx.pieces.append(Piece("similar_case", case.id, ctx.as_of - timedelta(days=1), {}))
    with pytest.raises(LeakageError, match="its own similar cases"):
        check(ctx, [])
    ctx.pieces.pop()
    ctx.pieces.append(Piece("rule", "r1", None, {"text": "x", "supporting_case_ids": [case.id]}))
    with pytest.raises(LeakageError, match="learned from this very case"):
        check(ctx, [])


# External agents ---------------------------------------------------------------------------

def test_external_agent_runs_through_the_same_scoring(client, session, history):
    created = client.post("/agents", json={"name": "Vendor AP agent", "endpoint": "http://localhost:8100/predict",
                                           "version": "2.3.1", "model": "vendor-model"}, headers=history["mentor"]).json()
    secret = created["signing_secret"]
    assert client.get("/agents", headers=history["mentor"]).json()[-1].get("signing_secret") is None
    agent = session.get(Agent, created["id"])
    assert secret not in json.dumps(agent.config)  # stored encrypted

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        expected = "sha256=" + hmac.new(secret.encode(), request.content, hashlib.sha256).hexdigest()
        assert request.headers["X-Agent-Onboarding-Signature"] == expected
        body = json.loads(request.content)
        assert set(body) >= {"item", "handbook", "similar_cases", "task_type", "response_schema"}
        seen.append(body["case_id"])
        if len(seen) % 10 == 0:
            return httpx.Response(500)  # a flaky vendor: those cases are handed back, never agreements
        return httpx.Response(200, json={**_keyword_answer(body["item"]), "rationale": "rules",
                                         "self_reported_confidence": 0.9})

    mock = httpx.Client(transport=httpx.MockTransport(handler))
    registry.set_runner_override(
        lambda a: ExternalAgent(a.endpoint, crypto.decrypt(a.config["secret"]), a.model, http=mock))
    run = _run(client, session, history, limit=40, agent_id=created["id"])
    assert run["status"] == "done", run["error"]
    stats = run["stats"]
    assert stats["cases"] == 40 and stats["handed_back"] == 4 and stats["predicted"] == 36
    assert stats["agreement_rate"] > 0.85
    assert run["agent_version"] == "2.3.1" and run["model"] == "vendor-model"
    comps = session.scalars(select(Comparison).join(Prediction).where(Prediction.run_id == run["id"])).all()
    assert len(comps) == 36 and all(set(c.field_scores) == {"variance_reason", "gl_code"} for c in comps)

    disagreements = client.get(f"/backtests/{run['id']}/cases?only=handed_back", headers=history["mentor"]).json()["items"]
    assert len(disagreements) == 4 and all("HTTP 500" in d["error"] for d in disagreements)


@pytest.mark.parametrize(
    ("url", "dev", "ok"),
    [
        ("https://agent.vendor.example/predict", False, True),
        ("http://agent.vendor.example/predict", False, False),
        ("http://localhost:8100/predict", True, True),
        ("http://localhost:8100/predict", False, False),
        ("https://169.254.169.254/latest", True, False),
        ("https://10.0.0.5/predict", True, False),
    ],
)
def test_endpoint_rules(url, dev, ok):
    if ok:
        assert check_endpoint(url, allow_http_localhost=dev) == url
    else:
        with pytest.raises(EndpointError):
            check_endpoint(url, allow_http_localhost=dev)


def test_external_agent_bad_answers_are_hand_backs(session, history):
    tt = session.get(TaskType, history["tt"])
    builder = ContextBuilder(session, tt)
    case = session.scalars(select(Case).where(Case.connection_id.is_not(None)).order_by(Case.received_at.desc())).first()
    ctx = builder.build(case)
    for response, error in [
        (httpx.Response(200, json={"decision": "pay_twice"}), "isn't one of|is not one of"),
        (httpx.Response(200, text="not json"), "didn't fit"),
        (httpx.Response(404), "HTTP 404"),
    ]:
        agent = ExternalAgent("https://x.example", "s", "m", http=httpx.Client(transport=httpx.MockTransport(lambda r, resp=response: resp)))
        result = agent.predict(ctx)
        assert result.output is None and re.search(error, result.error)


# Permissions, worker -----------------------------------------------------------------------

def test_permissions(client, session, history):
    run = _run(client, session, history, limit=10)
    assert client.get(f"/backtests/{run['id']}", headers=history["manager"]).json()["stats"]["cases"] == 10
    assert client.get(f"/backtests/{run['id']}/cases", headers=history["manager"]).status_code == 403
    assert client.get(f"/backtests?task_type_id={history['tt']}", headers=history["manager"]).status_code == 200


def test_no_history_means_no_backtest(client, session, history):
    other = next(t for t in client.get("/task-types", headers=history["mentor"]).json() if t["team"] == "repair_request")
    resp = client.post("/backtests", json={"task_type_id": other["id"]}, headers=history["mentor"])
    assert resp.status_code == 400 and "no decided history" in resp.json()["detail"]


def test_jobs_are_claimed_once_and_unknown_types_fail(session, history):
    session.add_all([Job(type="mystery", payload={}), Job(type="mystery", payload={})])
    session.commit()
    first, second = claim(session), claim(session)
    assert first.id != second.id and claim(session) is None
    session.add(Job(type="mystery", payload={}))
    session.commit()
    assert run_once(session)
    failed = session.scalar(select(Job).where(Job.status == "failed"))
    assert "no handler" in failed.error
