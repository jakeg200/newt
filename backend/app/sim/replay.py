"""Process replays: past cases run end to end with Newt in the team's place, as if it were trusted to carry them.

For each scenario, in a sandbox that is always rolled back:
  1. the case is put back as it arrived (the team's own actions on it are removed: Newt stands in for them),
  2. the clock is set to the moment it arrived,
  3. Newt predicts and acts through the same code as live work (`live.predict_one`, policy, executor),
  4. the jobs that follow (confirmations, follow-ups, chases) run in simulated-time order, with the director standing
     in for the firm's system, until the scenario's horizon,
  5. Newt's timeline is scored against the team's (`eval/process.py`).

Lookups answer only from recordings, and follow-ups only see thread replies once the clock reaches them, so a replay
never knows anything Newt couldn't have known at that moment.
"""

import time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import clock
from app.agents.context import ContextBuilder, LeakageError, utc
from app.agents.registry import runner_for
from app.agents.replay import recordings_for
from app.eval import process
from app.eval.calibration import Calibrator
from app.eval.score import step_checks
from app.execution import service as execution
from app.live import decision_model, predict_one
from app.logs import get_logger
from app.models import ActionLog, Agent, Apprenticeship, BacktestRun, Case, HumanAction, Job, TaskType, User, utcnow
from app.sim.director import Director
from app.sim.sandbox import sandbox
from app.sim.scenario import Scenario, scenarios
from app.task_types import TaskTypeConfig

log = get_logger("sim")
DEFAULT_SCENARIOS = 50
MAX_JOBS = 200


class ReplayError(ValueError):
    pass


def create(session: Session, user: User | None, tt: TaskType, limit: int = DEFAULT_SCENARIOS) -> BacktestRun:
    agent = session.get(Agent, session.get(Apprenticeship, tt.apprenticeship_id).agent_id)
    run = BacktestRun(task_type_id=tt.id, agent_id=agent.id, requested_by=user.id if user else None, status="queued",
                      params={"kind": "process", "limit": limit}, agent_version=agent.version, model=agent.model or "",
                      config_hash=tt.config_hash)
    session.add(run)
    session.flush()
    session.add(Job(type="process_replay", payload={"run_id": run.id}))
    return run


def latest(session: Session, tt: TaskType) -> BacktestRun | None:
    runs = session.scalars(select(BacktestRun).where(BacktestRun.task_type_id == tt.id).order_by(BacktestRun.created_at.desc()).limit(50))
    return next((r for r in runs if (r.params or {}).get("kind") == "process"), None)


def _threshold(session: Session, tt: TaskType) -> tuple[dict[str, Any], float, str]:
    """Replay as if trusted: at the graduated threshold, or the one today's evidence supports, or (with no evidence
    yet) with every answer let through, which the result says plainly."""
    if tt.tau is not None:
        return tt.calibration or {}, tt.tau, "graduated"
    from app.graduation.engine import evaluate

    ev = evaluate(session, tt)
    if ev.get("tau") is not None:
        return ev["calibration"], ev["tau"], "current evidence"
    return ev.get("calibration") or {}, 0.0, "none yet"


def _drain(s: Session, clk: clock.SimClock, sc: Scenario, before: set[str]) -> None:
    """Run the scenario's jobs in simulated-time order until its horizon."""
    for _ in range(MAX_JOBS):
        job = next((j for j in s.scalars(select(Job).where(Job.status == "queued").order_by(Job.run_at)) if j.id not in before), None)
        if job is None or utc(job.run_at) > sc.horizon:
            return
        clk.advance_to(utc(job.run_at))
        job.status = "done"
        s.commit()
        if job.type == "execute_action":
            execution.run(s, job.payload["action_id"])
        elif job.type == "follow_up":
            execution.follow_up(s, job.payload["case_id"], job.payload["since"])


def replay_case(session: Session, tt_id: str, sc: Scenario, recording: dict[str, Any], calibration: dict[str, Any],
                tau: float) -> dict[str, Any]:
    with sandbox(session) as s:
        tt = s.get(TaskType, tt_id)
        task = TaskTypeConfig.model_validate(tt.config)
        app_ = s.get(Apprenticeship, tt.apprenticeship_id)
        agent = s.get(Agent, app_.agent_id)
        case = s.get(Case, sc.case_id)
        s.execute(delete(HumanAction).where(HumanAction.case_id == case.id))  # Newt stands in for the team
        s.execute(delete(ActionLog).where(ActionLog.case_id == case.id))
        case.status, case.completed_at = "open", None
        tt.status = "autonomous"  # as if trusted to carry it alone, follow-ups included
        settings = dict(app_.settings or {})
        resp = dict(settings.get("responsibilities", {}))
        resp[tt.id] = {**resp.get(tt.id, {}), "follow_ups": True}
        app_.settings = {**settings, "responsibilities": resp}
        before = set(s.scalars(select(Job.id).where(Job.status == "queued")))
        s.commit()

        with clock.simulated(sc.received_at) as clk:
            director = Director(clk)
            token = execution.executor_override.set(director)
            try:
                builder = ContextBuilder(s, tt)
                builder.enable_tools(live=False, recordings={case.id: recording})
                p = predict_one(s, tt, task, agent, builder, runner_for(agent), Calibrator.load(calibration),
                                decision_model(builder, sc.received_at), case, mode="autonomous", tau=tau)
                s.commit()
                _drain(s, clk, sc, before)
            finally:
                execution.executor_override.reset(token)

        out = p.output or {}
        hb = out.get("hand_back") or {}
        logs = list(s.scalars(select(ActionLog).where(ActionLog.case_id == case.id)))
        first = [r for r in logs if not (r.payload or {}).get("follow_up")]
        newt = process.NewtTimeline(
            decision=out.get("decision"), handed_back=bool(hb.get("hand_back")),
            steps_ok=step_checks(task, p.trajectory, out.get("decision"))["ok"],
            policy_ok=not any(r.status == "blocked" for r in logs),
            replied=any(r.action in ("send_reply", "draft_reply") and r.exec_status == "done" for r in first),
            done_at=utc(case.completed_at) if case.completed_at else None,
            chases=tuple(sorted(utc(r.completed_at) for r in logs if (r.payload or {}).get("follow_up") and r.completed_at)),
            reasons=tuple(hb.get("reasons") or ()))
        verdict = process.score(sc.team, newt, sc.follow_up_days)
        newt_events = [{"at": sc.received_at, "who": "newt",
                        "what": f"handed it back: {'; '.join(hb.get('reasons') or [])[:160]}" if newt.handed_back
                        else f"decided {str(out.get('decision') or '').replace('_', ' ')}",
                        "steps": [st.get("tool") for st in (p.trajectory or [])]}]
        for e in director.events:
            off = (e["follow_up"] and not sc.team.chased) or (e["action"] in ("send_reply", "draft_reply") and not e["follow_up"] and not sc.team.replied)
            newt_events.append({"at": e["at"], "who": "newt", "what": e["what"], "off_script": off})

    def stamp(e: dict[str, Any]) -> dict[str, Any]:
        return {**e, "at": e["at"].isoformat(), "day": round((e["at"] - sc.received_at).total_seconds() / 86400, 2)}

    timeline = sorted([*sc.events, *newt_events], key=lambda e: (e["at"], e["who"] != "world"))
    return {"case_id": sc.case_id, "subject": sc.subject, "decision": out.get("decision"), "team_decision": sc.team.decision,
            "follow_up_days": sc.follow_up_days, **verdict, "timeline": [stamp(e) for e in timeline]}


def execute(session: Session, run_id: str) -> BacktestRun:
    run = session.get(BacktestRun, run_id)
    if run is None:
        raise ReplayError("run not found")
    run.status, run.started_at, run.error = "running", utcnow(), None
    session.commit()
    started = time.monotonic()
    try:
        tt = session.get(TaskType, run.task_type_id)
        scen = scenarios(session, tt, int(run.params.get("limit") or DEFAULT_SCENARIOS))
        recordings = recordings_for(session, [sc.case_id for sc in scen])
        calibration, tau, source = _threshold(session, tt)
        run.progress = {"done": 0, "total": len(scen)}
        session.commit()  # the sandbox writes on its own connection: nothing of ours may be pending
        results = []
        for n, sc in enumerate(scen, start=1):
            results.append(replay_case(session, tt.id, sc, recordings.get(sc.case_id, {}), calibration, tau))
            run.progress = {"done": n, "total": len(scen)}
            session.commit()
        run.stats = {"summary": process.summarize(results), "threshold": {"tau": tau, "source": source},
                     "duration_s": round(time.monotonic() - started, 2), "results": results,
                     "simulated_days": round(sum((sc.horizon - sc.received_at).total_seconds() for sc in scen) / 86400, 1)}
        run.status, run.finished_at = "done", utcnow()
        session.commit()
        log.info("process replay %s: %d scenarios in %.1fs", run.id, len(results), time.monotonic() - started)
    except LeakageError as exc:
        session.rollback()
        run = session.get(BacktestRun, run_id)
        run.status, run.finished_at, run.error = "failed", utcnow(), f"Time-travel guard: {exc}"
        session.commit()
    except Exception as exc:
        session.rollback()
        run = session.get(BacktestRun, run_id)
        run.status, run.finished_at, run.error = "failed", utcnow(), f"{type(exc).__name__}: {str(exc)[:300]}"
        session.commit()
        log.exception("process replay %s failed", run_id)
    return run


def pass_rate(session: Session, tt: TaskType) -> dict[str, Any] | None:
    """The latest replay's headline, as evidence beside the statistical gate (never instead of it)."""
    run = latest(session, tt)
    if run is None or run.status != "done":
        return None
    return {"run_id": run.id, "at": utc(run.finished_at).isoformat() if run.finished_at else None, **(run.stats or {}).get("summary", {})}

