from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import current_user, require_role
from app.db import get_session
from app.llm.provider import ProviderError, get_provider
from app.models import Handbook, User
from app.orientation import service
from app.orientation.extract import ExtractionError

router = APIRouter(prefix="/orientation", tags=["orientation"])

editor = require_role("mentor", "manager", "admin")
mentor = require_role("mentor", "admin")
manager = require_role("manager")


def _team(session: Session, user: User, team: str) -> str:
    try:
        service.require_team(session, user.org_id, team)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return team


def _handbook_out(h: Handbook) -> dict[str, Any]:
    return {
        "id": h.id,
        "team": h.team,
        "version": h.version,
        "status": h.status,
        "content": h.content,
        "meta": h.meta,
        "created_at": h.created_at,
        "approved_by": h.approved_by,
        "approved_at": h.approved_at,
    }


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/teams")
def teams(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[str]:
    return service.org_teams(session, user.org_id)


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def upload_sources(
    team: str = Form(...),
    files: list[UploadFile] = File(...),
    user: User = Depends(editor),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    _team(session, user, team)
    results = []
    for upload in files:
        data = await upload.read()
        try:
            r = service.add_document(session, user, team, upload.filename or "upload.txt", data)
        except ExtractionError as exc:
            session.rollback()
            results.append({"filename": upload.filename, "error": str(exc)})
            continue
        results.append(
            {"id": r.document.id, "filename": r.document.filename, "doc_index": r.document.doc_index,
             "passages": r.passages, "duplicate": r.duplicate}
        )
    return results


@router.get("/sources")
def list_sources(
    team: str = Query(...), user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    _team(session, user, team)
    return [
        {"id": d.id, "filename": d.filename, "doc_index": d.doc_index, "mime": d.mime, "size_bytes": d.size_bytes,
         "passages": n, "uploaded_at": d.uploaded_at}
        for d, n in service.documents(session, user.org_id, team)
    ]


@router.delete("/sources/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(document_id: str, user: User = Depends(editor), session: Session = Depends(get_session)) -> None:
    try:
        service.delete_document(session, user.org_id, document_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/passages")
def list_passages(
    team: str = Query(...), user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    """Every citable source, so the UI can show what a handbook item points at."""
    _team(session, user, team)
    return service.sources(session, user.org_id, team)


@router.get("/questionnaire")
def get_questionnaire(
    team: str = Query(...), user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    _team(session, user, team)
    return service.questionnaire(session, user.org_id, team)


class Answers(BaseModel):
    answers: dict[str, str]


@router.put("/questionnaire")
def put_questionnaire(
    body: Answers, team: str = Query(...), user: User = Depends(mentor), session: Session = Depends(get_session)
) -> dict[str, int]:
    _team(session, user, team)
    try:
        return {"saved": service.save_answers(session, user, team, body.answers)}
    except service.OrientationError as exc:
        raise _bad_request(exc) from exc


class DraftRequest(BaseModel):
    team: str


@router.post("/handbook/draft", status_code=status.HTTP_201_CREATED)
def draft_handbook(body: DraftRequest, user: User = Depends(editor), session: Session = Depends(get_session)) -> dict[str, Any]:
    _team(session, user, body.team)
    try:
        return _handbook_out(service.draft(session, user, body.team, get_provider()))
    except service.OrientationError as exc:
        raise _bad_request(exc) from exc
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.get("/handbook")
def handbook_versions(
    team: str = Query(...), user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    """All versions for the team, newest first."""
    _team(session, user, team)
    return [_handbook_out(h) for h in service.versions(session, user.org_id, team)]


def _load(session: Session, user: User, handbook_id: str) -> Handbook:
    try:
        return service.get_handbook(session, user.org_id, handbook_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/handbook/{handbook_id}")
def get_handbook(handbook_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _handbook_out(_load(session, user, handbook_id))


class ContentUpdate(BaseModel):
    content: dict[str, Any]


@router.patch("/handbook/{handbook_id}")
def update_handbook(
    handbook_id: str, body: ContentUpdate, user: User = Depends(editor), session: Session = Depends(get_session)
) -> dict[str, Any]:
    try:
        return _handbook_out(service.update_draft(session, _load(session, user, handbook_id), body.content))
    except service.OrientationError as exc:
        raise _bad_request(exc) from exc


@router.post("/handbook/{handbook_id}/approve")
def approve_handbook(handbook_id: str, user: User = Depends(manager), session: Session = Depends(get_session)) -> dict[str, Any]:
    from sqlalchemy import select

    from app.graduation.engine import on_procedure_change
    from app.models import Agent, Apprenticeship, TaskType

    try:
        handbook = service.approve(session, _load(session, user, handbook_id), user)
    except service.OrientationError as exc:
        raise _bad_request(exc) from exc
    # A new handbook is a procedure change: graduated task types re-prove themselves on the frozen record.
    for tt in session.scalars(select(TaskType).join(Apprenticeship).join(Agent)
                              .where(Agent.org_id == user.org_id, Apprenticeship.team == handbook.team)):
        on_procedure_change(session, tt, user, f"handbook v{handbook.version} approved")
    session.commit()
    return _handbook_out(handbook)


@router.post("/handbook/{handbook_id}/revise", status_code=status.HTTP_201_CREATED)
def revise_handbook(handbook_id: str, user: User = Depends(editor), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return _handbook_out(service.revise(session, _load(session, user, handbook_id), user))
    except service.OrientationError as exc:
        raise _bad_request(exc) from exc
