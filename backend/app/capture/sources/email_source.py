"""Email in any form (.eml files, an .mbox, Gmail raw messages) becomes items and actions.

Messages from the mentor's addresses are actions; everything else is an item. Quoted text in
replies is stripped, so a mentor's reply carries only what they wrote.
"""

import mailbox
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from app.capture.types import Action, Batch, HistoryEntry, Item

_MSGID = re.compile(r"<[^<>\s]+>")
_QUOTE_HEADER = re.compile(r"^\s*(On .{4,200}wrote:|-----\s*Original Message\s*-----|From: .+)$", re.I | re.M)


@dataclass
class ParsedEmail:
    message_id: str
    sender: str | None
    recipients: list[str]
    sent_at: datetime
    subject: str
    body: str
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    thread_ref: str | None = None
    attachments: list[str] = field(default_factory=list)


def _plain_body(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<br\s*/?>|</p>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    return text.replace("\r\n", "\n")


def strip_quoted(text: str) -> str:
    """Drop quoted history: '>' lines and everything after an 'On … wrote:' style header."""
    m = _QUOTE_HEADER.search(text)
    if m:
        text = text[: m.start()]
    lines = [line for line in text.split("\n") if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip()


def parse_email(raw: bytes, thread_ref: str | None = None) -> ParsedEmail:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    sender = next((a for _, a in getaddresses([str(msg.get("From", ""))]) if a), None)
    recipients = [a.lower() for _, a in getaddresses([str(msg.get(h, "")) for h in ("To", "Cc")]) if a]
    try:
        sent_at = parsedate_to_datetime(str(msg["Date"]))
    except (TypeError, ValueError):
        raise ValueError("message has no valid Date header") from None
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    message_id = (_MSGID.findall(str(msg.get("Message-ID", ""))) or [None])[0]
    if not message_id:
        raise ValueError("message has no Message-ID header")
    references = _MSGID.findall(str(msg.get("References", "")))
    in_reply_to = (_MSGID.findall(str(msg.get("In-Reply-To", ""))) or [None])[0]
    attachments = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    return ParsedEmail(
        message_id=message_id,
        sender=sender.lower() if sender else None,
        recipients=recipients,
        sent_at=sent_at,
        subject=str(msg.get("Subject", "")),
        body=_plain_body(msg),
        in_reply_to=in_reply_to,
        references=references,
        # Gmail supplies a thread id; otherwise the first message in the References chain.
        thread_ref=thread_ref or (references[0] if references else in_reply_to or message_id),
        attachments=attachments,
    )


def read_mbox(data: bytes) -> list[bytes]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.mbox"
        path.write_bytes(data)
        box = mailbox.mbox(str(path))
        try:
            return [m.as_bytes() for m in box]
        finally:
            box.close()


def emails_to_batch(emails: list[ParsedEmail], mentor_addresses: list[str], body_input: str) -> Batch:
    mentors = {a.strip().lower() for a in mentor_addresses}
    batch = Batch()
    by_thread: dict[str, list[ParsedEmail]] = {}
    for e in sorted(emails, key=lambda e: e.sent_at):
        by_thread.setdefault(e.thread_ref or e.message_id, []).append(e)

    for thread, messages in by_thread.items():
        for i, e in enumerate(messages):
            if e.sender in mentors:
                batch.actions.append(
                    Action(
                        source_ref=e.message_id,
                        acted_at=e.sent_at,
                        kind="message",
                        thread_ref=thread,
                        in_reply_to=e.in_reply_to,
                        references=e.references,
                        recipients=e.recipients,
                        subject=e.subject,
                        text=strip_quoted(e.body),
                    )
                )
            else:
                batch.items.append(
                    Item(
                        source_ref=e.message_id,
                        received_at=e.sent_at,
                        inputs={body_input: strip_quoted(e.body)},
                        subject=e.subject,
                        sender=e.sender,
                        thread_ref=thread,
                        message_ids=[e.message_id],
                        attachments=e.attachments,
                        history=[HistoryEntry(p.sent_at, p.sender, strip_quoted(p.body)) for p in messages[:i]],
                    )
                )
    return batch


def parse_uploads(files: list[tuple[str, bytes]], mentor_addresses: list[str], body_input: str) -> Batch:
    emails: list[ParsedEmail] = []
    errors: list[str] = []
    for name, data in files:
        lower = name.lower()
        raws = read_mbox(data) if lower.endswith(".mbox") else [data] if lower.endswith(".eml") else None
        if raws is None:
            errors.append(f"{name}: not an .eml or .mbox file")
            continue
        for n, raw in enumerate(raws, start=1):
            try:
                emails.append(parse_email(raw))
            except ValueError as exc:
                errors.append(f"{name} message {n}: {exc}")
    batch = emails_to_batch(emails, mentor_addresses, body_input)
    batch.errors = errors
    return batch
