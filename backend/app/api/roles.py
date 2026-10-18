"""The role library: roles a Newt can be hired for, and hiring one."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import admin
from app.auth import current_user, require_role
from app.config import get_settings
from app.db import get_session
from app.models import Org, User
from app.task_types import load_role_packs

router = APIRouter(tags=["roles"])
manager = require_role("manager", "admin")


@router.get("/role-packs")
def role_packs(user: User = Depends(current_user)) -> list[dict[str, Any]]:
    s = get_settings()
    return [{"id": p.id, "title": p.title, "tagline": p.tagline, "description": p.description, "team": p.team, "task_type": c.name,
             "decisions": c.decision, "kpis": [k.label or k.metric for k in c.kpis], "tools": c.tools,
             "always_hand_back": c.hard_rules} for p, c in load_role_packs(s.roles_dir, s.task_types_dir).values()]


class HireIn(BaseModel):
    team: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,60}$")
    mentor_email: str | None = None


@router.post("/role-packs/{pack_id}/hire", status_code=status.HTTP_201_CREATED)
def hire(pack_id: str, body: HireIn, user: User = Depends(manager), session: Session = Depends(get_session)) -> dict[str, Any]:
    org = session.get(Org, user.org_id)
    try:
        tt = admin.hire(session, org.name, pack_id, body.mentor_email, body.team)
    except admin.AdminError as exc:
        code = status.HTTP_404_NOT_FOUND if "no role pack" in str(exc) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, str(exc)) from exc
    return {"task_type_id": tt.id, "name": tt.name}
