from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.config import get_settings
from app.db import get_session
from app.models import Apprenticeship, Agent, TaskType, User
from app.task_types import load_all

app = FastAPI(title="Agent Onboarding API", version="0.0.1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/task-type-configs")
def task_type_configs() -> dict:
    """Configs on disk, validated. Adding a file here needs no code change."""
    configs = load_all(get_settings().task_types_dir)
    return {key: cfg.model_dump(mode="json") for key, cfg in configs.items()}


@app.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "name": user.name, "role": user.role, "org_id": user.org_id}


@app.get("/task-types")
def task_types(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.scalars(
        select(TaskType)
        .join(Apprenticeship, TaskType.apprenticeship_id == Apprenticeship.id)
        .join(Agent, Apprenticeship.agent_id == Agent.id)
        .where(Agent.org_id == user.org_id)
        .order_by(TaskType.name)
    ).all()
    return [{"id": t.id, "name": t.name, "status": t.status, "tau": t.tau} for t in rows]
