"""Backtests: replay decided history through an agent, using only what was known when each item
arrived, and score every prediction against what the mentor did.

Contexts are built and leak-checked on the calling thread (all database work stays there);
only the agent calls run in parallel.
"""

import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.context import ContextBuilder, LeakageError, check, utc
from app.agents.output import PredictionResult
from app.agents.registry import describe_runner, runner_for
from app.config import get_settings
from app.eval.score import compare
from app.logs import get_logger
from app.models import Agent, BacktestRun, Case, Comparison, Job, Prediction, TaskType, User, utcnow
from app.task_types import TaskTypeConfig

log = get_logger("backtest")
BUCKETS = [(0.9, 1.01), (0.7, 0.9), (0.5, 0.7), (0.0, 0.5)]
EST_OUTPUT_TOKENS = 900  # per sample, incl. adaptive thinking at medium effort


class BacktestError(ValueError):
    """A request that can't be done as asked. The message is safe to show users."""


def _history(session: Session, task_type_id: str, params: dict[str, Any]):
    q = select(Case).where(Case.task_type_id == task_type_id, Case.connection_id.is_not(None),
                           Case.is_backtest.is_(True), Case.status == "decided")
    if params.get("date_from"):
        q = q.where(Case.received_at >= datetime.fromisoformat(params["date_from"]))
    if params.get("date_to"):
        q = q.where(Case.received_at < datetime.fromisoformat(params["date_to"]))
    return q


def available(session: Session, task_type_id: str, params: dict[str, Any] | None = None) -> int:
    return session.scalar(select(func.count()).select_from(_history(session, task_type_id, params or {}).subquery())) or 0


def select_cases(session: Session, task_type_id: str, params: dict[str, Any]) -> list[Case]:
    """The most recent N decided history cases, oldest first, so earlier ones can inform later."""
    rows = session.scalars(_history(session, task_type_id, params).order_by(Case.received_at.desc()).limit(params["limit"]))
    return sorted(rows, key=lambda c: utc(c.received_at))


def estimate(session: Session, task_type: TaskType, agent: Agent, limit: int) -> dict[str, Any]:
    """Cases, model calls, a rough cost and time, before anything is spent."""
    from app.agents.builtin import system_prompt, user_prompt
    from app.llm.provider import PRICES_PER_MTOK

    runs_with = describe_runner(agent)
    n = min(limit, available(session, task_type.id))
    out: dict[str, Any] = {"cases_available": available(session, task_type.id), "cases": n, **runs_with,
                           "est_cost_usd": 0.0, "est_minutes": None}
    if n == 0:
        return out
    calls = n * runs_with["samples"]
    if runs_with["billed_here"]:
        builder = ContextBuilder(session, task_type)
        sample = select_cases(session, task_type.id, {"limit": 1})[0]
        ctx = builder.build(sample)
        system_tokens, user_tokens = len(system_prompt(ctx)) // 4, len(user_prompt(ctx)) // 4
        p_in, p_out, p_read = PRICES_PER_MTOK.get(runs_with["model"], (0.0, 0.0, 0.0))
        per_call = (user_tokens * p_in + system_tokens * p_read + EST_OUTPUT_TOKENS * p_out) / 1e6
        out["est_cost_usd"] = round(calls * per_call + system_tokens * p_in * 1.25 / 1e6, 2)
        out["est_minutes"] = round(calls * 12 / get_settings().backtest_concurrency / 60, 1)  # ~12 s per call
    else:
        out["est_minutes"] = round(n * 0.05 / 60, 1) if runs_with["kind"] == "built_in" else None
    out["calls"] = calls
    return out


def create_run(session: Session, user: User, task_type: TaskType, agent: Agent, *, limit: int,
               date_from: str | None = None, date_to: str | None = None) -> BacktestRun:
    params = {"limit": limit, "date_from": date_from, "date_to": date_to}
    if available(session, task_type.id, params) == 0:
        raise BacktestError("no decided history for this task type yet; capture some first")
    runs_with = describe_runner(agent)
    run = BacktestRun(task_type_id=task_type.id, agent_id=agent.id, requested_by=user.id, status="queued",
                      params={**params, "samples": runs_with["samples"]}, agent_version=agent.version,
                      model=runs_with["model"], config_hash=task_type.config_hash)
    session.add(run)
    session.flush()
    session.add(Job(type="backtest", payload={"run_id": run.id}))
    session.commit()
    return run


def _safe_predict(runner, ctx) -> PredictionResult:
    try:
        return runner.predict(ctx)
    except Exception as exc:  # an agent bug must not sink the run; it's a hand-back
        return PredictionResult(None, None, getattr(runner, "model", ""), error=f"agent error: {type(exc).__name__}")


def execute(session: Session, run_id: str) -> BacktestRun:
    run = session.get(BacktestRun, run_id)
    if run is None:
        raise BacktestError("run not found")
    run.status, run.started_at, run.error = "running", utcnow(), None
    session.commit()
    started = time.monotonic()
    try:
        task_type = session.get(TaskType, run.task_type_id)
        agent = session.get(Agent, run.agent_id)
        task = TaskTypeConfig.model_validate(task_type.config)
        builder = ContextBuilder(session, task_type)
        run.handbook_version = builder.handbook.version if builder.handbook else None
        run.rules_version = builder.rules_version
        cases = select_cases(session, task_type.id, run.params)
        run.progress = {"done": 0, "total": len(cases)}
        session.commit()

        contexts = []
        for case in cases:
            ctx = builder.build(case)
            check(ctx, builder.forbidden(case))  # LeakageError fails the whole run
            contexts.append((case, ctx))

        runner = runner_for(agent)
        rows: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, get_settings().backtest_concurrency)) as pool:
            futures = {pool.submit(_safe_predict, runner, ctx): case for case, ctx in contexts}
            for n, fut in enumerate(as_completed(futures), start=1):
                case = futures[fut]
                rows.append(_record(session, run, agent, task, case, builder, fut.result()))
                if n % 10 == 0 or n == len(futures):
                    run.progress = {"done": n, "total": len(futures)}
                    run.cost_usd = round(sum(r["cost"] for r in rows), 4)
                    session.commit()

        run.stats = summarize(task, rows, duration_s=time.monotonic() - started, no_handbook=builder.handbook is None)
        run.cost_usd = run.stats["cost_usd"]
        run.status, run.finished_at = "done", utcnow()
        session.commit()
        log.info("backtest %s done: %d cases in %.1fs", run.id, len(rows), time.monotonic() - started)
    except LeakageError as exc:
        session.rollback()
        run = session.get(BacktestRun, run_id)
        run.status, run.finished_at, run.error = "failed", utcnow(), f"Time-travel guard: {exc}"
        session.commit()
        log.error("backtest %s stopped by the time-travel guard", run_id)
    except Exception as exc:
        session.rollback()
        run = session.get(BacktestRun, run_id)
        run.status, run.finished_at, run.error = "failed", utcnow(), f"{type(exc).__name__}: {str(exc)[:300]}"
        session.commit()
        log.exception("backtest %s failed", run_id)
    return run


def _record(session: Session, run: BacktestRun, agent: Agent, task: TaskTypeConfig, case: Case,
            builder: ContextBuilder, result: PredictionResult) -> dict[str, Any]:
    prediction = Prediction(
        case_id=case.id, agent_id=agent.id, run_id=run.id, agent_version=agent.version, model=result.model,
        handbook_version=run.handbook_version, rules_version=run.rules_version,
        output={**(result.output or {}), "samples": result.samples} if result.output else {},
        confidence=result.confidence, error=result.error, input_tokens=result.input_tokens,
        output_tokens=result.output_tokens, cost_usd=result.cost_usd, latency_ms=result.latency_ms,
    )
    session.add(prediction)
    session.flush()
    mentor = builder.mentor_decision(case)
    row: dict[str, Any] = {"mentor": mentor.decision if mentor else None, "agent": None, "confidence": result.confidence,
                           "error": result.error, "cost": result.cost_usd, "tokens_in": result.input_tokens,
                           "tokens_out": result.output_tokens, "latency_ms": result.latency_ms, "comparison": None}
    if result.output and mentor:
        c = compare(task, result.output, mentor.decision, mentor.fields, mentor.text_outputs)
        session.add(Comparison(case_id=case.id, prediction_id=prediction.id, decision_match=c["decision_match"],
                               field_scores=c["field_scores"], text_judgement=c["text_judgement"], agreement=c["agreement"]))
        row.update(agent=result.output["decision"], comparison=c)
    return row


def summarize(task: TaskTypeConfig, rows: list[dict[str, Any]], *, duration_s: float, no_handbook: bool) -> dict[str, Any]:
    scored = [r for r in rows if r["comparison"]]
    agree = sum(1 for r in scored if r["comparison"]["agreement"])
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for r in scored:
        confusion[r["mentor"]][r["agent"]] += 1
    fields: dict[str, Counter[str]] = defaultdict(Counter)
    for r in scored:
        for name, s in r["comparison"]["field_scores"].items():
            fields[name]["total"] += 1
            fields[name]["match"] += s["match"]
    buckets = []
    for lo, hi in BUCKETS:
        b = [r for r in scored if r["confidence"] is not None and lo <= r["confidence"] < hi]
        buckets.append({"from": lo, "to": min(hi, 1.0), "cases": len(b),
                        "agreement": round(sum(r["comparison"]["agreement"] for r in b) / len(b), 4) if b else None})
    errors = Counter(r["error"] for r in rows if r["error"])
    return {
        "cases": len(rows),
        "predicted": len(scored),
        "handed_back": len(rows) - len(scored),
        "agreement": agree,
        "agreement_rate": round(agree / len(scored), 4) if scored else None,
        "decision_accuracy": round(sum(r["comparison"]["decision_match"] for r in scored) / len(scored), 4) if scored else None,
        "confusion": {m: dict(c) for m, c in sorted(confusion.items())},
        "decisions": task.decision,
        "fields": {n: {"cases": c["total"], "accuracy": round(c["match"] / c["total"], 4)} for n, c in fields.items()},
        "confidence_buckets": buckets,
        "errors": dict(errors.most_common(5)),
        "cost_usd": round(sum(r["cost"] for r in rows), 4),
        "input_tokens": sum(r["tokens_in"] for r in rows),
        "output_tokens": sum(r["tokens_out"] for r in rows),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / len(rows)) if rows else 0,
        "duration_s": round(duration_s, 1),
        "no_handbook": no_handbook,
        "text_outputs_pending": sum(1 for r in scored if r["comparison"]["text_judgement"]),
    }
