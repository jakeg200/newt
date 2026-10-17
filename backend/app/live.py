"""Live work: what happens when a new item arrives, by stage.

shadow      a sealed prediction is stored. Nothing is shown until the mentor has acted; then it's
            revealed and scored like a backtest case.
supervised  the agent drafts its actions; the mentor approves in one tap, edits, or rejects.
autonomous  above τ and with no hand-back reason, allowed actions run; everything else is handed
            back. About 1 in 10 handled cases gets a blind audit.
"""

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actions import policy
from app.agents.context import ContextBuilder, check, utc
from app.agents.output import validate_output
from app.agents.registry import runner_for
from app.eval.calibration import Calibrator, DecisionModel, Example, raw_score
from app.eval.judge import get_judge, judge_outputs
from app.eval.score import compare, inherited_attribution, prior_teaching
from app.graduation import handback
from app.logs import get_logger
from app.models import (ActionLog, Agent, Apprenticeship, Audit, Case, Comparison, HumanAction, Job, Prediction, TaskType,
                        User, utcnow)
from app.task_types import TaskTypeConfig

log = get_logger("live")
AUDIT_ONE_IN = 10


def after_ingest(session: Session, new_live_case_ids: list[str], touched_case_ids: list[str]) -> None:
    """Queue the follow-up work for a capture run (called by ingest; never does the work inline)."""
    if new_live_case_ids:
        session.add(Job(type="live_predict", payload={"case_ids": new_live_case_ids}))
    sealed = sorted(set(session.scalars(
        select(Prediction.case_id).where(Prediction.case_id.in_(touched_case_ids), Prediction.run_id.is_(None))
    ))) if touched_case_ids else []
    if sealed:
        session.add(Job(type="live_score", payload={"case_ids": sealed}))


def _audit_sampled(case_id: str) -> bool:
    return int(hashlib.sha256(f"audit:{case_id}".encode()).hexdigest(), 16) % AUDIT_ONE_IN == 0


def predict_cases(session: Session, case_ids: list[str]) -> int:
    cases = list(session.scalars(select(Case).where(Case.id.in_(case_ids))))
    done = 0
    for tt_id in {c.task_type_id for c in cases}:
        tt = session.get(TaskType, tt_id)
        task = TaskTypeConfig.model_validate(tt.config)
        agent = session.get(Agent, session.get(Apprenticeship, tt.apprenticeship_id).agent_id)
        builder = ContextBuilder(session, tt)
        runner = runner_for(agent)
        calibrator = Calibrator.load(tt.calibration)
        batch = sorted((c for c in cases if c.task_type_id == tt_id), key=lambda c: utc(c.received_at))
        earliest = utc(batch[0].received_at)
        model = DecisionModel([Example(d.decided_at, " ".join([(d.case.snapshot or {}).get("subject", ""),
                                                                 *[str(v) for v in ((d.case.snapshot or {}).get("inputs") or {}).values()]]),
                                       d.decision) for d in builder.decided.values() if d.decided_at < earliest])
        for case in batch:
            if session.scalar(select(Prediction.id).where(Prediction.case_id == case.id, Prediction.run_id.is_(None))):
                continue  # already predicted
            ctx = builder.build(case)
            check(ctx, builder.forbidden(case))
            result = runner.predict(ctx)
            if result.output is not None:  # whatever the agent, only the task's output shape goes further
                try:
                    result.output = validate_output(result.output, task).model_dump()
                except ValueError as exc:
                    result.output, result.error = None, f"the agent's answer didn't fit the task: {exc}"[:300]
            clf = model.prob(handback.item_text(ctx), result.output["decision"]) if result.output else None
            raw = raw_score(result.confidence, clf)
            conf = calibrator(raw) if result.output else None
            hb = handback.decide(ctx, result, conf, tt.tau) if tt.status in ("supervised", "autonomous") else {"hand_back": False, "reasons": []}
            p = Prediction(case_id=case.id, agent_id=agent.id, run_id=None, agent_version=agent.version, model=result.model,
                           handbook_version=ctx.handbook_version, rules_version=ctx.rules_version,
                           output={**(result.output or {}), "confidence": {"self": result.confidence, "classifier": clf,
                                                                            "raw": raw, "calibrated": conf},
                                   "hand_back": hb, "mode": tt.status} if result.output else {"hand_back": hb, "mode": tt.status},
                           confidence=conf, error=result.error, input_tokens=result.input_tokens,
                           output_tokens=result.output_tokens, cost_usd=result.cost_usd, latency_ms=result.latency_ms)
            session.add(p)
            session.flush()
            if result.output and not hb["hand_back"] and tt.status in ("supervised", "autonomous"):
                _act(session, tt, task, case, p, mode=tt.status)
            done += 1
        session.commit()
    return done


def _act(session: Session, tt: TaskType, task: TaskTypeConfig, case: Case, p: Prediction, mode: str) -> None:
    snapshot = case.snapshot or {}
    checked = [(a, policy.check(a, task, snapshot)) for a in policy.plan(task, snapshot, p.output, mode)]
    stopped = [(a, v) for a, v in checked if not v["ok"]]
    if stopped:
        # One blocked action stops the whole case: a status set without its reply would be half done.
        for action, verdict in stopped:
            session.add(ActionLog(case_id=case.id, prediction_id=p.id, mode=mode, action=action.type, payload=action.params,
                                  policy_check=verdict, status="blocked"))
            log.warning("blocked %s on case %s: %s", action.type, case.id, "; ".join(verdict["reasons"]))
        hb = p.output.get("hand_back") or {}
        reasons = [*hb.get("reasons", []), *(f"the action policy stopped {a.type}: {r}" for a, v in stopped for r in v["reasons"])]
        p.output = {**p.output, "hand_back": {**hb, "hand_back": True, "reasons": reasons}}
        return
    for action, verdict in checked:
        status = "executed" if mode == "autonomous" else "pending"
        session.add(ActionLog(case_id=case.id, prediction_id=p.id, mode=mode, action=action.type, payload=action.params,
                              policy_check=verdict, status=status, executed_at=utcnow() if status == "executed" else None))
    if mode == "autonomous":
        case.status = "handled"
        if _audit_sampled(case.id):
            session.add(Audit(case_id=case.id, task_type_id=tt.id, prediction_id=p.id, blind=True))


def score_cases(session: Session, case_ids: list[str]) -> int:
    """Reveal and score sealed live predictions once the mentor has acted on their cases."""
    scored = 0
    rows = session.execute(
        select(Prediction, Case).join(Case, Case.id == Prediction.case_id)
        .outerjoin(Comparison, Comparison.prediction_id == Prediction.id)
        .where(Prediction.case_id.in_(case_ids), Prediction.run_id.is_(None), Comparison.id.is_(None))
    ).all()
    judge = None
    for p, case in rows:
        mentor = session.scalar(select(HumanAction).where(HumanAction.case_id == case.id, HumanAction.source != "audit")
                                .order_by(HumanAction.acted_at))
        if mentor is None or not mentor.payload.get("decision") or not (p.output or {}).get("decision"):
            continue
        task = TaskTypeConfig.model_validate(session.get(TaskType, case.task_type_id).config)
        c = compare(task, p.output, mentor.payload["decision"], mentor.payload.get("fields") or {}, mentor.payload.get("text_outputs") or {})
        if c["text_judgement"]:
            if c["decision_match"]:
                judge = judge or get_judge()
                snap = case.snapshot or {}
                c["text_judgement"] = judge_outputs(judge, {"subject": snap.get("subject"), "inputs": snap.get("inputs")},
                                                    mentor.payload.get("text_outputs") or {}, p.output.get("text_outputs") or {},
                                                    c["text_judgement"]["outputs"])
                c["agreement"] = c["agreement"] and c["text_judgement"]["acceptable"]
            else:
                c["text_judgement"] = {"status": "skipped", "reason": "different decision"}
        inherited = inherited_attribution(task, p.output, prior_teaching(session, [case.id]).get(case.id))
        session.add(Comparison(case_id=case.id, prediction_id=p.id, decision_match=c["decision_match"], field_scores=c["field_scores"],
                               text_judgement=c["text_judgement"], agreement=c["agreement"],
                               attribution=inherited, excluded=inherited == "mentor_changed"))
        scored += 1
    session.commit()
    return scored


# Supervised practice -----------------------------------------------------------------------

def pending_drafts(session: Session, tt: TaskType) -> list[dict[str, Any]]:
    rows = session.execute(
        select(ActionLog, Prediction, Case).join(Prediction, Prediction.id == ActionLog.prediction_id)
        .join(Case, Case.id == ActionLog.case_id).where(Case.task_type_id == tt.id, ActionLog.mode == "supervised")
        .order_by(Case.received_at)
    ).all()
    cards: dict[str, dict[str, Any]] = {}
    for log_row, p, case in rows:
        card = cards.setdefault(p.id, {"prediction_id": p.id, "case": _case_out(case), "agent": _agent_out(p),
                                       "confidence": p.confidence, "actions": [], "open": False})
        card["actions"].append({"id": log_row.id, "action": log_row.action, "payload": log_row.payload,
                                "status": log_row.status, "policy": log_row.policy_check})
        card["open"] = card["open"] or log_row.status == "pending"
    return [c for c in cards.values() if c["open"]]


def _case_out(case: Case) -> dict[str, Any]:
    snap = case.snapshot or {}
    return {"id": case.id, "received_at": case.received_at, "subject": snap.get("subject", ""), "from": snap.get("from"),
            "inputs": snap.get("inputs", {})}


def _agent_out(p: Prediction) -> dict[str, Any]:
    out = p.output or {}
    return {k: out.get(k) for k in ("decision", "fields", "text_outputs", "rationale", "missing_info", "hand_back")}


def _prediction(session: Session, user: User, prediction_id: str) -> tuple[Prediction, Case, TaskType]:
    from app.models import Connection

    p = session.get(Prediction, prediction_id)
    case = session.get(Case, p.case_id) if p else None
    conn = session.get(Connection, case.connection_id) if case and case.connection_id else None
    if p is None or conn is None or conn.org_id != user.org_id:
        raise LookupError("prediction not found")
    return p, case, session.get(TaskType, case.task_type_id)


def decide_draft(session: Session, user: User, prediction_id: str, *, approve: bool, decision: str | None = None,
                 fields: dict[str, Any] | None = None, text_outputs: dict[str, str] | None = None, note: str | None = None) -> dict[str, Any]:
    """One tap: approve as drafted, approve with edits, or reject with the mentor's own decision.
    The outcome is the mentor's action on the case, so it's scored like any other."""
    p, case, tt = _prediction(session, user, prediction_id)
    task = TaskTypeConfig.model_validate(tt.config)
    logs = list(session.scalars(select(ActionLog).where(ActionLog.prediction_id == p.id, ActionLog.status == "pending")))
    if not logs:
        raise ValueError("nothing is waiting for approval on this case")
    out = p.output or {}
    final = {"decision": decision or out.get("decision"), "fields": fields if fields is not None else out.get("fields") or {},
             "text_outputs": text_outputs if text_outputs is not None else out.get("text_outputs") or {}}
    if final["decision"] not in task.decision:
        raise ValueError(f"decision must be one of {task.decision}")
    untouched = approve and decision is None and fields is None and text_outputs is None
    status = "approved" if untouched else ("edited" if approve else "rejected")
    now = utcnow()
    for row in logs:
        row.status, row.decided_by = status, user.id
        if approve:
            row.executed_at = now  # simulated execution
    session.add(HumanAction(case_id=case.id, action_type="decision", acted_at=now, source="supervised",
                            source_ref=f"supervised:{p.id}", match_method="explicit",
                            payload={**final, "via": "supervised", "untouched": untouched, **({"note": note} if note else {})}))
    case.status = "decided"
    session.commit()
    score_cases(session, [case.id])
    return {"status": status, "untouched": untouched}


def untouched_rate(session: Session, tt: TaskType) -> dict[str, Any]:
    rows = session.execute(
        select(HumanAction.payload).join(Case, Case.id == HumanAction.case_id)
        .where(Case.task_type_id == tt.id, HumanAction.source == "supervised")
    ).all()
    n = len(rows)
    untouched = sum(1 for (payload,) in rows if payload.get("untouched"))
    return {"cases": n, "untouched": untouched, "rate": round(untouched / n, 4) if n else None}


# Blind audits ------------------------------------------------------------------------------

def audit_queue(session: Session, tt: TaskType) -> list[dict[str, Any]]:
    rows = session.execute(select(Audit, Case).join(Case, Case.id == Audit.case_id)
                           .where(Audit.task_type_id == tt.id, Audit.result.is_(None)).order_by(Audit.created_at)).all()
    # Blind: the agent's answer is never sent with the card.
    return [{"audit_id": a.id, "case": _case_out(c)} for a, c in rows]


def submit_audit(session: Session, user: User, audit_id: str, decision: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.graduation.engine import review

    audit = session.get(Audit, audit_id)
    if audit is None or audit.result is not None:
        raise LookupError("audit not found or already done")
    p, case, tt = _prediction(session, user, audit.prediction_id)
    task = TaskTypeConfig.model_validate(tt.config)
    if decision not in task.decision:
        raise ValueError(f"decision must be one of {task.decision}")
    c = compare(task, p.output or {}, decision, fields or {}, {})
    audit.result = "pass" if c["agreement"] else "fail"
    audit.mentor_payload = {"decision": decision, "fields": fields or {}}
    audit.completed_at = utcnow()
    session.add(HumanAction(case_id=case.id, action_type="decision", acted_at=audit.completed_at, source="audit",
                            source_ref=f"audit:{audit.id}", match_method="explicit",
                            payload={"decision": decision, "fields": fields or {}, "via": "blind_audit"}))
    session.commit()
    outcome = review(session, tt)
    return {"result": audit.result, "agent_decision": (p.output or {}).get("decision"), "review": outcome}
