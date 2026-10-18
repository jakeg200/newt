"""What Newt asks, and why: only questions worth a person's time.

Work items (drafts to approve, cases handed back) always come through: they're the person's job anyway.
Questions are ranked by value and rationed by the etiquette budget:

- unsure cases it's shadowing: uncertainty x how many similar open cases the answer would settle. Its own guess
  stays sealed until the person has answered;
- cases where it differed from the mentor in the latest backtest (already decided, so nothing is revealed early);
- the role's question bank from the task-type config (first-week questions any good intern would ask).

Every candidate has a dedupe key, so Newt never asks the same thing twice.
"""

import math
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.retrieval import Index
from app.learning import teaching
from app.live import pending_drafts
from app.models import Agent, Apprenticeship, Case, Prediction, QuestionnaireAnswer, TaskType
from app.orientation.questionnaire import _slug
from app.task_types import TaskTypeConfig

UNSURE_BELOW = 0.7  # calibrated confidence under which Newt would rather ask
MIN_VALUE = 0.3  # questions worth less than this aren't asked at all
SIMILAR = 0.35  # TF-IDF similarity at which two open cases count as "the same kind of thing"


@dataclass
class Candidate:
    kind: str  # question | handback | draft
    dedupe_key: str
    body: str
    payload: dict[str, Any] = field(default_factory=dict)
    value: float = 1.0  # for questions: how much the answer is worth
    work: bool = False  # work items skip the question budget


def _label(s: str | None) -> str:
    return (s or "").replace("_", " ")


def _subject(case: Case) -> str:
    return (case.snapshot or {}).get("subject") or "this case"


def _text(case: Case) -> str:
    snap = case.snapshot or {}
    return " ".join([snap.get("subject", ""), *[str(v) for v in (snap.get("inputs") or {}).values()]])


def value_of_question(confidence: float, similar_open: int) -> float:
    """How much an answer is worth: more when Newt is less sure and when it would settle more open cases."""
    return round((1.0 - confidence) * (1.0 + math.log1p(similar_open)), 4)


def work_items(session: Session, tt: TaskType) -> list[Candidate]:
    task = TaskTypeConfig.model_validate(tt.config)
    out: list[Candidate] = []
    for d in pending_drafts(session, tt):
        agent = d["agent"]
        reply = next(iter((agent.get("text_outputs") or {}).values()), "")
        out.append(Candidate(
            kind="draft", dedupe_key=f"draft:{d['prediction_id']}", work=True,
            body=f"I've drafted {d['case']['subject'] or 'a case'}: I'd {_label(agent.get('decision'))}." + (" Reply ready to send." if reply else ""),
            payload={"prediction_id": d["prediction_id"], "case": {"id": d["case"]["id"], "subject": d["case"]["subject"], "inputs": d["case"]["inputs"]},
                     "decision": agent.get("decision"), "reply": reply, "confidence": d["confidence"], "options": task.decision}))
    rows = session.execute(select(Prediction, Case).join(Case, Case.id == Prediction.case_id).where(
        Case.task_type_id == tt.id, Case.status == "open", Prediction.run_id.is_(None))).all()
    for p, case in rows:
        hb = (p.output or {}).get("hand_back") or {}
        if any(str(r).startswith("couldn't finish") for r in hb.get("reasons") or []):
            continue  # execution already told the mentor, with a "try again" option
        if hb.get("hand_back"):
            reasons = hb.get("reasons") or []
            out.append(Candidate(
                kind="handback", dedupe_key=f"handback:{p.id}", work=True,
                body=f"I've handed {_subject(case)} back to you" + (f": {reasons[0].rstrip('.')}." if reasons else ".") + " What should happen?",
                payload={"prediction_id": p.id, "case": {"id": case.id, "subject": _subject(case), "inputs": (case.snapshot or {}).get("inputs", {})},
                         "reasons": reasons, "options": task.decision}))
    return out


def questions(session: Session, tt: TaskType) -> list[Candidate]:
    task = TaskTypeConfig.model_validate(tt.config)
    out: list[Candidate] = []

    # Unsure cases it is shadowing: ask before the mentor gets to them, never showing its own guess.
    if tt.status in ("shadow", "demoted"):
        rows = session.execute(select(Prediction, Case).join(Case, Case.id == Prediction.case_id).where(
            Case.task_type_id == tt.id, Case.status == "open", Prediction.run_id.is_(None), Prediction.confidence.is_not(None))).all()
        if rows:
            index = Index({c.id: _text(c) for _, c in rows})
            ids = [c.id for _, c in rows]
            for p, case in rows:
                if p.confidence is None or p.confidence >= UNSURE_BELOW:
                    continue
                similar = sum(1 for _, s in index.top_k(case.id, [i for i in ids if i != case.id], 50) if s >= SIMILAR)
                out.append(Candidate(
                    kind="question", dedupe_key=f"unsure:{p.id}", value=value_of_question(p.confidence, similar),
                    body=f"I'm not sure what you'd do with {_subject(case)}." + (f" There are {similar} more like it waiting." if similar else "") + " What's your call?",
                    payload={"type": "case", "prediction_id": p.id, "case": {"id": case.id, "subject": _subject(case), "inputs": (case.snapshot or {}).get("inputs", {})},
                             "options": task.decision, "similar": similar}))

    # Where it differed from the mentor (already decided, so revealing its answer is fine).
    for card in teaching.queue(session, tt, limit=5)["cards"]:
        if card["kind"] != "disagreement":
            continue
        mentor, agent = card["mentor"]["decision"], card["agent"]["decision"]
        out.append(Candidate(
            kind="question", dedupe_key=f"lesson:{card['prediction_id']}", value=0.6,
            body=f"On {card['case']['subject'] or 'one case'} you chose {_label(mentor)}; I'd have chosen {_label(agent)}. Was I wrong?",
            payload={"type": "lesson", "prediction_id": card["prediction_id"], "mentor": mentor, "agent": agent,
                     "options": ["intern_wrong", "both_fine", "mentor_changed", "couldnt_know"]}))

    # The role's first-week questions, until they're answered.
    if task.question_bank:
        app_ = session.get(Apprenticeship, tt.apprenticeship_id)
        org_id = session.get(Agent, app_.agent_id).org_id
        team = app_.team
        answered = set(session.scalars(select(QuestionnaireAnswer.question_key).where(
            QuestionnaireAnswer.org_id == org_id, QuestionnaireAnswer.team == team)))
        for i, q in enumerate(task.question_bank):
            key = f"{_slug(task.name, 40)}.bank.{q.key}"
            if key not in answered:
                out.append(Candidate(kind="question", dedupe_key=f"bank:{tt.id}:{q.key}", value=0.5 - i * 0.01, body=q.question,
                                     payload={"type": "bank", "key": key, "team": team}))

    return sorted((c for c in out if c.value >= MIN_VALUE), key=lambda c: -c.value)
