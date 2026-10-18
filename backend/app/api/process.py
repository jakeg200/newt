from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.context import utc
from app.api.backtest import _task_type, operator
from app.auth import current_user
from app.db import get_session
from app.models import BacktestRun, User
from app.sim import replay

router = APIRouter(tags=["process replays"])
CASE_ROLES = ("mentor", "admin")  # per-case timelines show captured (redacted) content


class NewReplay(BaseModel):
    limit: int = Field(default=replay.DEFAULT_SCENARIOS, ge=1, le=200)


def _out(run: BacktestRun, user: User) -> dict[str, Any]:
    stats = run.stats or {}
    show_cases = user.role in CASE_ROLES
    return {"id": run.id, "status": run.status, "progress": run.progress, "error": run.error,
            "created_at": utc(run.created_at).isoformat(), "finished_at": utc(run.finished_at).isoformat() if run.finished_at else None,
            "summary": stats.get("summary"), "threshold": stats.get("threshold"), "duration_s": stats.get("duration_s"),
            "simulated_days": stats.get("simulated_days"),
            "results": stats.get("results", []) if show_cases else None}


@router.post("/task-types/{task_type_id}/process-replays", status_code=status.HTTP_201_CREATED)
def start(task_type_id: str, body: NewReplay | None = None, user: User = Depends(operator),
          session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _task_type(session, user, task_type_id)
    run = replay.create(session, user, tt, (body or NewReplay()).limit)
    session.commit()
    return _out(run, user)


@router.get("/task-types/{task_type_id}/process-replays/latest")
def latest(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any] | None:
    tt = _task_type(session, user, task_type_id)
    run = replay.latest(session, tt)
    return _out(run, user) if run else None


@router.get("/process-replays/{run_id}")
def get(run_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    run = session.get(BacktestRun, run_id)
    if run is None or (run.params or {}).get("kind") != "process":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "replay not found")
    _task_type(session, user, run.task_type_id)  # org check
    return _out(run, user)
