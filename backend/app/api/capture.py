from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user, require_role
from app.capture import service
from app.config import get_settings
from app.db import get_session
from app.models import CaptureRun, Case, Connection, HumanAction, UnmatchedAction, User

router = APIRouter(tags=["capture"])

# Captured cases come from the mentor's own work, so the mentor (and admins) handle capture.
mentor = require_role("mentor", "admin")
anyone = current_user


def _connection(session: Session, user: User, connection_id: str) -> Connection:
    try:
        return service.get_connection(session, user.org_id, connection_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _run_out(run: CaptureRun) -> dict[str, Any]:
    return {"id": run.id, "connection_id": run.connection_id, "started_at": run.started_at,
            "finished_at": run.finished_at, "stats": run.stats}


@router.post("/connections", status_code=status.HTTP_201_CREATED)
def create_connection(body: service.NewConnection, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        connection, token = service.create_connection(session, user, body)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except service.CaptureError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    out = service.connection_summary(session, connection)
    if token:
        out["push_token"] = token  # shown once; only a hash is stored
        out["push_url"] = f"{get_settings().api_url}/capture/push/{connection.id}"
    return out


@router.get("/connections")
def list_connections(
    task_type_id: str | None = None, user: User = Depends(anyone), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    query = select(Connection).where(Connection.org_id == user.org_id).order_by(Connection.created_at)
    if task_type_id:
        query = query.where(Connection.task_type_id == task_type_id)
    return [service.connection_summary(session, c) for c in session.scalars(query)]


class ConnectionPatch(BaseModel):
    name: str | None = None
    status: Literal["active", "paused"] | None = None


@router.patch("/connections/{connection_id}")
def update_connection(
    connection_id: str, body: ConnectionPatch, user: User = Depends(mentor), session: Session = Depends(get_session)
) -> dict[str, Any]:
    connection = _connection(session, user, connection_id)
    if body.name is not None:
        connection.name = body.name
    if body.status is not None:
        if connection.status == "pending" and body.status == "active":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "sign in with Google first")
        connection.status = body.status
    session.commit()
    return service.connection_summary(session, connection)


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> None:
    """Deletes the connection and every case captured through it."""
    session.delete(_connection(session, user, connection_id))
    session.commit()


@router.post("/connections/{connection_id}/import", status_code=status.HTTP_201_CREATED)
async def import_files(
    connection_id: str, files: list[UploadFile] = File(...), user: User = Depends(mentor), session: Session = Depends(get_session)
) -> dict[str, Any]:
    connection = _connection(session, user, connection_id)
    uploads = [(f.filename or "upload", await f.read()) for f in files]
    try:
        return _run_out(service.import_files(session, connection, uploads))
    except service.CaptureError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/connections/{connection_id}/sync", status_code=status.HTTP_201_CREATED)
def sync(connection_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return _run_out(service.sync_gmail(session, _connection(session, user, connection_id)))
    except service.CaptureError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/connections/{connection_id}/oauth/start")
def oauth_start(connection_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, str]:
    try:
        return {"url": service.oauth_start(_connection(session, user, connection_id), user)}
    except service.CaptureError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/oauth/google/callback")
def oauth_callback(code: str = Query(...), state: str = Query(...), session: Session = Depends(get_session)) -> RedirectResponse:
    try:
        service.oauth_finish(session, code, state)
        outcome = "connected"
    except service.CaptureError:
        outcome = "failed"
    return RedirectResponse(f"{get_settings().web_url}/capture?gmail={outcome}")


@router.get("/connections/{connection_id}/runs")
def runs(connection_id: str, user: User = Depends(anyone), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    connection = _connection(session, user, connection_id)
    rows = session.scalars(
        select(CaptureRun).where(CaptureRun.connection_id == connection.id).order_by(CaptureRun.started_at.desc()).limit(50)
    )
    return [_run_out(r) for r in rows]


@router.get("/connections/{connection_id}/unmatched")
def unmatched(connection_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    connection = _connection(session, user, connection_id)
    rows = session.scalars(
        select(UnmatchedAction).where(UnmatchedAction.connection_id == connection.id).order_by(UnmatchedAction.acted_at.desc()).limit(200)
    )
    return [
        {"id": u.id, "acted_at": u.acted_at, "reason": u.reason,
         "summary": {k: v for k, v in u.summary.items() if k != "prepared"}}
        for u in rows
    ]


@router.post("/capture/push/{connection_id}", status_code=status.HTTP_201_CREATED)
def push(
    connection_id: str,
    body: service.PushBody,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """For ticketing systems, CRMs and scripts: send items and decisions with the connection's token."""
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    try:
        connection = service.connection_for_push(session, connection_id, token)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    try:
        return _run_out(service.push(session, connection, body))
    except service.CaptureError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def _case_out(case: Case, actions: list[HumanAction], detail: bool = False) -> dict[str, Any]:
    decision_action = next((a for a in actions if a.payload.get("decision")), None)
    out = {
        "id": case.id,
        "connection_id": case.connection_id,
        "source_ref": case.source_ref,
        "received_at": case.received_at,
        "status": case.status,
        "is_backtest": case.is_backtest,
        "subject": case.snapshot.get("subject", ""),
        "decision": decision_action.payload["decision"] if decision_action else None,
        "match_method": decision_action.match_method if decision_action else None,
        "action_count": len(actions),
    }
    if detail:
        out["snapshot"] = case.snapshot
        out["actions"] = [
            {"id": a.id, "type": a.action_type, "acted_at": a.acted_at, "match_method": a.match_method, "payload": a.payload}
            for a in actions
        ]
    return out


@router.get("/cases")
def list_cases(
    task_type_id: str,
    status_filter: Literal["open", "decided"] | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    user: User = Depends(mentor),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        service.org_task_type(session, user.org_id, task_type_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    where = [Case.task_type_id == task_type_id, Case.connection_id.is_not(None)]
    if status_filter:
        where.append(Case.status == status_filter)
    total = session.scalar(select(func.count()).select_from(Case).where(*where)) or 0
    cases = list(session.scalars(select(Case).where(*where).order_by(Case.received_at.desc()).limit(limit).offset(offset)))
    actions: dict[str, list[HumanAction]] = {}
    if cases:
        for a in session.scalars(
            select(HumanAction).where(HumanAction.case_id.in_([c.id for c in cases])).order_by(HumanAction.acted_at)
        ):
            actions.setdefault(a.case_id, []).append(a)
    return {"total": total, "items": [_case_out(c, actions.get(c.id, [])) for c in cases]}


@router.get("/cases/{case_id}")
def get_case(case_id: str, user: User = Depends(mentor), session: Session = Depends(get_session)) -> dict[str, Any]:
    case = session.get(Case, case_id)
    connection = session.get(Connection, case.connection_id) if case and case.connection_id else None
    if case is None or connection is None or connection.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")
    actions = list(session.scalars(select(HumanAction).where(HumanAction.case_id == case.id).order_by(HumanAction.acted_at)))
    return _case_out(case, actions, detail=True)
