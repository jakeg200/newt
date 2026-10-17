"""What every capture source produces, before redaction. Raw values here never reach storage
or logs: ingest redacts or hashes each field on the way in."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class HistoryEntry:
    at: datetime
    sender: str | None
    text: str


@dataclass
class Item:
    """Something arrived that a person had to decide on."""

    source_ref: str  # stable id in the source: Message-ID, row id, ticket id
    received_at: datetime
    inputs: dict[str, str]  # text per task-type input
    subject: str = ""
    sender: str | None = None
    thread_ref: str | None = None
    message_ids: list[str] = field(default_factory=list)  # ids a reply may point at
    attachments: list[str] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)  # earlier thread messages, before received_at


@dataclass
class Action:
    """Something the mentor did."""

    source_ref: str
    acted_at: datetime
    kind: str  # message | decision | label | status
    item_ref: str | None = None  # explicit link (CSV, REST)
    thread_ref: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    recipients: list[str] = field(default_factory=list)
    subject: str = ""
    text: str = ""
    decision: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    text_outputs: dict[str, str] = field(default_factory=dict)
    label: str | None = None
    status: str | None = None


@dataclass
class Batch:
    items: list[Item] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # per-record problems, no content
