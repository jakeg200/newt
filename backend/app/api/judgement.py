"""The judgement ledger: what Newt knows about how the team decides, written and unwritten, with evidence."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.auth import current_user
from app.capture.service import org_task_type
from app.colleague.service import intern_name
from app.db import get_session
from app.learning import judgement
from app.models import TaskType, User

router = APIRouter(tags=["judgement"])


def _tt(session: Session, user: User, task_type_id: str) -> TaskType:
    try:
        return org_task_type(session, user.org_id, task_type_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/task-types/{task_type_id}/judgement")
def get_judgement(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    return judgement.ledger(session, _tt(session, user, task_type_id))


def _name(tt: TaskType) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in tt.name.lower()).strip("-")


@router.get("/task-types/{task_type_id}/judgement.md")
def judgement_markdown(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> PlainTextResponse:
    tt = _tt(session, user, task_type_id)
    return PlainTextResponse(judgement.markdown(tt, judgement.ledger(session, tt), intern_name(session, tt)),
                             headers={"Content-Disposition": f'attachment; filename="judgement-{_name(tt)}.md"'})


@router.get("/task-types/{task_type_id}/judgement.pdf")
def judgement_pdf(task_type_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> Response:
    tt = _tt(session, user, task_type_id)
    data = judgement.pdf(tt, judgement.ledger(session, tt), intern_name(session, tt))
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="judgement-{_name(tt)}.pdf"'})
