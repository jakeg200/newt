"""The judgement ledger: the firm's decision IP, written down from behaviour.

Copilot can find the documents a team wrote. What a role really runs on is what nobody wrote: the exceptions,
thresholds and "we never do that for them". Newt captures it from decisions, disagreements and answers:

written     the approved handbook, each item with its source passage
unwritten   rules learned from behaviour or stated by the mentor, each with example cases, who taught it, how many
            decisions it governs (coverage), how often the team's decisions agree with it (its test), and the
            mentor's own "why" notes from lessons
exceptions  patterns in Newt's disagreements with the mentor that look like an unwritten rule, proposed for the
            mentor to confirm (confirming makes it a rule through the normal, versioned path)
conflicts   rules that fire on the same cases but point at different decisions

Nothing here scores a person; coverage and tests are about the knowledge.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import ContextBuilder, Decided
from app.learning import improve
from app.learning.rules import _case_text, label, parse, phrases
from app.models import Comparison, Handbook, Lesson, Prediction, Rule, TaskType, User
from app.task_types import TaskTypeConfig

TESTED_AT = 0.9  # a rule "passes" when the team's decisions agree with it at least this often
EXCEPTION_MIN = 3  # disagreements sharing a pattern before Newt suggests it's an unwritten rule


def _decided(session: Session, tt: TaskType) -> list[Decided]:
    return list(ContextBuilder(session, tt).decided.values())


def rule_evidence(rule_text: str, task: TaskTypeConfig, decided: list[Decided]) -> dict[str, Any]:
    """How many past decisions a rule governs and how often the team's decision matched it."""
    parsed = parse(rule_text, task)
    hits = [d for d in decided if parsed.matches(_case_text(d))]
    agree = sum(1 for d in hits if parsed.decision and d.decision == parsed.decision)
    precision = round(agree / len(hits), 3) if hits else None
    return {"coverage": len(hits), "share": round(len(hits) / len(decided), 3) if decided else 0.0, "agreement": precision,
            "passes": precision is not None and precision >= TESTED_AT and len(hits) >= 3,
            "examples": [(d.case.snapshot or {}).get("subject", "") for d in hits[:3]],
            "case_ids": [d.case.id for d in hits[:20]]}


def exceptions(session: Session, tt: TaskType, decided: list[Decided] | None = None) -> list[dict[str, Any]]:
    """Patterns in where Newt was wrong that look like a rule the team never wrote down."""
    task = TaskTypeConfig.model_validate(tt.config)
    decided = decided if decided is not None else _decided(session, tt)
    by_case = {d.case.id: d for d in decided}
    wrong = session.execute(select(Comparison, Prediction).join(Prediction, Prediction.id == Comparison.prediction_id)
                            .where(Comparison.case_id.in_(list(by_case)) if by_case else Comparison.case_id.is_(None))).all()
    misses = {c.case_id: by_case[c.case_id] for c, p in wrong
              if c.case_id in by_case and not c.decision_match and c.effective_agreement is False}
    if len(misses) < EXCEPTION_MIN:
        return []
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for cid, d in misses.items():
        for g in phrases(_case_text(d)):
            groups[(g, d.decision)].add(cid)
    existing = [r.text.lower() for r in session.scalars(select(Rule).where(Rule.apprenticeship_id == tt.apprenticeship_id, Rule.status != "retired"))]
    out = []
    for (phrase, decision), ids in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(ids) < EXCEPTION_MIN or any(f'"{phrase}"' in t for t in existing):
            continue
        text = f'When an item mentions "{phrase}", choose {label(decision)}.'
        ev = rule_evidence(text, task, decided)
        if ev["agreement"] is None or ev["agreement"] < 0.8:
            continue  # the team doesn't actually do this consistently
        out.append({"text": text, "decision": decision, "phrase": phrase, "misses": len(ids), **ev,
                    "key": f"{phrase}->{decision}"})
        if len(out) >= 3:
            break
    return out


def conflicts(rules: list[Rule], task: TaskTypeConfig, decided: list[Decided]) -> list[dict[str, Any]]:
    out = []
    parsed = [(r, parse(r.text, task)) for r in rules if r.status == "active"]
    for i, (a, pa) in enumerate(parsed):
        for b, pb in parsed[i + 1:]:
            if not pa.decision or not pb.decision or pa.decision == pb.decision:
                continue
            both = [d for d in decided if pa.matches(_case_text(d)) and pb.matches(_case_text(d))]
            if len(both) >= 2:
                out.append({"rules": [a.text, b.text], "cases": len(both), "examples": [(d.case.snapshot or {}).get("subject", "") for d in both[:2]]})
    return out


def ledger(session: Session, tt: TaskType) -> dict[str, Any]:
    task = TaskTypeConfig.model_validate(tt.config)
    builder = ContextBuilder(session, tt)
    decided = list(builder.decided.values())
    written = []
    hb: Handbook | None = builder.handbook
    if hb:
        content = hb.content or {}
        for kind, key in (("procedure", "procedures"), ("decision rule", "decision_rules"), ("always escalate", "always_escalate")):
            for item in content.get(key, []):
                written.append({"kind": kind, "text": item.get("text") or item.get("title") or "", "sources": item.get("sources", []),
                                "steps": item.get("steps")})
    rules = list(session.scalars(select(Rule).where(Rule.apprenticeship_id == tt.apprenticeship_id).order_by(Rule.created_at)))
    names = {u.id: u.name for u in session.scalars(select(User).where(User.id.in_([r.created_by for r in rules if r.created_by])))}
    unwritten = []
    for r in rules:
        if r.status == "retired":
            continue
        unwritten.append({"id": r.id, "text": r.text, "decision": r.decision, "status": r.status,
                          "learned": "from behaviour" if r.source == "inferred" else "told by the mentor",
                          "taught_by": names.get(r.created_by or ""), "since": r.created_at, "version": r.version,
                          **rule_evidence(r.text, task, decided)})
    notes = [{"note": lesson.note, "case": (builder.cases[lesson.case_id].snapshot or {}).get("subject", ""), "at": lesson.created_at}
             for lesson in session.scalars(select(Lesson).where(Lesson.note.is_not(None)).order_by(Lesson.created_at))
             if lesson.case_id in builder.cases][-20:]
    governed = set()
    for r in unwritten:
        if r["status"] != "active":
            continue  # only rules Newt actually uses explain decisions
        p = parse(r["text"], task)
        governed |= {d.case.id for d in decided if p.matches(_case_text(d))}
    return {"written": written, "unwritten": unwritten, "notes": notes, "exceptions": exceptions(session, tt, decided),
            "conflicts": conflicts(rules, task, decided), "decisions": len(decided),
            "explicit_share": round(len(governed) / len(decided), 3) if decided else 0.0,
            "handbook_version": hb.version if hb else None, "changes": improve.log_of(session, tt, 30)}


def markdown(tt: TaskType, led: dict[str, Any], intern: str) -> str:
    lines = [f"# {tt.name}: how the team decides", "", f"Written down by {intern} from the team's own decisions.", ""]
    lines += ["## Written (the handbook)", ""] + [f"- **{w['kind']}**: {w['text']} ({', '.join(w['sources'])})" for w in led["written"]] or ["- none yet"]
    lines += ["", "## Unwritten (learned from how the team actually decides)", ""]
    for u in led["unwritten"]:
        test = "passes" if u["passes"] else "not yet proven"
        lines.append(f"- {u['text']} — {u['learned']}; governs {u['coverage']} past decisions; the team agrees "
                     f"{round((u['agreement'] or 0) * 100)}% of the time ({test}).")
    if led["notes"]:
        lines += ["", "## In the mentor's words", ""] + [f"- \"{n['note']}\" (on {n['case']})" for n in led["notes"]]
    if led["conflicts"]:
        lines += ["", "## Conflicts to resolve", ""] + [f"- {' / '.join(c['rules'])} ({c['cases']} cases)" for c in led["conflicts"]]
    return "\n".join(lines) + "\n"


def pdf(tt: TaskType, led: dict[str, Any], intern: str) -> bytes:
    from fpdf import FPDF

    from app.graduation.track_record import _safe

    doc = FPDF(format="A4")
    doc.add_page()
    doc.set_font("Helvetica", "B", 16)
    doc.multi_cell(0, 9, _safe(f"{tt.name}: how the team decides"), new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", "", 10)
    for line in markdown(tt, led, intern).splitlines()[2:]:
        if line.startswith("## "):
            doc.ln(2)
            doc.set_font("Helvetica", "B", 12)
            doc.multi_cell(0, 7, _safe(line[3:]), new_x="LMARGIN", new_y="NEXT")
            doc.set_font("Helvetica", "", 10)
        elif line.strip():
            doc.multi_cell(0, 5.5, _safe(line.replace("**", "")), new_x="LMARGIN", new_y="NEXT")
    return bytes(doc.output())
