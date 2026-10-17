"""What an agent may see for a case, assembled as of the moment the item arrived, and the guard
that proves nothing from later leaked in.

Every piece of context records when that information existed. The guard checks those times
against `as_of` and scans the item, handbook and rules for the mentor's own words on this case.
A backtest refuses to predict a case whose context fails the guard.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.retrieval import Index
from app.models import Agent, Apprenticeship, Case, Handbook, HumanAction, Rule, TaskType
from app.task_types import TaskTypeConfig

# Knowledge the agent is given rather than evidence from the case stream: allowed whatever its
# date, but still scanned for the mentor's words on the case being predicted.
STANDING = frozenset({"handbook", "rule"})


class LeakageError(RuntimeError):
    """Context for a case contains information from after the item arrived."""


def utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Piece:
    kind: str  # item | history | similar_case | handbook | rule
    source_id: str
    observed_at: datetime | None
    content: dict[str, Any]


@dataclass
class CaseContext:
    case_id: str
    as_of: datetime
    task: TaskTypeConfig
    team: str
    handbook_version: int | None
    rules_version: int | None
    pieces: list[Piece] = field(default_factory=list)

    def of(self, kind: str) -> list[Piece]:
        return [p for p in self.pieces if p.kind == kind]

    def payload(self) -> dict[str, Any]:
        """The case as sent to any agent, built-in or external."""
        item = self.of("item")[0].content
        handbook = self.of("handbook")
        return {
            "case_id": self.case_id,
            "as_of": self.as_of.isoformat(),
            "team": self.team,
            "task_type": {
                "name": self.task.name, "trigger": self.task.trigger, "inputs": self.task.inputs,
                "decision": self.task.decision,
                "fields": {k: v.model_dump(exclude_none=True) for k, v in self.task.fields.items()},
                "text_outputs": self.task.text_outputs, "hard_rules": self.task.hard_rules,
            },
            "item": {**item, "history": [p.content for p in self.of("history")]},
            "handbook": handbook[0].content if handbook else None,
            "rules": [p.content for p in self.of("rule")],
            "similar_cases": [p.content for p in self.of("similar_case")],
        }


def check(ctx: CaseContext, forbidden_texts: list[str]) -> None:
    """Raise LeakageError if anything in the context postdates the item or quotes the mentor's
    response to it. `forbidden_texts` are the mentor's own outputs for this case."""
    for p in ctx.pieces:
        if p.kind == "similar_case" and p.source_id == ctx.case_id:
            raise LeakageError(f"case {ctx.case_id} appears among its own similar cases")
        if ctx.case_id in p.content.get("supporting_case_ids", []):
            raise LeakageError(f"{p.kind} {p.source_id} was learned from this very case")
        if p.kind not in STANDING:
            if p.observed_at is None or utc(p.observed_at) > ctx.as_of:
                raise LeakageError(
                    f"{p.kind} {p.source_id} is from {p.observed_at}, after the item arrived at {ctx.as_of.isoformat()}"
                )
    scanned = " ".join(" ".join(json.dumps(p.content, ensure_ascii=False).split()) for p in ctx.pieces if p.kind != "similar_case")
    for text in forbidden_texts:
        normal = " ".join(text.split())
        if len(normal) >= 20 and normal in scanned:
            raise LeakageError("the mentor's own response to this case appears in its context")


def mentor_outputs(actions: list[HumanAction]) -> list[str]:
    texts = []
    for a in actions:
        texts += [v for v in (a.payload.get("text_outputs") or {}).values() if isinstance(v, str)]
        if isinstance(a.payload.get("note"), str):
            texts.append(a.payload["note"])
    return texts


@dataclass
class Decided:
    """A past case with the mentor's decision, as retrieval candidates."""

    case: Case
    decided_at: datetime
    decision: str
    fields: dict[str, Any]
    text_outputs: dict[str, str]


class ContextBuilder:
    """Builds contexts for many cases of one task type, sharing one retrieval index."""

    def __init__(self, session: Session, task_type: TaskType, k: int = 5) -> None:
        self.session, self.task_type, self.k = session, task_type, k
        self.task = TaskTypeConfig.model_validate(task_type.config)
        apprenticeship = session.get(Apprenticeship, task_type.apprenticeship_id)
        self.team = apprenticeship.team
        agent = session.get(Agent, apprenticeship.agent_id)
        self.handbook = session.scalar(
            select(Handbook).where(Handbook.org_id == agent.org_id, Handbook.team == self.team, Handbook.status == "approved")
            .order_by(Handbook.version.desc()).limit(1)
        )
        self.rules = list(session.scalars(
            select(Rule).where(Rule.apprenticeship_id == apprenticeship.id, Rule.status == "active").order_by(Rule.id)
        ))
        self.rules_version = max((r.version for r in self.rules), default=None)

        # Captured cases only (they always come through a connection); the seed's placeholders don't count.
        captured = (Case.task_type_id == task_type.id, Case.connection_id.is_not(None))
        cases = {c.id: c for c in session.scalars(select(Case).where(*captured))}
        self.actions: dict[str, list[HumanAction]] = {}
        for a in session.scalars(select(HumanAction).join(Case).where(*captured).order_by(HumanAction.acted_at)):
            self.actions.setdefault(a.case_id, []).append(a)
        self.decided: dict[str, Decided] = {}
        for cid, acts in self.actions.items():
            first = next((a for a in acts if a.payload.get("decision")), None)
            if first:
                self.decided[cid] = Decided(cases[cid], utc(first.acted_at), first.payload["decision"],
                                            first.payload.get("fields") or {}, first.payload.get("text_outputs") or {})
        self.cases = cases
        self.index = Index({cid: _text(c) for cid, c in cases.items()})

    def build(self, case: Case) -> CaseContext:
        as_of = utc(case.received_at)
        ctx = CaseContext(case.id, as_of, self.task, self.team,
                          self.handbook.version if self.handbook else None, self.rules_version)
        snap = case.snapshot or {}
        ctx.pieces.append(Piece("item", case.id, as_of, {
            "received_at": as_of.isoformat(), "subject": snap.get("subject", ""), "from": snap.get("from"),
            "inputs": snap.get("inputs", {}), "attachments": snap.get("attachments", []),
        }))
        for h in snap.get("history", []):
            ctx.pieces.append(Piece("history", case.id, datetime.fromisoformat(h["at"]), h))
        if self.handbook:
            ctx.pieces.append(Piece("handbook", self.handbook.id, self.handbook.approved_at, self.handbook.content))
        for r in self.rules:
            ctx.pieces.append(Piece("rule", r.id, None, {"text": r.text, "supporting_case_ids": r.supporting_case_ids}))

        # Only cases whose decision was known before this item arrived.
        candidates = [cid for cid, d in self.decided.items() if cid != case.id and d.decided_at < as_of
                      and utc(d.case.received_at) < as_of]
        for cid, score in self.index.top_k(case.id, candidates, self.k):
            d = self.decided[cid]
            snap_c = d.case.snapshot or {}
            ctx.pieces.append(Piece("similar_case", cid, d.decided_at, {
                "received_at": utc(d.case.received_at).isoformat(), "subject": snap_c.get("subject", ""),
                "inputs": snap_c.get("inputs", {}), "mentor_decision": d.decision, "mentor_fields": d.fields,
                "mentor_text_outputs": d.text_outputs, "similarity": round(score, 3),
            }))
        return ctx

    def forbidden(self, case: Case) -> list[str]:
        return mentor_outputs(self.actions.get(case.id, []))

    def mentor_decision(self, case: Case) -> Decided | None:
        return self.decided.get(case.id)


def _text(case: Case) -> str:
    snap = case.snapshot or {}
    return " ".join([snap.get("subject", ""), *[str(v) for v in (snap.get("inputs") or {}).values()]])
