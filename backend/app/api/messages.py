"""The conversation with Newt: your thread, talking to it, answering it, and how it may reach you."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.capture.service import org_task_type
from app.colleague import career, etiquette, service
from app.db import get_session
from app.models import TaskType, User

router = APIRouter(tags=["messages"])


def _tt(session: Session, user: User, task_type_id: str) -> TaskType:
    try:
        return org_task_type(session, user.org_id, task_type_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/messages")
def get_thread(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    tt = _tt(session, user, task_type_id)
    messages = service.thread(session, user, tt)
    return {"intern_name": service.intern_name(session, tt), "messages": messages, "rank": career.rank(session, tt),
            "status_line": service.status_line(session, user, tt, messages)}


class SayIn(BaseModel):
    task_type_id: str
    text: str = Field(min_length=1, max_length=2000)


@router.post("/messages", status_code=status.HTTP_201_CREATED)
def say(body: SayIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    tt = _tt(session, user, body.task_type_id)
    try:
        return service.post(session, user, tt, body.text)
    except service.ConversationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


class ReplyIn(BaseModel):
    action: Literal["decide", "approve", "reject", "lesson", "answer", "sign", "feedback", "dismiss", "retry", "chase"]
    value: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/messages/{message_id}/reply")
def answer(message_id: str, body: ReplyIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    try:
        return service.reply(session, user, message_id, body.action, body.value, body.note)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except (service.ConversationError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/me/preferences")
def get_preferences(user: User = Depends(current_user)) -> dict[str, Any]:
    return etiquette.prefs_from(user.preferences).as_dict()


class PrefsIn(BaseModel):
    timezone: str | None = Field(default=None, max_length=64)
    start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    workdays: list[int] | None = None
    questions_per_day: int | None = Field(default=None, ge=0, le=20)
    urgent_out_of_hours: bool | None = None
    calls: bool | None = None
    channel: Literal["app", "email", "slack", "teams"] | None = None


@router.patch("/me/preferences")
def set_preferences(body: PrefsIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    merged = {**etiquette.prefs_from(user.preferences).as_dict(), **body.model_dump(exclude_none=True)}
    user.preferences = etiquette.prefs_from(merged).as_dict()  # validated and normalised
    session.commit()
    return user.preferences
