from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import manager
from app.auth import current_user, require_role
from app.db import get_session
from app.models import User

router = APIRouter(prefix="/manager", tags=["manager"])


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    return manager.dashboard(session, user)


class SettingsIn(BaseModel):
    currency: str | None = Field(default=None, min_length=1, max_length=5)
    usd_rate: float | None = Field(default=None, gt=0, le=10000)  # units of the manager's currency per US dollar
    hourly_cost: float | None = Field(default=None, ge=0, le=100000)
    minutes_per_case: float | None = Field(default=None, gt=0, le=600)


@router.patch("/settings/{team}")
def update_settings(team: str, body: SettingsIn, user: User = Depends(require_role("manager", "admin")),
                    session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return manager.update_settings(session, user, team, body.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
