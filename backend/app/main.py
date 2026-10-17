from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import capture, orientation
from app.auth import current_user
from app.config import get_settings
from app.db import get_session
from app.logs import configure_logging
from app.models import Apprenticeship, Agent, Org, TaskType, User
from app.task_types import load_all

configure_logging()
app = FastAPI(title="Agent Onboarding API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(orientation.router)
app.include_router(capture.router)


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
    rows = session.execute(
        select(TaskType, Apprenticeship.team)
        .join(Apprenticeship, TaskType.apprenticeship_id == Apprenticeship.id)
        .join(Agent, Apprenticeship.agent_id == Agent.id)
        .where(Agent.org_id == user.org_id)
        .order_by(TaskType.name)
    ).all()
    return [
        {"id": t.id, "name": t.name, "team": team, "status": t.status, "tau": t.tau,
         "inputs": t.config.get("inputs", []), "decision": t.config.get("decision", [])}
        for t, team in rows
    ]


@app.get("/dev/users")
def dev_users(session: Session = Depends(get_session)) -> list[dict]:
    """Lets the web app's user picker stand in for sign-in. Development only."""
    if get_settings().env != "dev":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rows = session.execute(select(User, Org).join(Org).order_by(Org.name, User.role, User.name)).all()
    return [{"id": u.id, "name": u.name, "role": u.role, "email": u.email, "org": o.name} for u, o in rows]
