from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import registry
from app.agents.external import EndpointError
from app.auth import current_user, require_role
from app.backtest import runner
from app.capture.service import org_task_type
from app.db import get_session
from app.models import Agent, Apprenticeship, BacktestRun, Case, Comparison, HumanAction, Prediction, TaskType, User

router = APIRouter(tags=["agents and backtests"])

operator = require_role("mentor", "manager", "admin")
mentor = require_role("mentor", "admin")  # case-level results show captured content


def _task_type(session: Session, user: User, task_type_id: str) -> TaskType:
    try:
        return org_task_type(session, user.org_id, task_type_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _agent(session: Session, user: User, agent_id: str | None, task_type: TaskType) -> Agent:
    if agent_id is None:  # default: the apprenticeship's own agent
        return session.get(Agent, session.get(Apprenticeship, task_type.apprenticeship_id).agent_id)
    agent = session.get(Agent, agent_id)
    if agent is None or agent.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    return agent


@router.get("/agents")
def list_agents(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [registry.agent_out(a) for a in registry.org_agents(session, user.org_id)]


class NewAgent(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    endpoint: str = Field(min_length=8, max_length=500)
    version: str = Field(min_length=1, max_length=50)
    model: str = Field(default="", max_length=100)


@router.post("/agents", status_code=status.HTTP_201_CREATED)
def create_agent(body: NewAgent, user: User = Depends(operator), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        agent, secret = registry.create_external(session, user, name=body.name, endpoint=body.endpoint,
                                                 version=body.version, model=body.model)
    except EndpointError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {**registry.agent_out(agent), "signing_secret": secret}  # shown once


@router.get("/backtests/estimate")
def estimate(task_type_id: str, agent_id: str | None = None, limit: int = Query(default=300, ge=1, le=5000),
             user: User = Depends(operator), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _task_type(session, user, task_type_id)
    return runner.estimate(session, tt, _agent(session, user, agent_id, tt), limit)


class NewBacktest(BaseModel):
    task_type_id: str
    agent_id: str | None = None
    limit: int = Field(default=300, ge=1, le=5000)
    date_from: str | None = None
    date_to: str | None = None


def _run_out(run: BacktestRun, agent: Agent | None = None) -> dict[str, Any]:
    return {
        "id": run.id, "task_type_id": run.task_type_id, "agent_id": run.agent_id,
        "agent_name": registry.agent_out(agent)["name"] if agent else None,
        "status": run.status, "params": run.params, "model": run.model, "agent_version": run.agent_version,
        "handbook_version": run.handbook_version, "progress": run.progress, "stats": run.stats,
        "cost_usd": run.cost_usd, "error": run.error, "created_at": run.created_at,
        "started_at": run.started_at, "finished_at": run.finished_at,
    }


@router.post("/backtests", status_code=status.HTTP_201_CREATED)
def create_backtest(body: NewBacktest, user: User = Depends(operator), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _task_type(session, user, body.task_type_id)
    agent = _agent(session, user, body.agent_id, tt)
    try:
        run = runner.create_run(session, user, tt, agent, limit=body.limit, date_from=body.date_from, date_to=body.date_to)
    except runner.BacktestError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _run_out(run, agent)


@router.get("/backtests")
def list_backtests(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    _task_type(session, user, task_type_id)
    rows = session.execute(
        select(BacktestRun, Agent).join(Agent).where(BacktestRun.task_type_id == task_type_id)
        .order_by(BacktestRun.created_at.desc()).limit(100)
    ).all()
    return [_run_out(r, a) for r, a in rows if r.params.get("kind") != "repredict"][:50]


def _load_run(session: Session, user: User, run_id: str) -> BacktestRun:
    run = session.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backtest not found")
    _task_type(session, user, run.task_type_id)  # org check
    return run


@router.get("/backtests/{run_id}")
def get_backtest(run_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    run = _load_run(session, user, run_id)
    return _run_out(run, session.get(Agent, run.agent_id))


@router.get("/backtests/{run_id}/cases")
def backtest_cases(run_id: str, only: str = Query(default="disagreements", pattern="^(all|disagreements|handed_back)$"),
                   limit: int = Query(default=50, le=500), offset: int = 0,
                   user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    run = _load_run(session, user, run_id)
    q = (select(Prediction, Comparison, Case).join(Case, Prediction.case_id == Case.id)
         .outerjoin(Comparison, Comparison.prediction_id == Prediction.id).where(Prediction.run_id == run.id))
    if only == "disagreements":
        q = q.where(Comparison.agreement.is_(False))
    elif only == "handed_back":
        q = q.where(Comparison.id.is_(None))
    rows = session.execute(q.order_by(Case.received_at).limit(limit).offset(offset)).all()
    decisions = {}
    if rows:
        for a in session.scalars(select(HumanAction).where(HumanAction.case_id.in_([c.id for _, _, c in rows])).order_by(HumanAction.acted_at)):
            if a.payload.get("decision") and a.case_id not in decisions:
                decisions[a.case_id] = a.payload
    return {"items": [
        {
            "case_id": c.id, "received_at": c.received_at, "subject": (c.snapshot or {}).get("subject", ""),
            "mentor": {"decision": decisions.get(c.id, {}).get("decision"), "fields": decisions.get(c.id, {}).get("fields", {}),
                       "text_outputs": decisions.get(c.id, {}).get("text_outputs", {})},
            "agent": p.output, "confidence": p.confidence, "error": p.error,
            "agreement": comp.agreement if comp else None, "field_scores": comp.field_scores if comp else {},
        }
        for p, comp, c in rows
    ]}
