"""Getting better safely: every change is tested on past cases before it goes live.

  propose   a change (a rule added, edited, retired or accepted; a routine changed) is recorded and a replay queued.
            A new rule waits in status "testing", which no agent ever sees.
  execute   in a sandbox that is always rolled back: answer the suite as things stand, make the change, answer it
            again on the same recordings, and compare (`eval/blast.py`). Routine changes replay whole processes.
  promote   the change goes live for real: rules version bumped, backlog re-predicted, re-probation if graduated.
            A mentor's own change that breaks nothing goes live by itself; anything that breaks a past case, or that
            Newt proposed, waits for the mentor, who sees the cases and decides.
  reject    the change is dropped; a testing rule is retired.

The suite: the change's own target cases, the cases it touches (the rule's words, the routine's decision), and a
control sample from the frozen record to catch spill-over.
"""

import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import ContextBuilder, check, utc
from app.agents.output import validate_output
from app.agents.registry import runner_for
from app.agents.replay import recordings_for
from app.eval import blast
from app.eval.score import step_checks
from app.learning import rules as rules_mod
from app.logs import get_logger
from app.models import Agent, Apprenticeship, Case, Improvement, Job, Rule, TaskType, User, utcnow
from app.sim.sandbox import sandbox

log = get_logger("improve")
TOUCHED_MAX = 60
CONTROL = 30
PROCESS_MAX = 20
KINDS = ("add_rule", "edit_rule", "retire_rule", "activate_rule", "routine")


class ImproveError(ValueError):
    pass


def _agent(session: Session, tt: TaskType) -> Agent:
    return session.get(Agent, session.get(Apprenticeship, tt.apprenticeship_id).agent_id)


def summary_of(kind: str, rule: Rule | None, candidate: dict[str, Any]) -> str:
    if kind == "add_rule" or kind == "activate_rule":
        return f"New rule: {candidate.get('text') or (rule.text if rule else '')}"
    if kind == "edit_rule":
        return f"Edit rule: {candidate['text']}"
    if kind == "retire_rule":
        return f"Retire rule: {rule.text if rule else ''}"
    steps = ", ".join(s.replace("_", " ") for s in candidate.get("steps", [])) or "no actions"
    fu = f", follow up after {candidate['follow_up_days']} days" if candidate.get("follow_up_days") else ""
    return f"Routine for {candidate['decision'].replace('_', ' ')}: {steps}{fu}"


def propose(session: Session, tt: TaskType, user: User | None, kind: str, *, rule: Rule | None = None, text: str | None = None,
            decision: str | None = None, steps: list[str] | None = None, follow_up_days: int | None = None,
            source: str = "mentor", signal: str = "taught", targets: list[str] | None = None) -> Improvement:
    """Record a change and queue its replay. Doesn't commit: it rides on the caller's change."""
    if kind not in KINDS:
        raise ImproveError("unknown kind of change")
    candidate: dict[str, Any] = {"targets": list(targets or [])}
    if kind == "add_rule":
        if not text:
            raise ImproveError("a rule needs its text")
        rule = rules_mod.write(session, tt, user, text, example_case_id=(targets or [None])[0] if signal == "lesson" else None,
                               status="testing")
        session.flush()
        candidate["text"] = rule.text
    elif kind == "edit_rule":
        if rule is None or not text:
            raise ImproveError("an edit needs the rule and its new text")
        candidate["text"] = text.strip()
    elif kind in ("retire_rule", "activate_rule"):
        if rule is None:
            raise ImproveError("which rule?")
        candidate["text"] = rule.text
    else:
        if decision is None:
            raise ImproveError("a routine belongs to a decision")
        candidate.update(decision=decision, steps=list(steps or []), follow_up_days=follow_up_days)
    imp = Improvement(task_type_id=tt.id, kind=kind, rule_id=rule.id if rule else None, candidate=candidate,
                      summary=summary_of(kind, rule, candidate)[:500], source=source, signal=signal, status="testing",
                      blast={}, proposed_by=user.id if user else None)
    session.add(imp)
    session.flush()
    session.add(Job(type="improvement_replay", payload={"improvement_id": imp.id}))
    return imp


# The change itself, applied in the sandbox for the replay and for real on promotion -------------------

def apply(session: Session, tt: TaskType, imp: Improvement, user: User | None) -> bool:
    """Make the change. Returns True when what the agent uses changed (rules version bumped)."""
    rule = session.get(Rule, imp.rule_id) if imp.rule_id else None
    if imp.kind in ("add_rule", "activate_rule"):
        return rules_mod.update(session, tt, rule, text=None, status="active")
    if imp.kind == "edit_rule":
        return rules_mod.update(session, tt, rule, text=imp.candidate["text"], status=None)
    if imp.kind == "retire_rule":
        return rules_mod.update(session, tt, rule, text=None, status="retired")
    from app.execution import routines

    c = imp.candidate
    routines.approve(session, user or session.get(User, imp.proposed_by), tt, c["decision"], c["steps"], c.get("follow_up_days"),
                     recertify=False)
    return False


# The suite ------------------------------------------------------------------------------------------

def _text(case: Case) -> str:
    snap = case.snapshot or {}
    return " ".join([snap.get("subject", ""), *[str(v) for v in (snap.get("inputs") or {}).values()]])


def suite(session: Session, tt: TaskType, imp: Improvement, builder: ContextBuilder) -> list[str]:
    task = builder.task
    decided = [cid for cid in builder.decided]
    targets = [c for c in imp.candidate.get("targets", []) if c in builder.decided]
    texts = [imp.candidate.get("text") or ""]
    if imp.kind == "edit_rule" and imp.rule_id:
        texts.append(session.get(Rule, imp.rule_id).text)  # both what it said and what it will say
    parsed = [rules_mod.parse(t, task) for t in texts if t]
    touched = [cid for cid in reversed(decided) if any(p.matches(_text(builder.cases[cid])) for p in parsed)][:TOUCHED_MAX]
    from app.graduation.engine import frozen_case_ids

    frozen = [c for c in frozen_case_ids(session, tt) if c in builder.decided]
    rng = random.Random(imp.id)  # the same change always gets the same control sample
    pool = [c for c in (frozen or decided) if c not in set(targets) | set(touched)]
    control = rng.sample(pool, min(CONTROL, len(pool)))
    return list(dict.fromkeys([*targets, *touched, *control]))


def _answers(s: Session, tt: TaskType, ids: list[str], recordings: dict[str, Any]) -> tuple[dict[str, blast.Answer], ContextBuilder]:
    builder = ContextBuilder(s, tt)
    builder.enable_tools(live=False, recordings=recordings)
    runner = runner_for(_agent(s, tt))
    task = builder.task
    out: dict[str, blast.Answer] = {}
    for cid in ids:
        case = builder.cases[cid]
        ctx = builder.build(case)
        check(ctx, builder.forbidden(case))
        try:
            result = runner.predict(ctx)
            output = validate_output(result.output, task).model_dump() if result.output is not None else None
        except Exception:  # an agent error is a wrong answer here, never a crash
            output, result = None, None
        decision = (output or {}).get("decision")
        out[cid] = blast.Answer(decision, step_checks(task, result.trajectory if result else None, decision)["ok"])
    return out, builder


def _rule_blast(session: Session, tt: TaskType, imp: Improvement) -> dict[str, Any]:
    ids = suite(session, tt, imp, ContextBuilder(session, tt))
    recordings = recordings_for(session, ids)
    session.commit()  # the sandbox writes on its own connection
    with sandbox(session) as s:
        stt = s.get(TaskType, tt.id)
        before, builder = _answers(s, stt, ids, recordings)
        apply(s, stt, s.get(Improvement, imp.id), None)
        s.commit()
        after, _ = _answers(s, s.get(TaskType, tt.id), ids, recordings)
        rows = [{"case_id": cid, "subject": (builder.cases[cid].snapshot or {}).get("subject", ""),
                 "truth": builder.decided[cid].decision if cid in builder.decided else None,
                 "before": before[cid], "after": after[cid]} for cid in ids]
    return blast.radius(rows)


def _routine_blast(session: Session, tt: TaskType, imp: Improvement) -> dict[str, Any]:
    """A routine changes what Newt does over days, so the replay is of whole processes for that decision."""
    from app.sim.replay import _threshold, replay_case
    from app.sim.scenario import scenarios

    decision = imp.candidate["decision"]
    scen = [sc for sc in scenarios(session, tt, PROCESS_MAX * 3) if sc.team.decision == decision][:PROCESS_MAX]
    recordings = recordings_for(session, [sc.case_id for sc in scen])
    calibration, tau, _ = _threshold(session, tt)
    session.commit()
    rows = []
    for sc in scen:
        rec = recordings.get(sc.case_id, {})
        before = replay_case(session, tt.id, sc, rec, calibration, tau)
        after = replay_case(session, tt.id, sc, rec, calibration, tau,
                            prepare=lambda s, stt: apply(s, stt, s.get(Improvement, imp.id), None))
        good = "like_team"
        rows.append({"case_id": sc.case_id, "subject": sc.subject, "truth": good,
                     "before": blast.Answer(before["verdict"]), "after": blast.Answer(after["verdict"]),
                     "reasons_after": after["reasons"]})
    b = blast.radius(rows)
    return {**b, "unit": "processes"}


def execute(session: Session, improvement_id: str) -> Improvement:
    imp = session.get(Improvement, improvement_id)
    if imp is None or imp.status != "testing":
        return imp
    tt = session.get(TaskType, imp.task_type_id)
    try:
        imp.blast = _routine_blast(session, tt, imp) if imp.kind == "routine" else _rule_blast(session, tt, imp)
        imp.status = "ready"
        session.commit()
    except Exception as exc:
        session.rollback()
        imp = session.get(Improvement, improvement_id)
        imp.status, imp.error = "failed", f"{type(exc).__name__}: {str(exc)[:300]}"
        session.commit()
        log.exception("improvement %s replay failed", improvement_id)
        return imp
    from app.colleague import service as colleague

    if imp.source == "mentor" and not imp.blast.get("broke"):
        promote(session, None, imp)
        colleague.tell_improvement(session, tt, imp, live=True)
    else:
        colleague.tell_improvement(session, tt, imp, live=False)
    return imp


def promote(session: Session, user: User | None, imp: Improvement, *, keep_anyway: bool = False) -> Improvement:
    if imp.status != "ready":
        raise ImproveError("only a tested change can go live")
    if imp.blast.get("broke") and not keep_anyway:
        raise ImproveError(f"it would change {imp.blast['broke']} past cases the team decided differently; keep it anyway?")
    tt = session.get(TaskType, imp.task_type_id)
    actor = user or (session.get(User, imp.proposed_by) if imp.proposed_by else None)
    changed = apply(session, tt, imp, actor)
    imp.status, imp.decided_by, imp.decided_at = "promoted", actor.id if actor else None, utcnow()
    from app.backtest.runner import create_repredict
    from app.graduation.engine import on_procedure_change

    reason = imp.summary[:100]
    if changed:
        run = create_repredict(session, actor, tt, _agent(session, tt), reason=reason)
        imp.repredict_run_id = run.id if run else None
    on_procedure_change(session, tt, actor, reason)
    session.commit()
    return imp


def reject(session: Session, user: User, imp: Improvement) -> Improvement:
    if imp.status not in ("testing", "ready", "failed"):
        raise ImproveError("that change has already been decided")
    if imp.kind == "add_rule" and imp.rule_id:
        session.get(Rule, imp.rule_id).status = "retired"
    imp.status, imp.decided_by, imp.decided_at = "rejected", user.id if user else None, utcnow()
    session.commit()
    return imp


def out(imp: Improvement) -> dict[str, Any]:
    return {"id": imp.id, "task_type_id": imp.task_type_id, "kind": imp.kind, "rule_id": imp.rule_id, "summary": imp.summary,
            "source": imp.source, "signal": imp.signal, "status": imp.status, "blast": imp.blast,
            "sentence": blast.sentence(imp.blast) if imp.blast.get("cases") is not None else None,
            "repredict_run_id": imp.repredict_run_id, "error": imp.error,
            "created_at": utc(imp.created_at).isoformat(), "decided_at": utc(imp.decided_at).isoformat() if imp.decided_at else None}


def log_of(session: Session, tt: TaskType, limit: int = 50) -> list[dict[str, Any]]:
    """The change log: every change, newest first, with what it did to past cases."""
    return [out(i) for i in session.scalars(select(Improvement).where(Improvement.task_type_id == tt.id)
                                            .order_by(Improvement.created_at.desc()).limit(limit))]
