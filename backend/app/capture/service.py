"""Connections: where a task type's items and the mentor's actions come from."""

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import crypto
from app.capture.ingest import aware, ingest
from app.capture.sources import gmail
from app.capture.sources.email_source import parse_uploads
from app.capture.sources.tabular import ColumnMap, read_rows, rows_to_batch
from app.capture.types import Action, Batch, Item
from app.config import get_settings
from app.models import Agent, Apprenticeship, CaptureRun, Case, Connection, Consent, TaskType, User
from app.task_types import TaskTypeConfig

PROVIDERS = ("email_upload", "gmail", "csv", "rest")
CONSENT_TEXT_VERSION = "capture-v1"


class CaptureError(ValueError):
    """A request that can't be done as asked. The message is safe to show users."""


def decrypt(token: str) -> str:
    try:
        return crypto.decrypt(token)
    except crypto.DecryptError as exc:
        raise CaptureError("stored credentials can't be read; reconnect") from exc


encrypt = crypto.encrypt


def _push_hash(token: str) -> str:
    return hmac.new(get_settings().secret(), f"push:{token}".encode(), hashlib.sha256).hexdigest()


def sign_state(connection_id: str, user_id: str) -> str:
    payload = f"{connection_id}.{user_id}"
    sig = hmac.new(get_settings().secret(), f"oauth:{payload}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def verify_state(state: str) -> tuple[str, str]:
    try:
        connection_id, user_id, sig = state.split(".")
    except ValueError as exc:
        raise CaptureError("invalid sign-in state") from exc
    if not hmac.compare_digest(sign_state(connection_id, user_id), state):
        raise CaptureError("invalid sign-in state")
    return connection_id, user_id


class NewConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    provider: Literal["email_upload", "gmail", "csv", "rest"]
    task_type_id: str
    mentor_addresses: list[str] = Field(default_factory=list)
    body_input: str | None = None  # which task input an email body fills
    label: str | None = None  # gmail
    columns: dict[str, Any] | None = None  # csv
    consent: bool = False

    @field_validator("mentor_addresses")
    @classmethod
    def _addresses(cls, v: list[str]) -> list[str]:
        cleaned = [a.strip().lower() for a in v if a.strip()]
        bad = [a for a in cleaned if "@" not in a]
        if bad:
            raise ValueError(f"not email addresses: {', '.join(bad)}")
        return cleaned


def org_task_type(session: Session, org_id: str, task_type_id: str) -> TaskType:
    tt = session.scalar(
        select(TaskType).join(Apprenticeship).join(Agent).where(TaskType.id == task_type_id, Agent.org_id == org_id)
    )
    if tt is None:
        raise LookupError("task type not found")
    return tt


def create_connection(session: Session, user: User, body: NewConnection) -> tuple[Connection, str | None]:
    tt = org_task_type(session, user.org_id, body.task_type_id)
    config = TaskTypeConfig.model_validate(tt.config)
    conn_config: dict[str, Any] = {}
    push_token = None

    if body.provider in ("email_upload", "gmail"):
        if not body.mentor_addresses:
            raise CaptureError("add the mentor's email address so their replies are recognised as actions")
        body_input = body.body_input or config.inputs[0]
        if body_input not in config.inputs:
            raise CaptureError(f"body_input must be one of {config.inputs}")
        conn_config = {"mentor_addresses": body.mentor_addresses, "body_input": body_input}
        if not body.consent:
            raise CaptureError("the mentor's consent is needed to capture their email")
    if body.provider == "gmail" and not (body.label or "").strip():
        raise CaptureError("name the Gmail label to read; nothing outside it is captured")
    if body.provider == "csv":
        try:
            columns = ColumnMap.model_validate(body.columns or {})
        except ValidationError as exc:
            raise CaptureError(f"column map: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}") from exc
        unknown = sorted(set(columns.inputs) - set(config.inputs))
        if unknown:
            raise CaptureError(f"column map inputs not in the task type: {', '.join(unknown)}")
        conn_config = {"columns": columns.model_dump()}
    if body.provider == "rest":
        push_token = "ao_" + secrets.token_urlsafe(32)
        conn_config = {"push_token_hash": _push_hash(push_token)}

    connection = Connection(
        org_id=user.org_id,
        task_type_id=tt.id,
        name=body.name,
        provider=body.provider,
        filter={"label": body.label.strip()} if body.provider == "gmail" else {},
        scopes={"gmail": [gmail.SCOPE]} if body.provider == "gmail" else {},
        config=conn_config,
        status="pending" if body.provider == "gmail" else "active",
    )
    session.add(connection)
    session.flush()
    if body.consent:
        session.add(
            Consent(
                user_id=user.id,
                scopes={"connection_id": connection.id, "provider": body.provider, "filter": connection.filter,
                        "addresses": body.mentor_addresses},
                text_version=CONSENT_TEXT_VERSION,
            )
        )
    session.commit()
    return connection, push_token


def get_connection(session: Session, org_id: str, connection_id: str) -> Connection:
    connection = session.get(Connection, connection_id)
    if connection is None or connection.org_id != org_id:
        raise LookupError("connection not found")
    return connection


def _require_active(connection: Connection) -> None:
    if connection.status == "paused":
        raise CaptureError("this connection is paused")
    if connection.status == "pending" and connection.provider == "gmail":
        raise CaptureError("sign in with Google first")
    if connection.status != "active":
        raise CaptureError(f"this connection is {connection.status}")


def _task_config(session: Session, connection: Connection) -> TaskTypeConfig:
    return TaskTypeConfig.model_validate(session.get(TaskType, connection.task_type_id).config)


def import_files(session: Session, connection: Connection, files: list[tuple[str, bytes]]) -> CaptureRun:
    _require_active(connection)
    if connection.provider == "email_upload":
        batch = parse_uploads(files, connection.config["mentor_addresses"], connection.config["body_input"])
    elif connection.provider == "csv":
        columns = ColumnMap.model_validate(connection.config["columns"])
        decisions = _task_config(session, connection).decision
        batch = Batch()
        for name, data in files:
            try:
                part = rows_to_batch(read_rows(name, data), columns, decisions)
            except (ValueError, UnicodeDecodeError) as exc:
                batch.errors.append(f"{name}: {exc}")
                continue
            batch.items += part.items
            batch.actions += part.actions
            batch.errors += [f"{name} {e}" for e in part.errors]
    else:
        raise CaptureError(f"{connection.provider} connections don't take file uploads")
    return ingest(session, connection, batch)  # uploaded history is always backtest


class PushItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str = Field(min_length=1, max_length=500)
    received_at: datetime
    inputs: dict[str, str]
    subject: str = ""
    thread: str | None = None
    sender: str | None = Field(default=None, max_length=320)  # stored only as a pseudonym


class PushAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str = Field(min_length=1, max_length=500)
    acted_at: datetime
    item_ref: str | None = None
    thread: str | None = None
    kind: Literal["decision", "label", "status"] = "decision"
    decision: str | None = None
    label: str | None = None
    status: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    text_outputs: dict[str, str] = Field(default_factory=dict)


class PushBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[PushItem] = Field(default_factory=list, max_length=1000)
    actions: list[PushAction] = Field(default_factory=list, max_length=1000)
    backtest: bool = False


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def connection_for_push(session: Session, connection_id: str, token: str | None) -> Connection:
    connection = session.get(Connection, connection_id)
    expected = (connection.config or {}).get("push_token_hash") if connection else None
    if not connection or connection.provider != "rest" or not token or not expected or not hmac.compare_digest(expected, _push_hash(token)):
        raise PermissionError("invalid connection or token")
    return connection


def push(session: Session, connection: Connection, body: PushBody) -> CaptureRun:
    _require_active(connection)
    config = _task_config(session, connection)
    batch = Batch()
    for i in body.items:
        unknown = sorted(set(i.inputs) - set(config.inputs))
        if unknown:
            batch.errors.append(f"item {i.ref[:40]}: unknown inputs {', '.join(unknown)}")
            continue
        batch.items.append(Item(source_ref=i.ref, received_at=_utc(i.received_at), inputs=i.inputs, subject=i.subject,
                                thread_ref=i.thread, sender=i.sender.lower() if i.sender else None))
    for a in body.actions:
        if a.kind == "decision" and a.decision not in config.decision:
            batch.errors.append(f"action {a.ref[:40]}: decision must be one of {config.decision}")
            continue
        batch.actions.append(
            Action(source_ref=a.ref, acted_at=_utc(a.acted_at), kind=a.kind, item_ref=a.item_ref, thread_ref=a.thread,
                   decision=a.decision, label=a.label, status=a.status, fields=a.fields, text_outputs=a.text_outputs)
        )
    return ingest(session, connection, batch, live_after=None if body.backtest else aware(connection.created_at))


def oauth_start(connection: Connection, user: User) -> str:
    settings = get_settings()
    if connection.provider != "gmail":
        raise CaptureError("only Gmail connections sign in with Google")
    if not settings.google_client_id:
        raise CaptureError("Google sign-in isn't configured yet (GOOGLE_CLIENT_ID; see docs/NEEDS_JAKE.md)")
    return gmail.auth_url(settings.google_client_id, f"{settings.api_url}/oauth/google/callback", sign_state(connection.id, user.id))


def oauth_finish(session: Session, code: str, state: str, http=None) -> Connection:
    settings = get_settings()
    connection_id, _user_id = verify_state(state)
    connection = session.get(Connection, connection_id)
    if connection is None or connection.provider != "gmail":
        raise CaptureError("connection not found")
    try:
        refresh = gmail.exchange_code(code, settings.google_client_id or "", settings.google_client_secret or "",
                                      f"{settings.api_url}/oauth/google/callback", http)
    except gmail.GmailError as exc:
        raise CaptureError(str(exc)) from exc
    connection.encrypted_tokens = encrypt(refresh)
    connection.status = "active"
    session.commit()
    return connection


def sync_gmail(session: Session, connection: Connection, http=None) -> CaptureRun:
    settings = get_settings()
    if connection.provider != "gmail":
        raise CaptureError("only Gmail connections sync")
    _require_active(connection)
    if not connection.encrypted_tokens:
        raise CaptureError("sign in with Google first")
    client = gmail.GmailClient(settings.google_client_id or "", settings.google_client_secret or "",
                               decrypt(connection.encrypted_tokens), http)
    last = session.scalar(
        select(func.max(CaptureRun.started_at)).where(CaptureRun.connection_id == connection.id, CaptureRun.finished_at.is_not(None))
    )
    try:
        batch = gmail.fetch_batch(client, connection.filter["label"], connection.config["mentor_addresses"],
                                  connection.config["body_input"], after=None if last is None else aware(last))
    except gmail.GmailError as exc:
        raise CaptureError(str(exc)) from exc
    # Mail from before the mailbox was connected is history (backtest); after that it's live.
    return ingest(session, connection, batch, live_after=aware(connection.created_at))


def connection_summary(session: Session, connection: Connection) -> dict[str, Any]:
    cases = session.scalar(select(func.count()).select_from(Case).where(Case.connection_id == connection.id)) or 0
    decided = session.scalar(
        select(func.count()).select_from(Case).where(Case.connection_id == connection.id, Case.status == "decided")
    ) or 0
    last_run = session.scalar(
        select(CaptureRun).where(CaptureRun.connection_id == connection.id).order_by(CaptureRun.started_at.desc()).limit(1)
    )
    return {
        "id": connection.id,
        "name": connection.name,
        "provider": connection.provider,
        "task_type_id": connection.task_type_id,
        "status": connection.status,
        "filter": connection.filter,
        "mentor_addresses": (connection.config or {}).get("mentor_addresses", []),
        "body_input": (connection.config or {}).get("body_input"),
        "columns": (connection.config or {}).get("columns"),
        "created_at": connection.created_at,
        "cases": cases,
        "decided": decided,
        "last_run": {"id": last_run.id, "started_at": last_run.started_at, "stats": last_run.stats} if last_run else None,
    }
