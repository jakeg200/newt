"""Data model from BRIEF.md. Portable across SQLite (dev) and Postgres (production)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import now
from app.db import Base

Json = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """The app's one clock: real time, or simulated time inside a process replay (`app/clock.py`)."""
    return now()


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
    preferences: Mapped[dict] = mapped_column(Json, default=dict)  # how Newt may reach this person: hours, budget, channel


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = pk()
    user_id: Mapped[str] = fk("users.id")
    scopes: Mapped[dict] = mapped_column(Json)
    text_version: Mapped[str] = mapped_column(String(50))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Connection(Base):
    """Where items and the mentor's actions come from, scoped to one task type."""

    __tablename__ = "connections"
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    task_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("task_types.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    provider: Mapped[str] = mapped_column(String(50))  # email_upload | gmail | csv | rest
    scopes: Mapped[dict] = mapped_column(Json, default=dict)
    filter: Mapped[dict] = mapped_column(Json, default=dict)  # e.g. {"label": "AP/Mismatch"}
    config: Mapped[dict] = mapped_column(Json, default=dict)  # mentor addresses, column maps, push token hash
    status: Mapped[str] = mapped_column(String(20), default="pending")
    encrypted_tokens: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaptureRun(Base):
    """One import, sync or push: what came in and how well actions matched."""

    __tablename__ = "capture_runs"
    id: Mapped[str] = pk()
    connection_id: Mapped[str] = fk("connections.id")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict] = mapped_column(Json, default=dict)


class UnmatchedAction(Base):
    """A mentor action we couldn't tie to a case. Kept (redacted) so someone can review it."""

    __tablename__ = "unmatched_actions"
    id: Mapped[str] = pk()
    connection_id: Mapped[str] = fk("connections.id")
    run_id: Mapped[str] = fk("capture_runs.id")
    source_ref: Mapped[str] = mapped_column(String(500))
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(200))
    summary: Mapped[dict] = mapped_column(Json, default=dict)


class SourceDocument(Base):
    """A policy or procedure document uploaded during orientation."""

    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("org_id", "team", "sha256"), UniqueConstraint("org_id", "team", "doc_index"))
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    team: Mapped[str] = mapped_column(String(200))
    doc_index: Mapped[int] = mapped_column(Integer)  # 1, 2, 3… within the team; prefixes passage labels
    filename: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Passage(Base):
    """A citable chunk of a source document. Labels look like "2.7" (document 2, passage 7)."""

    __tablename__ = "passages"
    __table_args__ = (UniqueConstraint("document_id", "idx"),)
    id: Mapped[str] = pk()
    document_id: Mapped[str] = fk("source_documents.id")
    label: Mapped[str] = mapped_column(String(20))
    idx: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)


class QuestionnaireAnswer(Base):
    """The mentor's answer to one orientation question. Cited in the handbook as "Q.<key>"."""

    __tablename__ = "questionnaire_answers"
    __table_args__ = (UniqueConstraint("org_id", "team", "question_key"),)
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    team: Mapped[str] = mapped_column(String(200))
    mentor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    question_key: Mapped[str] = mapped_column(String(100))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Handbook(Base):
    __tablename__ = "handbooks"
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    team: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved | superseded
    content: Mapped[dict] = mapped_column(Json, default=dict)
    meta: Mapped[dict] = mapped_column(Json, default=dict)  # model, tokens, cost, duration
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HandbookSource(Base):
    __tablename__ = "handbook_sources"
    id: Mapped[str] = pk()
    handbook_id: Mapped[str] = fk("handbooks.id")
    document_ref: Mapped[str] = mapped_column(String(500))  # source_documents.id, or "questionnaire"
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    kind: Mapped[str] = mapped_column(String(20))  # built_in | external
    name: Mapped[str] = mapped_column(String(200), default="")
    endpoint: Mapped[str | None] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict] = mapped_column(Json, default=dict)  # external: encrypted signing secret, timeout
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Apprenticeship(Base):
    __tablename__ = "apprenticeships"
    id: Mapped[str] = pk()
    agent_id: Mapped[str] = fk("agents.id")
    mentor_id: Mapped[str] = fk("users.id")
    team: Mapped[str] = mapped_column(String(200))
    handbook_version: Mapped[int | None] = mapped_column(Integer)
    rules_version: Mapped[int] = mapped_column(Integer, default=0)  # bumped on every rule change
    settings: Mapped[dict] = mapped_column(Json, default=dict)  # manager's inputs: hourly cost, currency, minutes per case


class TaskType(Base):
    __tablename__ = "task_types"
    id: Mapped[str] = pk()
    apprenticeship_id: Mapped[str] = fk("apprenticeships.id")
    name: Mapped[str] = mapped_column(String(200))
    config: Mapped[dict] = mapped_column(Json)
    config_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="shadow")  # shadow | supervised | autonomous | demoted
    tau: Mapped[float | None] = mapped_column(Float)
    calibration: Mapped[dict] = mapped_column(Json, default=dict)  # isotonic map fixed at graduation


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("connection_id", "source_ref"),)
    id: Mapped[str] = pk()
    task_type_id: Mapped[str] = fk("task_types.id")
    connection_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    source_ref: Mapped[str] = mapped_column(String(500))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict] = mapped_column(Json)  # redacted inputs as of decision time
    match_keys: Mapped[dict] = mapped_column(Json, default=dict)  # hashed ids and reference tokens, no content
    is_backtest: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | decided
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # every action confirmed done


class BacktestRun(Base):
    """Replay of decided history: the agent predicts each case using only what was known when
    the item arrived, and is scored against what the mentor actually did."""

    __tablename__ = "backtest_runs"
    id: Mapped[str] = pk()
    task_type_id: Mapped[str] = fk("task_types.id")
    agent_id: Mapped[str] = fk("agents.id")
    requested_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | done | failed
    params: Mapped[dict] = mapped_column(Json, default=dict)  # limit, date range, samples
    agent_version: Mapped[str] = mapped_column(String(50), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    handbook_version: Mapped[int | None] = mapped_column(Integer)
    rules_version: Mapped[int | None] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(64), default="")
    progress: Mapped[dict] = mapped_column(Json, default=dict)  # done, total
    stats: Mapped[dict] = mapped_column(Json, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    agent_id: Mapped[str] = fk("agents.id")
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True)
    agent_version: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100), default="")
    handbook_version: Mapped[int | None] = mapped_column(Integer)
    rules_version: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[dict] = mapped_column(Json)
    confidence: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)  # the agent failed; counts as a hand-back, never as agreement
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    sealed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # How it got there: each tool step with its (redacted) input and output, so the work can be checked and replayed.
    trajectory: Mapped[list | None] = mapped_column(Json)


class HumanAction(Base):
    __tablename__ = "human_actions"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    action_type: Mapped[str] = mapped_column(String(50))  # decision | reply | forward | label | status
    payload: Mapped[dict] = mapped_column(Json)  # decision, fields, text_outputs (redacted)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(50))
    source_ref: Mapped[str | None] = mapped_column(String(500))
    match_method: Mapped[str | None] = mapped_column(String(30))  # explicit | reply_header | thread | reference


class Comparison(Base):
    __tablename__ = "comparisons"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    prediction_id: Mapped[str] = fk("predictions.id")
    decision_match: Mapped[bool] = mapped_column(Boolean)
    field_scores: Mapped[dict] = mapped_column(Json, default=dict)
    text_judgement: Mapped[dict] = mapped_column(Json, default=dict)
    agreement: Mapped[bool] = mapped_column(Boolean)  # as scored, before any lesson
    attribution: Mapped[str | None] = mapped_column(String(20))  # set by the mentor's lesson
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)  # "I'd change my call": not the agent's error
    steps: Mapped[dict] = mapped_column(Json, default=dict)  # trajectory checks: required evidence, allowed tools

    @property
    def effective_agreement(self) -> bool | None:
        """Agreement after the mentor's lesson: None when the case no longer counts."""
        if self.excluded:
            return None
        if self.attribution == "both_fine":
            return True
        if self.attribution in ("intern_wrong", "couldnt_know"):
            return False
        return self.agreement


class Rule(Base):
    """Something the apprentice believes the mentor cares about, in plain English."""

    __tablename__ = "rules"
    id: Mapped[str] = pk()
    apprenticeship_id: Mapped[str] = fk("apprenticeships.id")
    text: Mapped[str] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(100))
    supporting_case_ids: Mapped[list] = mapped_column(Json, default=list)  # example cases it came from
    source: Mapped[str] = mapped_column(String(20), default="inferred")  # inferred | mentor
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | active | retired
    version: Mapped[int] = mapped_column(Integer, default=1)
    evidence_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # latest decision it learned from
    stats: Mapped[dict] = mapped_column(Json, default=dict)  # support, precision
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    prediction_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("predictions.id", ondelete="CASCADE"), index=True)
    attribution: Mapped[str] = mapped_column(String(20))  # intern_wrong | both_fine | mentor_changed | couldnt_know
    note: Mapped[str | None] = mapped_column(Text)
    reply_ok: Mapped[bool | None] = mapped_column(Boolean)  # mentor's verdict on the agent's reply, if asked
    rule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("rules.id", ondelete="SET NULL"))
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    """One message in the conversation between Newt and a person, about one task type.

    Newt writes `body` itself from redacted case data; anything a person types is redacted before it's stored.
    `dedupe_key` stops Newt asking the same thing twice. `deliver_after` is when etiquette lets it be seen."""

    __tablename__ = "messages"
    id: Mapped[str] = pk()
    task_type_id: Mapped[str] = fk("task_types.id")
    user_id: Mapped[str] = fk("users.id")
    direction: Mapped[str] = mapped_column(String(10))  # newt | person
    kind: Mapped[str] = mapped_column(String(20))  # standup | question | delivery | handback | draft | promotion | ack | chat
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(Json, default=dict)  # case refs, options, the answer
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | answered | done | dismissed
    urgency: Mapped[str] = mapped_column(String(10), default="normal")  # low | normal | urgent
    dedupe_key: Mapped[str | None] = mapped_column(String(200), index=True)
    deliver_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    """A blind audit: the mentor decides an autonomously handled case without seeing the agent's answer."""

    __tablename__ = "audits"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    task_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("task_types.id", ondelete="CASCADE"), index=True)
    prediction_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("predictions.id", ondelete="CASCADE"))
    blind: Mapped[bool] = mapped_column(Boolean, default=True)
    result: Mapped[str | None] = mapped_column(String(20))  # pass | fail; None until the mentor answers
    mentor_payload: Mapped[dict] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DriftCheck(Base):
    __tablename__ = "drift_checks"
    id: Mapped[str] = pk()
    task_type_id: Mapped[str] = fk("task_types.id")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    drifted: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict] = mapped_column(Json, default=dict)


class TrackRecord(Base):
    __tablename__ = "track_records"
    id: Mapped[str] = pk()
    task_type_id: Mapped[str] = fk("task_types.id")
    metrics: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActionLog(Base):
    """Every action the agent proposed, whether the policy allowed it, and what happened to it."""

    __tablename__ = "action_log"
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk("cases.id")
    prediction_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("predictions.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="supervised")  # supervised | autonomous
    action: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(Json)
    policy_check: Mapped[dict] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | edited | rejected | executed | blocked
    decided_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Doing the work in the firm's systems: queued -> running -> done | failed. None means nothing to run.
    exec_status: Mapped[str | None] = mapped_column(String(20))
    destination_id: Mapped[str | None] = mapped_column(String(36))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    external_ref: Mapped[str | None] = mapped_column(String(200))
    result: Mapped[dict] = mapped_column(Json, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Destination(Base):
    """Where Newt does the work: a firm's system (or Zapier, Make, n8n) that receives signed actions referring to the
    source item, carries them out, and confirms. Newt never holds the real recipients; the system does."""

    __tablename__ = "destinations"
    id: Mapped[str] = pk()
    org_id: Mapped[str] = fk("orgs.id")
    task_type_id: Mapped[str] = fk("task_types.id")
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="webhook")
    url: Mapped[str] = mapped_column(String(500))
    actions: Mapped[list] = mapped_column(Json, default=list)  # which action types it carries out
    encrypted_secret: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | paused
    last_test: Mapped[dict] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = pk()
    type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | done | failed
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Improvement(Base):
    """A change to how Newt works (a rule, a routine), tested on past cases before it goes live.

    The replay's result is the blast radius: which past cases the change fixes, which it breaks, which it moves. A
    mentor's own change goes live by itself when it breaks nothing; anything else waits for the mentor."""

    __tablename__ = "improvements"
    id: Mapped[str] = pk()
    task_type_id: Mapped[str] = fk("task_types.id")
    kind: Mapped[str] = mapped_column(String(20))  # add_rule | edit_rule | retire_rule | activate_rule | routine
    rule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("rules.id"))
    candidate: Mapped[dict] = mapped_column(Json, default=dict)  # new text, routine steps, target case ids
    summary: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="mentor")  # mentor | newt
    signal: Mapped[str] = mapped_column(String(40), default="taught")  # taught | exception | inferred | routine
    status: Mapped[str] = mapped_column(String(20), default="testing")  # testing | ready | promoted | rejected | failed
    blast: Mapped[dict] = mapped_column(Json, default=dict)
    proposed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    decided_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    repredict_run_id: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
