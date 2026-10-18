"""Graduation: per task type, on a statistical bar, signed by people.

Stages (BRIEF.md):
  shadow      sealed predictions, scored against the mentor; no actions
  supervised  bar met and the mentor signs; the agent drafts, the mentor approves in one tap
  autonomous  50+ supervised cases, no failed audit, the manager signs; acts alone above τ
  demoted     back to supervised or shadow when the evidence says so

The evidence is every scored prediction (the latest backtest plus live shadowing), each with a
calibrated confidence. τ is the lowest threshold whose upper bound stays under α.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.context import ContextBuilder, utc
from app.backtest.runner import _new_run, latest_backtest
from app.eval.calibration import Calibrator, DecisionModel, Example, Scored, classifier_probs, fit_calibrator, raw_score
from app.eval.stats import cases_needed, choose_tau, lcb95, ucb95
from app.logs import get_logger
from app.models import (ActionLog, Agent, Apprenticeship, Audit, BacktestRun, Case, Comparison, GraduationEvent,
                        Prediction, TaskType, TrackRecord, User, utcnow)
from app.task_types import TaskTypeConfig

log = get_logger("graduation")

MIN_LIVE = 50
MIN_COVERAGE = 0.4
SUPERVISED_BEFORE_AUTONOMY = 50
# The frozen record is the graduation evidence itself, so re-probation has the same statistical power:
# at α = 2%, even one error in 150 cases breaks the bound, which would demote on every model swap.
FROZEN_MAX = 600
AUDIT_WINDOW = 50
GRADUATED = ("supervised", "autonomous")


class GraduationError(ValueError):
    """A request that can't be done as asked. The message is safe to show users."""


@dataclass
class Sample:
    case_id: str
    prediction_id: str
    as_of: datetime
    subject: str
    text: str
    agent_decision: str
    mentor_decision: str | None
    self_consistency: float | None
    error: bool
    live: bool


def _text(case: Case) -> str:
    snap = case.snapshot or {}
    return " ".join([snap.get("subject", ""), *[str(v) for v in (snap.get("inputs") or {}).values()]])


def samples(session: Session, task_type: TaskType, *, run_id: str | None = None) -> list[Sample]:
    """Scored predictions: one run's (when given), or the latest backtest plus every live one."""
    if run_id:
        where = Prediction.run_id == run_id
    else:
        run = latest_backtest(session, task_type.id)
        where = (Prediction.run_id == run.id) | Prediction.run_id.is_(None) if run else Prediction.run_id.is_(None)
    rows = session.execute(
        select(Prediction, Comparison, Case).join(Comparison, Comparison.prediction_id == Prediction.id)
        .join(Case, Case.id == Prediction.case_id).where(Case.task_type_id == task_type.id, where)
    ).all()
    out = []
    for p, comp, case in rows:
        agreed = comp.effective_agreement
        if agreed is None or not (p.output or {}).get("decision"):
            continue
        conf = (p.output or {}).get("confidence", {})
        out.append(Sample(case.id, p.id, utc(case.received_at), (case.snapshot or {}).get("subject", ""), _text(case),
                          p.output["decision"], None, conf.get("self", p.confidence) if isinstance(conf, dict) else p.confidence,
                          not agreed, p.run_id is None))
    return sorted(out, key=lambda s: s.as_of)


def history(builder: ContextBuilder) -> list[Example]:
    return [Example(d.decided_at, _text(d.case), d.decision) for d in builder.decided.values()]


def score(builder: ContextBuilder, items: list[Sample], calibrator: Calibrator | None = None) -> tuple[list[float], Calibrator]:
    probs = classifier_probs(history(builder), [Scored(s.case_id, s.as_of, s.text, s.agent_decision, s.self_consistency) for s in items])
    raws = [raw_score(s.self_consistency, probs.get(s.case_id)) for s in items]
    cal = calibrator if calibrator is not None else fit_calibrator(raws, [not s.error for s in items])
    return [cal(r) for r in raws], cal


def scores_and_errors(session: Session, task_type: TaskType) -> tuple[list[float], list[bool]]:
    """The calibrated confidence and error flag of every evidence case: what `choose_tau` works on. Used for what-ifs
    on the risk limit (capacity planning); the gate itself still runs through `evaluate`."""
    builder = ContextBuilder(session, task_type)
    items = samples(session, task_type)
    scores, _ = score(builder, items)
    return scores, [s.error for s in items]


def evaluate(session: Session, task_type: TaskType) -> dict[str, Any]:
    task = TaskTypeConfig.model_validate(task_type.config)
    builder = ContextBuilder(session, task_type)
    items = samples(session, task_type)
    for s in items:
        d = builder.decided.get(s.case_id)
        s.mentor_decision = d.decision if d else None
    scores, cal = score(builder, items)
    th = choose_tau(scores, [s.error for s in items], task.alpha)
    order = sorted(range(len(items)), key=lambda i: -scores[i])
    above = [items[i] for i in order[: th.n_above]]
    below = [items[i] for i in order[th.n_above:]]
    live_above = sum(1 for s in above if s.live)
    checks = [
        {"name": "bound", "ok": th.tau is not None,
         "detail": f"upper bound {th.ucb:.1%} on the error rate, against α = {task.alpha:.0%}"},
        {"name": "cases", "ok": th.n_above >= task.min_cases, "detail": f"{th.n_above} cases above τ, of {task.min_cases} needed"},
        {"name": "live", "ok": live_above >= MIN_LIVE, "detail": f"{live_above} of them live, of {MIN_LIVE} needed"},
        {"name": "coverage", "ok": th.coverage >= MIN_COVERAGE, "detail": f"coverage {th.coverage:.0%}, of {MIN_COVERAGE:.0%} needed"},
    ]

    def ex(s: Sample, conf: float) -> dict[str, Any]:
        return {"case_id": s.case_id, "subject": s.subject, "agent": s.agent_decision, "mentor": s.mentor_decision,
                "confidence": round(conf, 3), "live": s.live}

    conf_of = {s.case_id: scores[i] for i, s in enumerate(items)}
    return {
        "task_type_id": task_type.id, "status": task_type.status, "alpha": task.alpha, "min_cases": task.min_cases,
        "evaluated_at": utcnow().isoformat(),
        "cases": len(items), "live_cases": sum(s.live for s in items), "backtest_cases": sum(not s.live for s in items),
        "agreement_rate": round(1 - sum(s.error for s in items) / len(items), 4) if items else None,
        "tau": th.tau, "n_above": th.n_above, "errors_above": th.errors_above, "live_above": live_above,
        "ucb": round(th.ucb, 5), "coverage": round(th.coverage, 4), "hand_back_rate": round(1 - th.coverage, 4) if items else None,
        "cases_needed": cases_needed(task.alpha, th.errors_above),
        "more_clean_cases_needed": max(0, cases_needed(task.alpha, th.errors_above) - th.n_above),
        "checks": checks, "eligible": all(c["ok"] for c in checks),
        "agreements": [ex(s, conf_of[s.case_id]) for s in above if not s.error][-5:],
        "disagreements": [ex(s, conf_of[s.case_id]) for s in above if s.error][:10],
        "hand_backs": [ex(s, conf_of[s.case_id]) for s in below][:5],
        "criteria": DecisionModel(history(builder)).top_terms(),
        "calibration": cal.dump(),
        "frozen_case_ids": [s.case_id for s in items][-FROZEN_MAX:],
    }


def _event(session: Session, tt: TaskType, to: str, evidence: dict[str, Any], signer: User | None) -> GraduationEvent:
    ev = GraduationEvent(task_type_id=tt.id, from_status=tt.status, to_status=to, evidence=evidence,
                         signed_by=signer.id if signer else None, signed_at=utcnow())
    session.add(ev)
    tt.status = to
    return ev


def last_graduation(session: Session, tt: TaskType) -> GraduationEvent | None:
    return session.scalar(select(GraduationEvent).where(GraduationEvent.task_type_id == tt.id, GraduationEvent.signed_by.is_not(None),
                                                       GraduationEvent.to_status.in_(GRADUATED))
                          .order_by(GraduationEvent.signed_at.desc()).limit(1))


def supervised_cases(session: Session, tt: TaskType, since: datetime | None) -> int:
    q = (select(func.count(func.distinct(ActionLog.case_id))).join(Case, Case.id == ActionLog.case_id)
         .where(Case.task_type_id == tt.id, ActionLog.mode == "supervised", ActionLog.status.in_(("approved", "edited", "rejected"))))
    if since:
        q = q.where(ActionLog.created_at >= since)
    return session.scalar(q) or 0


def audits_since(session: Session, tt: TaskType, since: datetime | None) -> list[Audit]:
    q = select(Audit).where(Audit.task_type_id == tt.id, Audit.result.is_not(None)).order_by(Audit.completed_at)
    if since:
        q = q.where(Audit.completed_at >= since)
    return list(session.scalars(q))


def sign(session: Session, tt: TaskType, user: User, to: str) -> GraduationEvent:
    if to == "supervised":
        if tt.status not in ("shadow", "demoted"):
            raise GraduationError(f"this task type is already {tt.status}")
        if user.role not in ("mentor", "admin"):
            raise PermissionError("the mentor signs graduation to supervised practice")
    elif to == "autonomous":
        if tt.status != "supervised":
            raise GraduationError("autonomy comes after supervised practice")
        if user.role != "manager":
            raise PermissionError("the accountable manager signs autonomy")
        grad = last_graduation(session, tt)
        since = utc(grad.signed_at) if grad else None
        n = supervised_cases(session, tt, since)
        if n < SUPERVISED_BEFORE_AUTONOMY:
            raise GraduationError(f"{n} supervised cases so far; autonomy needs {SUPERVISED_BEFORE_AUTONOMY}")
        if any(a.result == "fail" for a in audits_since(session, tt, since)):
            raise GraduationError("an audit failed since graduation")
    else:
        raise GraduationError("sign to 'supervised' or 'autonomous'")
    evaluation = evaluate(session, tt)
    if not evaluation["eligible"]:
        failing = "; ".join(c["detail"] for c in evaluation["checks"] if not c["ok"])
        raise GraduationError(f"the bar isn't met: {failing}")
    tt.tau = evaluation["tau"]
    tt.calibration = evaluation["calibration"]
    ev = _event(session, tt, to, {**evaluation, "role": user.role}, user)
    session.flush()
    session.add(TrackRecord(task_type_id=tt.id, metrics=_record_metrics(session, tt)))
    session.commit()
    log.info("task type %s graduated to %s", tt.id, to)
    return ev


def demote(session: Session, tt: TaskType, to: str, reason: str, evidence: dict[str, Any] | None = None) -> GraduationEvent:
    ev = _event(session, tt, "demoted" if to == "shadow" else to, {"reason": reason, "demoted_to": to, **(evidence or {})}, None)
    if to == "shadow":
        tt.tau = None
    session.flush()
    session.add(TrackRecord(task_type_id=tt.id, metrics=_record_metrics(session, tt)))
    session.commit()
    log.warning("task type %s demoted to %s: %s", tt.id, to, reason)
    return ev


def review(session: Session, tt: TaskType) -> dict[str, Any] | None:
    """The brief's demotion rules, checked after every audit.

    To supervised: the upper bound on the graduation hold-out plus every audit since rises above α.
    To shadow: the lower bound on the last 50 audits exceeds α (at 2%: four or more errors in 50).
    A bound on 50 audits alone can't be used: with zero errors it's 5.8%, which would demote everything at 2%."""
    if tt.status not in GRADUATED:
        return None
    task = TaskTypeConfig.model_validate(tt.config)
    grad = last_graduation(session, tt)
    if grad is None:
        return None
    audits = audits_since(session, tt, utc(grad.signed_at))
    fails = sum(a.result == "fail" for a in audits)
    recent = audits[-AUDIT_WINDOW:]
    recent_fails = sum(a.result == "fail" for a in recent)
    lower = lcb95(recent_fails, len(recent))
    upper = ucb95(grad.evidence.get("errors_above", 0) + fails, grad.evidence.get("n_above", 0) + len(audits))
    out = {"audits": len(audits), "failed": fails, "upper": round(upper, 5), "lower_recent": round(lower, 5), "alpha": task.alpha}
    if lower > task.alpha:
        demote(session, tt, "shadow", f"the last {len(recent)} audits show an error rate above α (lower bound {lower:.1%})", out)
        out["demoted_to"] = "shadow"
    elif upper > task.alpha and tt.status == "autonomous":
        demote(session, tt, "supervised", f"graduation evidence plus audits no longer clears α (upper bound {upper:.1%})", out)
        out["demoted_to"] = "supervised"
    return out


# Re-probation: model swaps and procedure changes re-run the frozen record --------------------

def frozen_case_ids(session: Session, tt: TaskType) -> list[str]:
    grad = last_graduation(session, tt)
    if grad and grad.evidence.get("frozen_case_ids"):
        return grad.evidence["frozen_case_ids"]
    return [s.case_id for s in samples(session, tt)][-FROZEN_MAX:]


def start_reprobation(session: Session, tt: TaskType, user: User | None, reason: str) -> BacktestRun | None:
    ids = frozen_case_ids(session, tt)
    if not ids:
        return None
    agent = session.get(Agent, session.get(Apprenticeship, tt.apprenticeship_id).agent_id)
    return _new_run(session, user, tt, agent, {"kind": "reprobation", "case_ids": ids, "limit": len(ids), "reason": reason})


def on_procedure_change(session: Session, tt: TaskType, user: User | None, reason: str) -> BacktestRun | None:
    """Handbook, rules or config changed: a graduated task type proves itself again on the frozen record."""
    if tt.status not in GRADUATED:
        return None
    return start_reprobation(session, tt, user, reason)


def swap_model(session: Session, agent: Agent, user: User, model: str, version: str) -> list[BacktestRun]:
    """A new model is a new hire: it re-runs probation on the frozen record before touching live work."""
    old = {"model": agent.model, "version": agent.version}
    agent.model, agent.version = model, version
    agent.config = {**(agent.config or {}), "model": model, "previous": old}
    runs = []
    for tt in session.scalars(select(TaskType).join(Apprenticeship).where(Apprenticeship.agent_id == agent.id)):
        if tt.status in GRADUATED or last_graduation(session, tt):
            run = start_reprobation(session, tt, user, f"model swap: {old['model']} {old['version']} → {model} {version}")
            if run:
                runs.append(run)
    session.commit()
    return runs


def after_reprobation(session: Session, run: BacktestRun) -> dict[str, Any]:
    """Score the frozen record with the graduation calibration and τ. Keep the stage if the bound
    holds; otherwise demote to shadow (failed regression)."""
    tt = session.get(TaskType, run.task_type_id)
    task = TaskTypeConfig.model_validate(tt.config)
    builder = ContextBuilder(session, tt)
    items = samples(session, tt, run_id=run.id)
    scores, _ = score(builder, items, Calibrator.load(tt.calibration))
    tau = tt.tau
    above = [s for s, c in zip(items, scores) if tau is not None and c >= tau]
    errors = sum(s.error for s in above)
    upper = ucb95(errors, len(above))
    result = {"cases": len(items), "tau": tau, "n_above": len(above), "errors_above": errors, "ucb": round(upper, 5),
              "alpha": task.alpha, "coverage": round(len(above) / len(items), 4) if items else 0.0,
              "duration_s": run.stats.get("duration_s"), "reason": run.params.get("reason")}
    passed = tau is not None and upper <= task.alpha and result["coverage"] >= MIN_COVERAGE
    result["passed"] = passed
    run.stats = {**run.stats, "reprobation": result}
    if tt.status in GRADUATED and not passed:
        demote(session, tt, "shadow", f"failed re-probation after {run.params.get('reason')}", result)
    else:
        session.add(GraduationEvent(task_type_id=tt.id, from_status=tt.status, to_status=tt.status,
                                    evidence={"recertified": passed, **result}, signed_at=utcnow()))
        session.commit()
    return result


def _record_metrics(session: Session, tt: TaskType) -> dict[str, Any]:
    from app.graduation.track_record import build

    return build(session, tt)
