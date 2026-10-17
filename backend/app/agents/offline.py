"""Offline baseline used when no API key is set: do what the mentor did on the most similar past
cases. Honest and cheap, and a floor any real agent should beat."""

import time
from collections import defaultdict

from app.agents.context import CaseContext
from app.agents.output import PredictionResult

MODEL = "offline-nearest-cases"


class NearestCasesAgent:
    model = MODEL

    def predict(self, ctx: CaseContext) -> PredictionResult:
        started = time.monotonic()
        neighbours = [p.content for p in ctx.of("similar_case")]
        if not neighbours:
            return PredictionResult(None, None, MODEL, error="no earlier decided cases to learn from")
        weight: dict[str, float] = defaultdict(float)
        for n in neighbours:
            weight[n["mentor_decision"]] += n["similarity"]
        decision = max(weight, key=lambda d: (weight[d], d))
        best = max((n for n in neighbours if n["mentor_decision"] == decision), key=lambda n: n["similarity"])
        confidence = weight[decision] / sum(weight.values())
        output = {
            "decision": decision,
            "fields": {k: v for k, v in best["mentor_fields"].items() if k in ctx.task.fields},
            "text_outputs": {k: v for k, v in best["mentor_text_outputs"].items() if k in ctx.task.text_outputs},
            "rationale": f"The mentor chose {decision} on the most similar earlier case: {best['subject'] or 'untitled'}.",
            "missing_info": [],
            "self_reported_confidence": round(confidence, 3),
        }
        return PredictionResult(output, confidence, MODEL, latency_ms=int((time.monotonic() - started) * 1000))
