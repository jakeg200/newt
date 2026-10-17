"""Offline baseline used when no API key is set: follow the first active rule that clearly applies,
otherwise do what the mentor did on the most similar past cases. Honest and cheap, and a floor any
real agent should beat."""

import time
from collections import defaultdict

from app.agents.context import CaseContext
from app.agents.output import PredictionResult

MODEL = "offline-nearest-cases"


class NearestCasesAgent:
    model = MODEL

    def predict(self, ctx: CaseContext) -> PredictionResult:
        from app.learning.rules import parse  # rules import context; keep this module importable on its own

        started = time.monotonic()
        neighbours = [p.content for p in ctx.of("similar_case")]
        item = ctx.of("item")[0].content
        item_text = " ".join([item.get("subject", ""), *[str(v) for v in (item.get("inputs") or {}).values()]])

        rule_hit = None
        for r in ctx.of("rule"):
            parsed = parse(r.content["text"], ctx.task)
            if parsed.decision and parsed.matches(item_text):
                rule_hit = (r.content["text"], parsed.decision)
                break

        if rule_hit is None and not neighbours:
            return PredictionResult(None, None, MODEL, error="no earlier decided cases to learn from")

        weight: dict[str, float] = defaultdict(float)
        for n in neighbours:
            weight[n["mentor_decision"]] += n["similarity"]
        if rule_hit:
            decision, confidence = rule_hit[1], 0.9
            rationale = f"Rule: {rule_hit[0]}"
        else:
            decision = max(weight, key=lambda d: (weight[d], d))
            confidence = weight[decision] / sum(weight.values())
        same = [n for n in neighbours if n["mentor_decision"] == decision]
        best = max(same, key=lambda n: n["similarity"]) if same else None
        if not rule_hit:
            rationale = f"The mentor chose {decision} on the most similar earlier case: {best['subject'] or 'untitled'}."
        output = {
            "decision": decision,
            "fields": {k: v for k, v in (best or {}).get("mentor_fields", {}).items() if k in ctx.task.fields},
            "text_outputs": {k: v for k, v in (best or {}).get("mentor_text_outputs", {}).items() if k in ctx.task.text_outputs},
            "rationale": rationale,
            "missing_info": [],
            "self_reported_confidence": round(confidence, 3),
        }
        return PredictionResult(output, confidence, MODEL, latency_ms=int((time.monotonic() - started) * 1000))
