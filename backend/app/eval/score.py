"""Scoring one prediction against what the mentor did.

Decision: exact match (the primary metric). Structured fields: compared after normalising, only
where the mentor's value is known. A case agrees when the decision and every observed critical
field match. Text outputs are judged in M4 (LLM judge); until then they're marked pending.
"""

import re
from typing import Any

from app.task_types import FieldSpec, TaskTypeConfig

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _text(value: Any) -> str:
    return " ".join(str(value).lower().split()).strip(" .,;:!")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUMBER.search(str(value).replace(",", ""))
    return float(m.group(0)) if m else None


def field_matches(spec: FieldSpec, mentor: Any, agent: Any) -> bool:
    if agent is None:
        return False
    if spec.type == "number":
        a, b = _number(mentor), _number(agent)
        return a is not None and b is not None and abs(a - b) <= max(0.01, 0.005 * abs(a))
    if spec.type == "boolean":
        truthy = {"true", "yes", "1", "y"}
        return (_text(mentor) in truthy) == (_text(agent) in truthy)
    return _text(mentor) == _text(agent)


def step_checks(task: TaskTypeConfig, trajectory: list[dict[str, Any]] | None, decision: str | None) -> dict[str, Any]:
    """Checks on how an answer was reached. A right answer without the evidence the role requires (e.g. approving
    without looking up the purchase order) doesn't count as agreement: that's luck, not competence.

    Only applies when the agent worked the case with tools; plain answers are scored as before."""
    if trajectory is None:
        return {"checked": False, "ok": True}
    used = [s.get("tool") for s in trajectory]
    allowed = set(task.tools) | {"propose"}
    disallowed = sorted({t for t in used if t not in allowed})
    missing = [t for t in task.required_steps.get(decision or "", []) if t not in used]
    return {"checked": True, "ok": not disallowed and not missing, "missing": missing, "disallowed": disallowed,
            "steps": len(trajectory)}


def same_answer(task: TaskTypeConfig, a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Same decision and the same critical field values: the same alternative, for teaching purposes."""
    if a.get("decision") != b.get("decision"):
        return False
    fa, fb = a.get("fields") or {}, b.get("fields") or {}
    return all(
        (fa.get(n) in (None, "") and fb.get(n) in (None, "")) or (fa.get(n) is not None and field_matches(spec, fb.get(n), fa.get(n)))
        for n, spec in task.fields.items() if spec.critical
    )


def inherited_attribution(task: TaskTypeConfig, output: dict[str, Any], teaching: dict[str, Any] | None) -> str | None:
    """What the mentor already taught about this case carries over to later predictions of it:
    "I'd change my call" keeps the case out of the score, and an alternative the mentor called
    "both fine" stays acceptable when the agent gives it again."""
    if not teaching:
        return None
    if teaching.get("mentor_changed"):
        return "mentor_changed"
    if any(same_answer(task, output, accepted) for accepted in teaching.get("accepted", [])):
        return "both_fine"
    return None


def prior_teaching(session, case_ids: list[str]) -> dict[str, dict[str, Any]]:
    from sqlalchemy import select

    from app.models import Lesson, Prediction

    out: dict[str, dict[str, Any]] = {}
    if not case_ids:
        return out
    rows = session.execute(select(Lesson, Prediction).join(Prediction, Prediction.id == Lesson.prediction_id)
                           .where(Lesson.case_id.in_(case_ids), Lesson.attribution.in_(("both_fine", "mentor_changed")))).all()
    for lesson, prediction in rows:
        t = out.setdefault(lesson.case_id, {"accepted": [], "mentor_changed": False})
        if lesson.attribution == "mentor_changed":
            t["mentor_changed"] = True
        else:
            t["accepted"].append(prediction.output or {})
    return out


def compare(task: TaskTypeConfig, output: dict[str, Any], mentor_decision: str, mentor_fields: dict[str, Any],
            mentor_texts: dict[str, str]) -> dict[str, Any]:
    decision_match = output.get("decision") == mentor_decision
    agent_fields = output.get("fields") or {}
    field_scores: dict[str, Any] = {}
    for name, spec in task.fields.items():
        if mentor_fields.get(name) in (None, ""):
            continue  # not observed for this case: neither right nor wrong
        field_scores[name] = {
            "mentor": mentor_fields[name], "agent": agent_fields.get(name),
            "match": field_matches(spec, mentor_fields[name], agent_fields.get(name)), "critical": spec.critical,
        }
    critical = [s["match"] for s in field_scores.values() if s["critical"]]
    critical_match = all(critical) if critical else None
    pending_texts = sorted(k for k in task.text_outputs if mentor_texts.get(k))
    return {
        "decision_match": decision_match,
        "field_scores": field_scores,
        "critical_match": critical_match,
        "agreement": decision_match and critical_match is not False,
        "text_judgement": {"status": "pending", "outputs": pending_texts} if pending_texts else {},
    }
