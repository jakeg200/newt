"""Doing the work: where Newt carries out actions, how (routines), confirmations, outcomes and its career."""

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user, require_role
from app.capture.service import org_task_type
from app.colleague import career
from app.db import get_session
from app.execution import destinations, routines
from app.execution import service as execution
from app.execution.executor import SIGNATURE_HEADER
from app.models import Apprenticeship, Destination, TaskType, User
from app.outcomes.kpis import outcomes

router = APIRouter(tags=["execution"])
operator = require_role("mentor", "manager", "admin")
mentor = require_role("mentor", "admin")
manager = require_role("manager", "admin")


def _tt(session: Session, user: User, task_type_id: str) -> TaskType:
    try:
        return org_task_type(session, user.org_id, task_type_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/destinations")
def list_destinations(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    tt = _tt(session, user, task_type_id)
    return [destinations.out(d) for d in session.scalars(select(Destination).where(Destination.task_type_id == tt.id).order_by(Destination.created_at))]


class DestinationIn(BaseModel):
    task_type_id: str
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8, max_length=500)
    actions: list[str] = Field(min_length=1)


@router.post("/destinations", status_code=status.HTTP_201_CREATED)
def add_destination(body: DestinationIn, user: User = Depends(operator), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _tt(session, user, body.task_type_id)
    try:
        d, secret = destinations.create(session, user, tt, body.name, body.url, body.actions)
    except destinations.DestinationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {**destinations.out(d), "secret": secret}  # shown once


def _destination(session: Session, user: User, destination_id: str) -> Destination:
    d = session.get(Destination, destination_id)
    if d is None or d.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "destination not found")
    return d


@router.post("/destinations/{destination_id}/test")
def test_destination(destination_id: str, user: User = Depends(operator), session: Session = Depends(get_session)) -> dict[str, Any]:
    return destinations.test(session, _destination(session, user, destination_id))


class DestinationPatch(BaseModel):
    status: Literal["active", "paused"]


@router.patch("/destinations/{destination_id}")
def update_destination(destination_id: str, body: DestinationPatch, user: User = Depends(operator), session: Session = Depends(get_session)) -> dict[str, Any]:
    d = _destination(session, user, destination_id)
    d.status = body.status
    session.commit()
    return destinations.out(d)


@router.post("/execution/callback/{action_id}")
async def confirm(action_id: str, request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    """A system confirms an action it carried out (or couldn't). Signed with the destination's secret."""
    raw = await request.body()
    if action_id == "test":
        return {"ok": True}
    try:
        body = json.loads(raw or b"{}")
        result = execution.callback(session, action_id, raw, request.headers.get(SIGNATURE_HEADER), body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body must be JSON") from exc
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return {"status": result}


@router.get("/task-types/{task_type_id}/routines")
def get_routines(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    return routines.current(session, _tt(session, user, task_type_id))


class RoutineIn(BaseModel):
    steps: list[str]
    follow_up_days: int | None = Field(default=None, ge=1, le=60)


@router.put("/task-types/{task_type_id}/routines/{decision}")
def set_routine(task_type_id: str, decision: str, body: RoutineIn, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _tt(session, user, task_type_id)
    try:
        if routines.is_live(session, tt, decision):  # changing live work: replay the processes first
            from app.learning import improve

            routines.validate(tt, decision, body.steps, body.follow_up_days)
            imp = improve.propose(session, tt, user, "routine", decision=decision, steps=body.steps,
                                  follow_up_days=body.follow_up_days, signal="routine")
            session.commit()
            return {**routines.current(session, tt).get(decision, {}), "status": "testing", "improvement": improve.out(imp)}
        return routines.approve(session, user, tt, decision, body.steps, body.follow_up_days)
    except routines.RoutineError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/task-types/{task_type_id}/outcomes")
def get_outcomes(task_type_id: str, weeks: int = 8, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    return outcomes(session, _tt(session, user, task_type_id), weeks=max(2, min(weeks, 26)))


@router.put("/task-types/{task_type_id}/kpi-targets")
def set_kpi_targets(task_type_id: str, body: dict[str, float | None], user: User = Depends(manager), session: Session = Depends(get_session)) -> dict[str, Any]:
    from app.task_types import KPI_METRICS

    tt = _tt(session, user, task_type_id)
    unknown = sorted(set(body) - set(KPI_METRICS))
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown metrics: {', '.join(unknown)}")
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    settings = dict(app_.settings or {})
    targets = {k: dict(v) for k, v in settings.get("kpi_targets", {}).items()}
    targets[tt.id] = {**targets.get(tt.id, {}), **body}
    app_.settings = {**settings, "kpi_targets": targets}
    session.commit()
    return targets[tt.id]


@router.get("/task-types/{task_type_id}/career")
def get_career(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _tt(session, user, task_type_id)
    r = career.rank(session, tt)
    return {"rank": r, "title": career.TITLES[r], "ladder": [{"rank": k, "title": career.TITLES[k]} for k in career.RANKS],
            "responsibilities": career.responsibilities(session, tt), "process": career.process_evidence(session, tt)[1]}
