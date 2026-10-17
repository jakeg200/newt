"""The teaching queue and lessons.

The queue shows only what's worth the mentor's time: cases where the apprentice disagreed, cases
where it was unsure, and a few agreed cases with a drafted reply as spot checks, which also keep
the reply judge honest. One tap records a lesson; agreements are counted, never reviewed.
"""

import hashlib
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import utc
from app.backtest.runner import create_repredict, latest_backtest
from app.learning import rules as rules_mod
from app.models import (Agent, Apprenticeship, BacktestRun, Case, Comparison, Connection, HumanAction, Lesson,
                        Prediction, Rule, TaskType, User)

UNSURE_BELOW = 0.7
SPOT_CHECK_ONE_IN = 10
TRUST_JUDGE_AT = 0.9
TRUST_JUDGE_MIN = 20

ATTRIBUTIONS = ("intern_wrong", "both_fine", "mentor_changed", "couldnt_know")
EFFECTS = {
    "intern_wrong": "Counted as the intern's mistake. It will see your decision on cases like this.",
    "both_fine": "Counted as agreement: both answers work here.",
    "mentor_changed": "Taken out of the intern's score, since your own call on this one was off.",
    "couldnt_know": "Marked as one the intern should have handed back. Add the missing fact as a rule so it can know next time.",
}


class TeachingError(ValueError):
    """A request that can't be done as asked. The message is safe to show users."""


def _spot_check(case_id: str) -> bool:
    return int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % SPOT_CHECK_ONE_IN == 0


def _kind(comp: Comparison, confidence: float | None) -> str | None:
    if not comp.agreement:
        return "disagreement"
    if confidence is not None and confidence < UNSURE_BELOW:
        return "unsure"
    if comp.text_judgement.get("status") == "judged" and _spot_check(comp.case_id):
        return "spot_check"
    return None


def _mentor_decisions(session: Session, case_ids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if case_ids:
        for a in session.scalars(select(HumanAction).where(HumanAction.case_id.in_(case_ids)).order_by(HumanAction.acted_at)):
            if a.payload.get("decision") and a.case_id not in out:
                out[a.case_id] = a.payload
    return out


def queue(session: Session, task_type: TaskType, limit: int = 20) -> dict[str, Any]:
    run = latest_backtest(session, task_type.id)
    if run is None:
        return {"run_id": None, "total": 0, "by_kind": {}, "cards": []}
    rows = session.execute(
        select(Prediction, Comparison, Case).join(Comparison, Comparison.prediction_id == Prediction.id)
        .join(Case, Case.id == Prediction.case_id).where(Prediction.run_id == run.id)
    ).all()
    taught = set(session.scalars(select(Lesson.prediction_id).where(Lesson.prediction_id.in_([p.id for p, _, _ in rows]))))
    order = {"disagreement": 0, "unsure": 1, "spot_check": 2}
    pending = []
    for p, comp, case in rows:
        kind = _kind(comp, p.confidence)
        if kind and p.id not in taught:
            pending.append((order[kind], -utc(case.received_at).timestamp(), kind, p, comp, case))
    pending.sort(key=lambda t: (t[0], t[1]))
    by_kind: dict[str, int] = {}
    for t in pending:
        by_kind[t[2]] = by_kind.get(t[2], 0) + 1
    shown = pending[:limit]
    mentor = _mentor_decisions(session, [t[5].id for t in shown])
    cards = []
    for _, _, kind, p, comp, case in shown:
        snap = case.snapshot or {}
        m = mentor.get(case.id, {})
        cards.append({
            "prediction_id": p.id, "kind": kind,
            "case": {"id": case.id, "received_at": case.received_at, "subject": snap.get("subject", ""), "from": snap.get("from"),
                     "inputs": snap.get("inputs", {})},
            "mentor": {"decision": m.get("decision"), "fields": m.get("fields", {}), "text_outputs": m.get("text_outputs", {}),
                       "note": m.get("note")},
            "agent": {k: (p.output or {}).get(k) for k in ("decision", "fields", "text_outputs", "rationale", "missing_info")},
            "confidence": p.confidence,
            "comparison": {"decision_match": comp.decision_match, "field_scores": comp.field_scores,
                           "text_judgement": comp.text_judgement},
        })
    return {"run_id": run.id, "total": len(pending), "by_kind": by_kind, "cards": cards}


def _prediction_in_org(session: Session, user: User, prediction_id: str) -> tuple[Prediction, Comparison, Case, TaskType]:
    p = session.get(Prediction, prediction_id)
    case = session.get(Case, p.case_id) if p else None
    conn = session.get(Connection, case.connection_id) if case and case.connection_id else None
    if p is None or conn is None or conn.org_id != user.org_id:
        raise LookupError("prediction not found")
    comp = session.scalar(select(Comparison).where(Comparison.prediction_id == p.id))
    if comp is None:
        raise TeachingError("this prediction has nothing to compare against yet")
    return p, comp, case, session.get(TaskType, case.task_type_id)


def record_lesson(session: Session, user: User, prediction_id: str, attribution: str, *, note: str | None = None,
                  reply_ok: bool | None = None, rule_text: str | None = None) -> dict[str, Any]:
    started = time.monotonic()
    if attribution not in ATTRIBUTIONS:
        raise TeachingError(f"attribution must be one of {', '.join(ATTRIBUTIONS)}")
    p, comp, case, task_type = _prediction_in_org(session, user, prediction_id)

    judged = comp.text_judgement.get("status") == "judged"
    if reply_ok is None and judged:
        critical_ok = all(s["match"] for s in comp.field_scores.values() if s.get("critical"))
        if attribution == "both_fine":
            reply_ok = True  # "both fine" includes the reply
        elif attribution == "intern_wrong" and comp.decision_match and critical_ok:
            reply_ok = False  # only the reply was left to be wrong

    lesson = session.scalar(select(Lesson).where(Lesson.prediction_id == p.id))
    if lesson is None:
        lesson = Lesson(case_id=case.id, prediction_id=p.id, attribution=attribution, created_by=user.id)
        session.add(lesson)
    lesson.attribution, lesson.note, lesson.reply_ok = attribution, (note or "").strip() or None, reply_ok
    comp.attribution = attribution
    comp.excluded = attribution == "mentor_changed"

    effect = EFFECTS[attribution]
    repredict = None
    if rule_text and rule_text.strip():
        rule = rules_mod.write(session, task_type, user, rule_text, example_case_id=case.id)
        session.flush()
        lesson.rule_id = rule.id
        agent = session.get(Agent, session.get(Apprenticeship, task_type.apprenticeship_id).agent_id)
        repredict = create_repredict(session, user, task_type, agent, reason=f"new rule: {rule.text[:80]}")
        from app.graduation.engine import on_procedure_change

        on_procedure_change(session, task_type, user, f"new rule: {rule.text[:80]}")
        effect += " Your rule is active; re-predicting your backlog now."
    session.commit()
    remaining = queue(session, task_type, limit=0)["total"]
    return {"lesson_id": lesson.id, "effect": effect, "remaining": remaining, "reply_ok": reply_ok,
            "repredict_run_id": repredict.id if repredict else None, "elapsed_ms": int((time.monotonic() - started) * 1000)}


def summary(session: Session, task_type: TaskType) -> dict[str, Any]:
    run = latest_backtest(session, task_type.id)
    out: dict[str, Any] = {"run_id": run.id if run else None, "predicted": 0, "agreement": None, "lessons": 0,
                           "by_attribution": {}, "queue": 0, "judge": {"compared": 0, "agree": 0, "rate": None, "trusted": False}}
    if run:
        comps = list(session.scalars(select(Comparison).join(Prediction).where(Prediction.run_id == run.id)))
        counted = [c.effective_agreement for c in comps if c.effective_agreement is not None]
        out["predicted"] = len(comps)
        out["agreement"] = round(sum(counted) / len(counted), 4) if counted else None
        out["excluded"] = sum(1 for c in comps if c.excluded)
        out["queue"] = queue(session, task_type, limit=0)["total"]
        lessons = list(session.scalars(select(Lesson).join(Prediction).where(Prediction.run_id == run.id)))
        out["lessons"] = len(lessons)
        for lesson in lessons:
            out["by_attribution"][lesson.attribution] = out["by_attribution"].get(lesson.attribution, 0) + 1
    out["judge"] = judge_agreement(session, task_type)
    rules = list(session.scalars(select(Rule).where(Rule.apprenticeship_id == task_type.apprenticeship_id)))
    out["rules"] = {s: sum(1 for r in rules if r.status == s) for s in ("proposed", "active", "retired")}
    return out


def judge_agreement(session: Session, task_type: TaskType) -> dict[str, Any]:
    """How often the reply judge's verdict matched the mentor's own, across every lesson that rated a reply."""
    rows = session.execute(
        select(Lesson.reply_ok, Comparison.text_judgement).join(Comparison, Comparison.prediction_id == Lesson.prediction_id)
        .join(Case, Case.id == Lesson.case_id).where(Case.task_type_id == task_type.id, Lesson.reply_ok.is_not(None))
    ).all()
    pairs = [(ok, tj.get("acceptable")) for ok, tj in rows if tj.get("status") == "judged"]
    agree = sum(1 for ok, judged in pairs if ok == judged)
    rate = round(agree / len(pairs), 4) if pairs else None
    judges = {tj.get("judge") for _, tj in rows if tj.get("judge")}
    return {"compared": len(pairs), "agree": agree, "rate": rate, "judge": next(iter(judges), None),
            "trusted": bool(rate is not None and len(pairs) >= TRUST_JUDGE_MIN and rate >= TRUST_JUDGE_AT),
            "trust_bar": {"rate": TRUST_JUDGE_AT, "min_lessons": TRUST_JUDGE_MIN}}


def latest_repredict(session: Session, task_type_id: str) -> BacktestRun | None:
    runs = session.scalars(select(BacktestRun).where(BacktestRun.task_type_id == task_type_id)
                           .order_by(BacktestRun.created_at.desc()).limit(20))
    return next((r for r in runs if r.params.get("kind") == "repredict"), None)
