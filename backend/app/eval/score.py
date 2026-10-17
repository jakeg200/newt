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
