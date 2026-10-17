"""Hand-back (learning to defer): when a graduated agent gives a case back to a person.

- its calibrated confidence is below τ;
- the item looks unlike anything it has seen (no similar past case);
- it says it's missing information;
- a hard rule fires (an amount above a limit, a named key account, anything always-escalate).

Each hand-back says why, and the mentor's answer becomes a lesson.
"""

import re
from typing import Any

from app.agents.context import CaseContext
from app.agents.output import PredictionResult
from app.learning.rules import words

OOD_SIMILARITY = 0.12  # closest past case less similar than this: unlike anything seen
_THRESHOLD = re.compile(r"\b(?:above|over|more than|exceeds?|greater than)\s+[£$€]?\s?(\d[\d,]*(?:\.\d+)?)", re.I)
_AMOUNT = re.compile(r"[£$€]\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:GBP|USD|EUR|pounds)\b", re.I)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def hard_rule_hits(rules: list[str], text: str) -> list[str]:
    hits = []
    low = text.lower()
    amounts = [_num(a or b) for a, b in _AMOUNT.findall(text)]
    for rule in rules:
        m = _THRESHOLD.search(rule)
        if m:
            if any(x > _num(m.group(1)) for x in amounts):
                hits.append(rule)
            continue
        ws = [w for w in words(rule)]
        if len(ws) >= 2 and sum(1 for w in ws if re.search(rf"\b{re.escape(w)}", low)) >= max(2, round(len(ws) * 2 / 3)):
            hits.append(rule)
    return hits


def item_text(ctx: CaseContext) -> str:
    item = ctx.of("item")[0].content
    return " ".join([item.get("subject", ""), *[str(v) for v in (item.get("inputs") or {}).values()]])


def decide(ctx: CaseContext, result: PredictionResult, confidence: float | None, tau: float | None) -> dict[str, Any]:
    reasons: list[str] = []
    if result.output is None:
        reasons.append(f"the agent couldn't answer: {result.error}")
    else:
        if tau is None:
            reasons.append("no confidence threshold set")
        elif confidence is None or confidence < tau:
            reasons.append(f"confidence {confidence or 0:.2f} is below the threshold {tau:.2f}")
        missing = result.output.get("missing_info") or []
        if missing:
            reasons.append("it's missing: " + "; ".join(missing[:3]))
    similar = [p.content.get("similarity", 0.0) for p in ctx.of("similar_case")]
    closest = max(similar, default=0.0)
    if closest < OOD_SIMILARITY:
        reasons.append(f"unlike anything it has seen (closest past case {closest:.2f})")
    for rule in hard_rule_hits(ctx.task.hard_rules, item_text(ctx)):
        reasons.append(f"always hand back: {rule}")
    return {"hand_back": bool(reasons), "reasons": reasons, "closest_similarity": round(closest, 3)}
