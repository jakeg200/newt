"""Data model from BRIEF.md. Portable across SQLite (dev) and Postgres (production)."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

Json = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def pk() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


def fk(target: str, nullable: bool = False) -> Mapped[Any]:
    return mapped_column(String(36), ForeignKey(target, ondelete="CASCADE"), nullable=nullable, index=True)


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[str] = pk()
    name: Mapped[str] = mapped_column(String(200))
    data_region: Mapped[str] = mapped_column(String(20), default="eu")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    role: Mapped[str] = mapped_column(String(20))  # mentor | manager | admin
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = pk()
    user_id: Mapped[str] = fk("users.id")
    scopes: Mapped[dict] = mapped_column(Json)
    text_version: Mapped[str] = mapped_column(String(50))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Connection(Base):
    __tablename__ = "connections"
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    provider: Mapped[str] = mapped_column(String(50))
    scopes: Mapped[dict] = mapped_column(Json, default=dict)
    filter: Mapped[dict] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    encrypted_tokens: Mapped[str | None] = mapped_column(Text)


class Handbook(Base):
    __tablename__ = "handbooks"
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    team: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict] = mapped_column(Json, default=dict)
    approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HandbookSource(Base):
    __tablename__ = "handbook_sources"
    id: Mapped[str] = pk()
    handbook_id: Mapped[str] = fk("handbooks.id")
    document_ref: Mapped[str] = mapped_column(String(500))
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    kind: Mapped[str] = mapped_column(String(20))  # built_in | external
    endpoint: Mapped[str | None] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))


class Apprenticeship(Base):
    __tablename__ = "apprenticeships"
    id: Mapped[str] = pk()
    agent_id: Mapped[str] = fk("agents.id")
    mentor_id: Mapped[str] = fk("users.id")
    team: Mapped[str] = mapped_column(String(200))
    handbook_version: Mapped[int | None] = mapped_column(Integer)


class TaskType(Base):
    __tablename__ = "task_types"
    id: Mapped[str] = pk()
    apprenticeship_id: Mapped[str] = fk("apprenticeships.id")
    name: Mapped[str] = mapped_column(String(200))
    config: Mapped[dict] = mapped_column(Json)
    config_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="shadow")  # shadow | supervised | autonomous | demoted
    tau: Mapped[float | None] = mapped_column(Float)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = pk()
    task_type_id: Mapped[str] = fk("task_types.id")
    source_ref: Mapped[str] = mapped_column(String(500))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict] = mapped_column(Json)  # redacted inputs as of decision time
    is_backtest: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="open")


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    agent_id: Mapped[str] = fk("agents.id")
    agent_version: Mapped[str] = mapped_column(String(50))
    handbook_version: Mapped[int | None] = mapped_column(Integer)
    rules_version: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[dict] = mapped_column(Json)
    confidence: Mapped[float | None] = mapped_column(Float)
    sealed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HumanAction(Base):
    __tablename__ = "human_actions"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    action_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(Json)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(50))


class Comparison(Base):
    __tablename__ = "comparisons"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    prediction_id: Mapped[str] = fk("predictions.id")
    decision_match: Mapped[bool] = mapped_column(Boolean)
    field_scores: Mapped[dict] = mapped_column(Json, default=dict)
    text_judgement: Mapped[dict] = mapped_column(Json, default=dict)
    agreement: Mapped[bool] = mapped_column(Boolean)


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[str] = pk()
    apprenticeship_id: Mapped[str] = fk("apprenticeships.id")
    text: Mapped[str] = mapped_column(Text)
    supporting_case_ids: Mapped[list] = mapped_column(Json, default=list)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | active | retired
    version: Mapped[int] = mapped_column(Integer, default=1)


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    attribution: Mapped[str] = mapped_column(String(20))  # intern_wrong | both_fine | mentor_changed | couldnt_know
    note: Mapped[str | None] = mapped_column(Text)
    rule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("rules.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GraduationEvent(Base):
    __tablename__ = "graduation_events"
    id: Mapped[str] = pk()
    task_type_id: Mapped[str] = fk("task_types.id")
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[dict] = mapped_column(Json)
    signed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Audit(Base):
    __tablename__ = "audits"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    blind: Mapped[bool] = mapped_column(Boolean, default=True)
    result: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrackRecord(Base):
    __tablename__ = "track_records"
    id: Mapped[str] = pk()
    task_type_id: Mapped[str] = fk("task_types.id")
    metrics: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActionLog(Base):
    __tablename__ = "action_log"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    action: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(Json)
    policy_check: Mapped[dict] = mapped_column(Json)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = pk()
    type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
