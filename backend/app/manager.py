"""The manager dashboard: what the agents are doing for each team, and what it's worth.

Per team: the approved handbook, task types by stage, cases handled, coverage, hand-back rate,
audit results, and hours returned (cases handled × minutes per case). The cost line compares the
hours returned, at a loaded hourly cost the manager enters, with the agents' running costs.

It never shows anything about the mentor as a person: no override rates, review times or
rankings. Those stay with the mentor (EU rules on evaluating workers).
"""

from datetime import timedelta
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.context import utc
from app.graduation import engine
from app.models import (ActionLog, Agent, Apprenticeship, Audit, BacktestRun, Case, Handbook, HumanAction, Prediction, TaskType,
                        User, utcnow)

PERIOD = timedelta(days=30)
DEFAULT_INTERN_NAME = "Newt"  # each team can rename its intern
DEFAULT_SETTINGS = {"currency": "USD", "usd_rate": 1.0, "hourly_cost": None, "minutes_per_case": None,
                    "intern_name": DEFAULT_INTERN_NAME}


def settings_for(app_: Apprenticeship) -> dict[str, Any]:
    return {**DEFAULT_SETTINGS, **(app_.settings or {})}


def _handled_cases(session: Session, tt: TaskType, since) -> dict[str, int]:
    """Cases where the agent's work was used: acted alone, or drafted and the mentor approved."""
    autonomous = session.scalar(
        select(func.count(func.distinct(ActionLog.case_id))).join(Case, Case.id == ActionLog.case_id)
        .where(Case.task_type_id == tt.id, ActionLog.mode == "autonomous", ActionLog.status == "executed", ActionLog.created_at >= since)
    ) or 0
    supervised = session.scalar(
        select(func.count(func.distinct(HumanAction.case_id))).join(Case, Case.id == HumanAction.case_id)
        .where(Case.task_type_id == tt.id, HumanAction.source == "supervised", HumanAction.acted_at >= since)
    ) or 0
    return {"autonomous": autonomous, "supervised": supervised, "total": autonomous + supervised}


def _time_to_decision_minutes(session: Session, tt: TaskType) -> float | None:
    """Median time from an item arriving to the mentor's decision, in history. Elapsed time, not
    effort: shown for context only; hours returned use the manager's own minutes per case."""
    rows = session.execute(
        select(Case.received_at, func.min(HumanAction.acted_at)).join(HumanAction, HumanAction.case_id == Case.id)
        .where(Case.task_type_id == tt.id, Case.connection_id.is_not(None)).group_by(Case.id)
    ).all()
    gaps = [(utc(a) - utc(r)).total_seconds() / 60 for r, a in rows if a and r and a >= r]
    return round(median(gaps), 1) if gaps else None


def dashboard(session: Session, user: User) -> dict[str, Any]:
    since = utcnow() - PERIOD
    teams = []
    for app_ in session.scalars(select(Apprenticeship).join(Agent).where(Agent.org_id == user.org_id).order_by(Apprenticeship.team)):
        settings = settings_for(app_)
        handbook = session.scalar(select(Handbook).where(Handbook.org_id == user.org_id, Handbook.team == app_.team,
                                                         Handbook.status == "approved").order_by(Handbook.version.desc()).limit(1))
        tasks, handled_total, live_cost = [], 0, 0.0
        for tt in session.scalars(select(TaskType).where(TaskType.apprenticeship_id == app_.id).order_by(TaskType.name)):
            ev = engine.evaluate(session, tt)
            handled = _handled_cases(session, tt, since)
            handled_total += handled["total"]
            live = list(session.scalars(select(Prediction).join(Case, Case.id == Prediction.case_id)
                                        .where(Case.task_type_id == tt.id, Prediction.run_id.is_(None), Prediction.created_at >= since)))
            graduated_live = [p for p in live if (p.output or {}).get("mode") in engine.GRADUATED]
            handed_back = sum(1 for p in graduated_live if ((p.output or {}).get("hand_back") or {}).get("hand_back"))
            live_cost += sum(p.cost_usd for p in live)
            grad = engine.last_graduation(session, tt)
            audits = engine.audits_since(session, tt, utc(grad.signed_at) if grad else None)
            tasks.append({
                "id": tt.id, "name": tt.name, "status": tt.status,
                "handled": handled,
                "coverage": ev["coverage"], "error_upper_bound": ev["ucb"], "alpha": ev["alpha"],
                "hand_back_rate": round(handed_back / len(graduated_live), 4) if graduated_live else None,
                "audits": {"passed": sum(a.result == "pass" for a in audits), "failed": sum(a.result == "fail" for a in audits),
                           "pending": session.scalar(select(func.count()).select_from(Audit).where(Audit.task_type_id == tt.id, Audit.result.is_(None))) or 0},
                "time_to_decision_minutes": _time_to_decision_minutes(session, tt),
            })
        evaluation_cost = session.scalar(
            select(func.coalesce(func.sum(BacktestRun.cost_usd), 0.0)).join(TaskType, TaskType.id == BacktestRun.task_type_id)
            .where(TaskType.apprenticeship_id == app_.id, BacktestRun.created_at >= since)
        ) or 0.0
        minutes = settings["minutes_per_case"]
        hours = round(handled_total * minutes / 60, 1) if minutes else None
        value = round(hours * settings["hourly_cost"], 2) if hours is not None and settings["hourly_cost"] else None
        running = round((live_cost + evaluation_cost) * float(settings["usd_rate"] or 1.0), 2)
        teams.append({
            "team": app_.team,
            "handbook": {"version": handbook.version, "approved_at": handbook.approved_at} if handbook else None,
            "stages": {s: sum(1 for t in tasks if t["status"] == s) for s in ("shadow", "supervised", "autonomous", "demoted")},
            "task_types": tasks,
            "cases_handled": handled_total,
            "hours_returned": hours,
            "value_of_hours": value,
            "running_cost": running,
            "running_cost_usd": {"live": round(live_cost, 2), "evaluation": round(float(evaluation_cost), 2)},
            "net": round(value - running, 2) if value is not None else None,
            "settings": settings,
        })
    return {"period_days": PERIOD.days, "teams": teams}


def update_settings(session: Session, user: User, team: str, changes: dict[str, Any]) -> dict[str, Any]:
    app_ = session.scalar(select(Apprenticeship).join(Agent).where(Agent.org_id == user.org_id, Apprenticeship.team == team))
    if app_ is None:
        raise LookupError("team not found")
    app_.settings = {**settings_for(app_), **{k: v for k, v in changes.items() if k in DEFAULT_SETTINGS}}
    session.commit()
    return settings_for(app_)
