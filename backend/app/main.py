from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api import backtest, capture, graduation, manager, orientation, teaching
from app.auth import current_user
from app.config import get_settings
from app.db import get_engine, get_session
from app.logs import configure_logging
from app.manager import DEFAULT_INTERN_NAME
from app.models import Apprenticeship, Agent, Org, TaskType, User
from app.task_types import load_all

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    worker = None
    if get_settings().inline_worker:
        from app.worker import InlineWorker

        worker = InlineWorker(sessionmaker(bind=get_engine(), expire_on_commit=False))
        worker.start()
    yield
    if worker:
        worker.stop()


app = FastAPI(title="Agent Onboarding API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(orientation.router)
app.include_router(capture.router)
app.include_router(backtest.router)
app.include_router(teaching.router)
app.include_router(graduation.router)
app.include_router(manager.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/task-type-configs")
def task_type_configs() -> dict:
    """Configs on disk, validated. Adding a file here needs no code change."""
    configs = load_all(get_settings().task_types_dir)
    return {key: cfg.model_dump(mode="json") for key, cfg in configs.items()}


@app.get("/me")
def me(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    org = session.get(Org, user.org_id)
    return {"id": user.id, "name": user.name, "role": user.role, "email": user.email, "org_id": user.org_id,
            "org": org.name if org else None, "synthetic": bool(org and org.is_synthetic)}


@app.get("/task-types")
def task_types(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(
        select(TaskType, Apprenticeship.team, Apprenticeship.settings)
        .join(Apprenticeship, TaskType.apprenticeship_id == Apprenticeship.id)
        .join(Agent, Apprenticeship.agent_id == Agent.id)
        .where(Agent.org_id == user.org_id)
        .order_by(TaskType.name)
    ).all()
    return [
        {"id": t.id, "name": t.name, "team": team, "status": t.status, "tau": t.tau,
         "inputs": t.config.get("inputs", []), "decision": t.config.get("decision", []),
         "intern_name": (settings or {}).get("intern_name") or DEFAULT_INTERN_NAME}
        for t, team, settings in rows
    ]


@app.get("/dev/users")
def dev_users(session: Session = Depends(get_session)) -> list[dict]:
    """Lets the web app's user picker stand in for sign-in. Development only."""
    if get_settings().env != "dev":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rows = session.execute(select(User, Org).join(Org).order_by(Org.name, User.role, User.name)).all()
    return [{"id": u.id, "name": u.name, "role": u.role, "email": u.email, "org": o.name, "synthetic": o.is_synthetic}
            for u, o in rows]
