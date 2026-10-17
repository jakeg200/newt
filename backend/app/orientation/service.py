"""Orientation workflow: documents in, handbook drafted, edited, approved and versioned."""

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.provider import Provider, ProviderError
from app.models import (
    Agent,
    Apprenticeship,
    Handbook,
    HandbookSource,
    Passage,
    QuestionnaireAnswer,
    SourceDocument,
    TaskType,
    User,
    utcnow,
)
from app.orientation import handbook as hb
from app.orientation.extract import extract_passages, mime_for
from app.orientation.questionnaire import label_for, questions_for

MAX_PROMPT_CHARS = 1_500_000  # ~400k tokens; well inside the model's context, and we never truncate


class OrientationError(ValueError):
    """A request that can't be done as asked. The message is safe to show users."""


@dataclass
class UploadResult:
    document: SourceDocument
    passages: int
    duplicate: bool


def org_teams(session: Session, org_id: str) -> list[str]:
    return list(
        session.scalars(
            select(Apprenticeship.team).join(Agent).where(Agent.org_id == org_id).distinct().order_by(Apprenticeship.team)
        )
    )


def require_team(session: Session, org_id: str, team: str) -> None:
    if team not in org_teams(session, org_id):
        raise LookupError(f"no team {team!r} in this organisation")


def team_task_types(session: Session, org_id: str, team: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(TaskType)
        .join(Apprenticeship)
        .join(Agent)
        .where(Agent.org_id == org_id, Apprenticeship.team == team)
        .order_by(TaskType.name)
    ).all()
    return [t.config for t in rows]


def add_document(session: Session, user: User, team: str, filename: str, data: bytes) -> UploadResult:
    mime = mime_for(filename)
    digest = hashlib.sha256(data).hexdigest()
    existing = session.scalar(
        select(SourceDocument).where(
            SourceDocument.org_id == user.org_id, SourceDocument.team == team, SourceDocument.sha256 == digest
        )
    )
    if existing:
        count = session.scalar(select(func.count()).select_from(Passage).where(Passage.document_id == existing.id))
        return UploadResult(existing, count or 0, duplicate=True)

    blocks = extract_passages(filename, data)  # raises ExtractionError before anything is stored
    doc_index = 1 + (
        session.scalar(
            select(func.max(SourceDocument.doc_index)).where(
                SourceDocument.org_id == user.org_id, SourceDocument.team == team
            )
        )
        or 0
    )
    document = SourceDocument(
        org_id=user.org_id,
        team=team,
        doc_index=doc_index,
        filename=filename[:300],
        mime=mime,
        sha256=digest,
        size_bytes=len(data),
        uploaded_by=user.id,
    )
    session.add(document)
    session.flush()
    for i, block in enumerate(blocks, start=1):
        session.add(Passage(document_id=document.id, label=f"{doc_index}.{i}", idx=i, text=block.text, page=block.page))
    session.commit()
    return UploadResult(document, len(blocks), duplicate=False)


def documents(session: Session, org_id: str, team: str) -> list[tuple[SourceDocument, int]]:
    rows = session.execute(
        select(SourceDocument, func.count(Passage.id))
        .outerjoin(Passage, Passage.document_id == SourceDocument.id)
        .where(SourceDocument.org_id == org_id, SourceDocument.team == team)
        .group_by(SourceDocument.id)
        .order_by(SourceDocument.doc_index)
    ).all()
    return [(doc, count) for doc, count in rows]


def delete_document(session: Session, org_id: str, document_id: str) -> None:
    doc = session.get(SourceDocument, document_id)
    if doc is None or doc.org_id != org_id:
        raise LookupError("document not found")
    session.delete(doc)
    session.commit()


def questionnaire(session: Session, org_id: str, team: str) -> list[dict[str, Any]]:
    answers = {
        a.question_key: a
        for a in session.scalars(
            select(QuestionnaireAnswer).where(QuestionnaireAnswer.org_id == org_id, QuestionnaireAnswer.team == team)
        )
    }
    out = []
    for q in questions_for(team_task_types(session, org_id, team)):
        a = answers.get(q["key"])
        out.append({**q, "label": label_for(q["key"]), "answer": a.answer if a else "", "answered_at": a.answered_at if a else None})
    return out


def save_answers(session: Session, user: User, team: str, answers: dict[str, str]) -> int:
    questions = {q["key"]: q["question"] for q in questions_for(team_task_types(session, user.org_id, team))}
    unknown = sorted(set(answers) - set(questions))
    if unknown:
        raise OrientationError(f"unknown question keys: {', '.join(unknown)}")
    saved = 0
    for key, text in answers.items():
        text = text.strip()
        row = session.scalar(
            select(QuestionnaireAnswer).where(
                QuestionnaireAnswer.org_id == user.org_id, QuestionnaireAnswer.team == team, QuestionnaireAnswer.question_key == key
            )
        )
        if not text:
            if row:
                session.delete(row)
            continue
        if row is None:
            row = QuestionnaireAnswer(org_id=user.org_id, team=team, question_key=key, question=questions[key], answer=text, mentor_id=user.id)
            session.add(row)
        else:
            row.answer, row.mentor_id, row.answered_at = text, user.id, utcnow()
        saved += 1
    session.commit()
    return saved


def sources(session: Session, org_id: str, team: str) -> list[dict[str, Any]]:
    """Everything the handbook may cite: document passages, then questionnaire answers."""
    out: list[dict[str, Any]] = [
        {"label": p.label, "document": d.filename, "document_id": d.id, "page": p.page, "text": p.text}
        for p, d in session.execute(
            select(Passage, SourceDocument)
            .join(SourceDocument)
            .where(SourceDocument.org_id == org_id, SourceDocument.team == team)
            .order_by(SourceDocument.doc_index, Passage.idx)
        )
    ]
    for q in questionnaire(session, org_id, team):
        if q["answer"]:
            out.append(
                {"label": q["label"], "document": "Mentor questionnaire", "document_id": None, "page": None,
                 "text": f"Q: {q['question']}\nA: {q['answer']}"}
            )
    return out


def _next_version(session: Session, org_id: str, team: str) -> int:
    current = session.scalar(select(func.max(Handbook.version)).where(Handbook.org_id == org_id, Handbook.team == team))
    return (current or 0) + 1


def _record_sources(session: Session, handbook: Handbook, content: hb.HandbookContent, srcs: list[dict[str, Any]]) -> None:
    by_label = {s["label"]: s for s in srcs}
    refs = {by_label[label]["document_id"] or "questionnaire" for label in hb.cited_labels(content) if label in by_label}
    for ref in sorted(refs):
        session.add(HandbookSource(handbook_id=handbook.id, document_ref=ref))


def draft(session: Session, user: User, team: str, provider: Provider) -> Handbook:
    srcs = sources(session, user.org_id, team)
    if not srcs:
        raise OrientationError("upload at least one document or answer the questionnaire first")
    prompt = hb.build_prompt(team, team_task_types(session, user.org_id, team), srcs)
    if len(prompt) > MAX_PROMPT_CHARS:
        raise OrientationError("these documents are too long to draft in one pass; remove the least relevant ones")

    result = provider.complete_json(
        task="handbook", system=hb.SYSTEM_PROMPT, user=prompt, schema=hb.OUTPUT_SCHEMA, effort=get_settings().handbook_effort
    )
    try:
        content = hb.parse_content(result.data)
    except ValueError as exc:
        raise ProviderError("the model's handbook didn't match the expected shape") from exc
    counters = hb.assign_ids(content)
    issues = hb.check_citations(content, {s["label"] for s in srcs})

    handbook = Handbook(
        org_id=user.org_id,
        team=team,
        version=_next_version(session, user.org_id, team),
        status="draft",
        content=content.model_dump(mode="json"),
        meta={**result.meta(), "drafted_by": user.id, "source_count": len(srcs), "issues": issues, "next_ids": counters},
    )
    session.add(handbook)
    session.flush()
    _record_sources(session, handbook, content, srcs)
    session.commit()
    return handbook


def get_handbook(session: Session, org_id: str, handbook_id: str) -> Handbook:
    handbook = session.get(Handbook, handbook_id)
    if handbook is None or handbook.org_id != org_id:
        raise LookupError("handbook not found")
    return handbook


def versions(session: Session, org_id: str, team: str) -> list[Handbook]:
    return list(
        session.scalars(
            select(Handbook).where(Handbook.org_id == org_id, Handbook.team == team).order_by(Handbook.version.desc())
        )
    )


def update_draft(session: Session, handbook: Handbook, raw_content: dict[str, Any]) -> Handbook:
    if handbook.status != "draft":
        raise OrientationError(f"version {handbook.version} is {handbook.status}; start a revision to change it")
    try:
        content = hb.parse_content(raw_content)
    except ValueError as exc:
        raise OrientationError(str(exc)) from exc
    counters = hb.assign_ids(content, handbook.meta.get("next_ids"))
    srcs = sources(session, handbook.org_id, handbook.team)
    issues = hb.check_citations(content, {s["label"] for s in srcs})
    handbook.content = content.model_dump(mode="json")
    handbook.meta = {**handbook.meta, "issues": issues, "next_ids": counters, "edited_at": utcnow().isoformat()}
    session.execute(HandbookSource.__table__.delete().where(HandbookSource.handbook_id == handbook.id))
    _record_sources(session, handbook, content, srcs)
    session.commit()
    return handbook


def approve(session: Session, handbook: Handbook, manager: User) -> Handbook:
    if handbook.status != "draft":
        raise OrientationError(f"version {handbook.version} is already {handbook.status}")
    content = hb.parse_content(handbook.content)
    # Re-check against today's sources: a document may have been removed since drafting.
    issues = hb.check_citations(content, {s["label"] for s in sources(session, handbook.org_id, handbook.team)})
    blocking = hb.blocking_issues(issues)
    if blocking:
        raise OrientationError(
            f"{len(blocking)} item(s) have no source ({', '.join(i['id'] for i in blocking[:8])}); cite or delete them first"
        )
    for previous in session.scalars(
        select(Handbook).where(Handbook.org_id == handbook.org_id, Handbook.team == handbook.team, Handbook.status == "approved")
    ):
        previous.status = "superseded"
    handbook.status = "approved"
    handbook.content = content.model_dump(mode="json")
    handbook.approved_by = manager.id
    handbook.approved_at = utcnow()
    handbook.meta = {**handbook.meta, "issues": issues}
    for apprenticeship in session.scalars(
        select(Apprenticeship).join(Agent).where(Agent.org_id == handbook.org_id, Apprenticeship.team == handbook.team)
    ):
        apprenticeship.handbook_version = handbook.version
    session.commit()
    return handbook


def revise(session: Session, handbook: Handbook, user: User) -> Handbook:
    """Start a new draft from an existing version (usually the approved one)."""
    if handbook.status == "draft":
        raise OrientationError("this version is already a draft; edit it directly")
    copy = Handbook(
        org_id=handbook.org_id,
        team=handbook.team,
        version=_next_version(session, handbook.org_id, handbook.team),
        status="draft",
        content=handbook.content,
        meta={
            "revised_from": handbook.version,
            "drafted_by": user.id,
            "provider": "manual",
            "issues": handbook.meta.get("issues", []),
            "next_ids": handbook.meta.get("next_ids", {}),
        },
    )
    session.add(copy)
    session.flush()
    srcs = sources(session, handbook.org_id, handbook.team)
    _record_sources(session, copy, hb.parse_content(copy.content), srcs)
    session.commit()
    return copy
