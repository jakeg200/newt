"""Backtests: replay decided history through an agent, using only what was known when each item
arrived, and score every prediction against what the mentor did. Re-predictions use the same
machinery on the current backlog after a rule changes, and report how many predictions moved.

Contexts are built and leak-checked on the calling thread (all database work stays there);
only agent and judge calls run in parallel.
"""

import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.context import CaseContext, ContextBuilder, LeakageError, check, utc
from app.agents.output import PredictionResult
from app.agents.registry import describe_runner, runner_for
from app.config import get_settings
from app.eval.judge import get_judge, judge_outputs
from app.agents.replay import recordings_for
from app.eval.score import compare, inherited_attribution, prior_teaching, step_checks
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
    """Either the explicit cases of a re-prediction, or the most recent N decided history cases.
    Oldest first, so earlier ones can inform later ones."""
    if params.get("case_ids"):
        rows = session.scalars(select(Case).where(Case.task_type_id == task_type_id, Case.id.in_(params["case_ids"])))
    else:
        rows = session.scalars(_history(session, task_type_id, params).order_by(Case.received_at.desc()).limit(params["limit"]))
    return sorted(rows, key=lambda c: utc(c.received_at))


def latest_backtest(session: Session, task_type_id: str) -> BacktestRun | None:
    runs = session.scalars(
        select(BacktestRun).where(BacktestRun.task_type_id == task_type_id, BacktestRun.status == "done")
        .order_by(BacktestRun.created_at.desc()).limit(20)
    )
    return next((r for r in runs if r.params.get("kind", "backtest") == "backtest"), None)


def backlog_case_ids(session: Session, task_type_id: str, limit: int) -> list[str]:
    """The work a rule change affects first: open items, then the latest backtest's newest cases."""
    ids = list(session.scalars(
        select(Case.id).where(Case.task_type_id == task_type_id, Case.connection_id.is_not(None), Case.status == "open")
        .order_by(Case.received_at.desc()).limit(limit)
    ))
    run = latest_backtest(session, task_type_id)
    if run and len(ids) < limit:
        recent = session.scalars(
            select(Case.id).join(Prediction, Prediction.case_id == Case.id).where(Prediction.run_id == run.id)
            .order_by(Case.received_at.desc()).limit(limit)
        )
        ids += [cid for cid in recent if cid not in ids][: limit - len(ids)]
    return ids


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


def _new_run(session: Session, user: User | None, task_type: TaskType, agent: Agent, params: dict[str, Any]) -> BacktestRun:
    runs_with = describe_runner(agent, samples=params.get("samples"))
    run = BacktestRun(task_type_id=task_type.id, agent_id=agent.id, requested_by=user.id if user else None,
                      status="queued", params={**params, "samples": runs_with["samples"]}, agent_version=agent.version,
                      model=runs_with["model"], config_hash=task_type.config_hash)
    session.add(run)
    session.flush()
    session.add(Job(type="backtest", payload={"run_id": run.id}))
    return run


def create_run(session: Session, user: User, task_type: TaskType, agent: Agent, *, limit: int,
               date_from: str | None = None, date_to: str | None = None) -> BacktestRun:
    params = {"kind": "backtest", "limit": limit, "date_from": date_from, "date_to": date_to}
    if available(session, task_type.id, params) == 0:
        raise BacktestError("no decided history for this task type yet; capture some first")
    run = _new_run(session, user, task_type, agent, params)
    session.commit()
    return run


def create_repredict(session: Session, user: User | None, task_type: TaskType, agent: Agent, reason: str) -> BacktestRun | None:
    """Queue a re-prediction of the backlog. Doesn't commit: it rides on the caller's change."""
    ids = backlog_case_ids(session, task_type.id, get_settings().backlog_size)
    if not ids:
        return None
    params = {"kind": "repredict", "case_ids": ids, "limit": len(ids), "reason": reason,
              "samples": get_settings().repredict_samples}
    return _new_run(session, user, task_type, agent, params)


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
        previous = _previous_decisions(session, [c.id for c in cases], run.created_at)

        # Tools in a backtest or replay answer lookups only from earlier live recordings, never the live system.
        builder.enable_tools(live=False, recordings=recordings_for(session, [c.id for c in cases]))
        contexts: dict[str, CaseContext] = {}
        for case in cases:
            ctx = builder.build(case)
            check(ctx, builder.forbidden(case))  # LeakageError fails the whole run
            contexts[case.id] = ctx

        runner = runner_for(agent, samples=run.params.get("samples"))
        rows: list[dict[str, Any]] = []
        settings = get_settings()
        workers = settings.reprobation_concurrency if run.params.get("kind") == "reprobation" else settings.backtest_concurrency
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(_safe_predict, runner, contexts[c.id]): c for c in cases}
            teaching = prior_teaching(session, [c.id for c in cases])
            for n, fut in enumerate(as_completed(futures), start=1):
                case = futures[fut]
                rows.append(_record(session, run, agent, task, case, builder, fut.result(), teaching.get(case.id)))
                if n % 10 == 0 or n == len(futures):
                    run.progress = {"done": n, "total": len(futures)}
                    run.cost_usd = round(sum(r["cost"] for r in rows), 4)
                    session.commit()

        judged_cost = _judge_texts(task, rows, contexts)
        run.stats = summarize(task, rows, duration_s=time.monotonic() - started, no_handbook=builder.handbook is None,
                              previous=previous, judge_cost=judged_cost)
        run.cost_usd = run.stats["cost_usd"]
        run.status, run.finished_at = "done", utcnow()
        session.commit()
        log.info("backtest %s done: %d cases in %.1fs", run.id, len(rows), time.monotonic() - started)
        if run.params.get("kind") == "reprobation":
            from app.graduation.engine import after_reprobation

            after_reprobation(session, run)
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


def _previous_decisions(session: Session, case_ids: list[str], before: datetime) -> dict[str, str | None]:
    """Each case's most recent prediction before this run, to count what a change moved."""
    out: dict[str, str | None] = {}
    if not case_ids:
        return out
    for p in session.scalars(
        select(Prediction).where(Prediction.case_id.in_(case_ids), Prediction.created_at < before)
        .order_by(Prediction.created_at)
    ):
        out[p.case_id] = (p.output or {}).get("decision")
    return out


def _record(session: Session, run: BacktestRun, agent: Agent, task: TaskTypeConfig, case: Case,
            builder: ContextBuilder, result: PredictionResult, teaching: dict[str, Any] | None = None) -> dict[str, Any]:
    prediction = Prediction(
        case_id=case.id, agent_id=agent.id, run_id=run.id, agent_version=agent.version, model=result.model,
        handbook_version=run.handbook_version, rules_version=run.rules_version,
        output={**(result.output or {}), "samples": result.samples} if result.output else {},
        confidence=result.confidence, error=result.error, input_tokens=result.input_tokens,
        output_tokens=result.output_tokens, cost_usd=result.cost_usd, latency_ms=result.latency_ms,
        trajectory=result.trajectory,
    )
    session.add(prediction)
    session.flush()
    mentor = builder.mentor_decision(case)
    row: dict[str, Any] = {"case_id": case.id, "subject": (case.snapshot or {}).get("subject", ""),
                           "mentor": mentor.decision if mentor else None,
                           "agent": (result.output or {}).get("decision"), "output": result.output,
                           "mentor_texts": mentor.text_outputs if mentor else {},
                           "confidence": result.confidence, "error": result.error, "cost": result.cost_usd,
                           "tokens_in": result.input_tokens, "tokens_out": result.output_tokens,
                           "latency_ms": result.latency_ms, "comparison": None, "comp": None}
    if result.output and mentor:
        c = compare(task, result.output, mentor.decision, mentor.fields, mentor.text_outputs)
        if c["text_judgement"] and not c["decision_match"]:
            c["text_judgement"] = {"status": "skipped", "reason": "different decision"}
        inherited = inherited_attribution(task, result.output, teaching)
        steps = step_checks(task, result.trajectory, result.output.get("decision"))
        if not steps["ok"]:
            c["agreement"] = False  # the right answer without the required evidence is luck, not competence
        comp = Comparison(case_id=case.id, prediction_id=prediction.id, decision_match=c["decision_match"],
                          field_scores=c["field_scores"], text_judgement=c["text_judgement"], agreement=c["agreement"],
                          attribution=inherited, excluded=inherited == "mentor_changed", steps=steps)
        session.add(comp)
        row.update(comparison=c, comp=comp)
    return row


def _judge_texts(task: TaskTypeConfig, rows: list[dict[str, Any]], contexts: dict[str, CaseContext]) -> float:
    """Judge the replies where the agent made the mentor's decision. Updates agreement in place."""
    todo = [r for r in rows if r["comp"] is not None and r["comparison"]["text_judgement"].get("status") == "pending"]
    if not todo:
        return 0.0
    judge = get_judge()

    def run(r: dict[str, Any]) -> dict[str, Any]:
        item = contexts[r["case_id"]].payload()["item"]
        return judge_outputs(judge, {k: item.get(k) for k in ("subject", "inputs")}, r["mentor_texts"],
                             (r["output"] or {}).get("text_outputs", {}), r["comparison"]["text_judgement"]["outputs"])

    with ThreadPoolExecutor(max_workers=max(1, get_settings().backtest_concurrency)) as pool:
        results = list(pool.map(run, todo))
    cost = 0.0
    for r, judgement in zip(todo, results):
        r["comparison"]["text_judgement"] = judgement
        r["comparison"]["agreement"] = r["comparison"]["agreement"] and judgement["acceptable"]
        r["comp"].text_judgement = judgement
        r["comp"].agreement = r["comparison"]["agreement"]
        cost += judgement["cost_usd"]
    return cost


def summarize(task: TaskTypeConfig, rows: list[dict[str, Any]], *, duration_s: float, no_handbook: bool,
              previous: dict[str, str | None] | None = None, judge_cost: float = 0.0) -> dict[str, Any]:
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
    judged = [r for r in scored if r["comparison"]["text_judgement"].get("status") == "judged"]
    errors = Counter(r["error"] for r in rows if r["error"])
    changes = []
    previous = previous or {}
    for r in rows:
        if r["case_id"] in previous and r["agent"] != previous[r["case_id"]]:
            changes.append({"case_id": r["case_id"], "subject": r["subject"], "before": previous[r["case_id"]], "after": r["agent"]})
    return {
        "cases": len(rows),
        "predicted": len(scored),
        "handed_back": sum(1 for r in rows if r["error"]),
        "agreement": agree,
        "agreement_rate": round(agree / len(scored), 4) if scored else None,
        "decision_accuracy": round(sum(r["comparison"]["decision_match"] for r in scored) / len(scored), 4) if scored else None,
        "confusion": {m: dict(c) for m, c in sorted(confusion.items())},
        "decisions": task.decision,
        "fields": {n: {"cases": c["total"], "accuracy": round(c["match"] / c["total"], 4)} for n, c in fields.items()},
        "confidence_buckets": buckets,
        "text_judged": len(judged),
        "text_acceptable": sum(1 for r in judged if r["comparison"]["text_judgement"]["acceptable"]),
        "errors": dict(errors.most_common(5)),
        "cost_usd": round(sum(r["cost"] for r in rows) + judge_cost, 4),
        "judge_cost_usd": round(judge_cost, 4),
        "input_tokens": sum(r["tokens_in"] for r in rows),
        "output_tokens": sum(r["tokens_out"] for r in rows),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / len(rows)) if rows else 0,
        "duration_s": round(duration_s, 1),
        "no_handbook": no_handbook,
        "compared_with_previous": sum(1 for r in rows if r["case_id"] in previous),
        "changed": len(changes),
        "changes": changes[:50],
    }
