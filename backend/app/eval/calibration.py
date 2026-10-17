"""Confidence: two signals, calibrated.

1. Self-consistency: the share of the agent's samples that agreed (from the prediction).
2. A small classifier: logistic regression on the item's (redacted) words, trained on the
   mentor's past decisions. Its probability for the agent's decision is a second opinion, and its
   weights are a readable view of the mentor's criteria.

The two are averaged and calibrated with isotonic regression against whether the agent actually
agreed with the mentor, so "0.9" means agreed about 90% of the time. The classifier only ever
trains on cases decided before the one it scores: no time travel.
"""

import warnings
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from app.capture.redact import strip_placeholders

MIN_TRAINING = 20
BLOCKS = 5


@dataclass
class Example:
    """A decided case the classifier can learn from."""

    decided_at: datetime
    text: str
    decision: str


@dataclass
class Scored:
    """One prediction to score."""

    case_id: str
    as_of: datetime
    text: str
    agent_decision: str
    self_consistency: float | None


class DecisionModel:
    def __init__(self, examples: list[Example]) -> None:
        self.classes: list[str] = []
        self.model = None
        decisions = {e.decision for e in examples}
        if len(examples) < MIN_TRAINING or len(decisions) < 2:
            return
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b")
        try:
            x = self.vectorizer.fit_transform([strip_placeholders(e.text) for e in examples])
        except ValueError:  # empty vocabulary
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            self.model = LogisticRegression(max_iter=2000, C=2.0).fit(x, [e.decision for e in examples])
        self.classes = list(self.model.classes_)

    def prob(self, text: str, decision: str) -> float | None:
        if self.model is None or decision not in self.classes:
            return None if self.model is None else 0.0
        p = self.model.predict_proba(self.vectorizer.transform([strip_placeholders(text)]))[0]
        return float(p[self.classes.index(decision)])

    def top_terms(self, per_class: int = 5) -> dict[str, list[str]]:
        """The words that push hardest towards each decision: the mentor's criteria, as the model sees them."""
        if self.model is None:
            return {}
        names = self.vectorizer.get_feature_names_out()
        coef = self.model.coef_
        if len(self.classes) == 2:
            coef = np.vstack([-coef[0], coef[0]])
        return {c: [names[i] for i in np.argsort(coef[j])[::-1][:per_class]] for j, c in enumerate(self.classes)}


def classifier_probs(history: list[Example], items: list[Scored]) -> dict[str, float | None]:
    """Forward chaining: items are split into chronological blocks, and each block's model is
    trained only on decisions made before that block began."""
    history = sorted(history, key=lambda e: e.decided_at)
    times = [e.decided_at for e in history]
    ordered = sorted(items, key=lambda s: s.as_of)
    out: dict[str, float | None] = {}
    if not ordered:
        return out
    size = max(1, -(-len(ordered) // BLOCKS))
    for start in range(0, len(ordered), size):
        block = ordered[start:start + size]
        cutoff = block[0].as_of
        model = DecisionModel(history[: bisect_left(times, cutoff)])
        for s in block:
            out[s.case_id] = model.prob(s.text, s.agent_decision)
    return out


def raw_score(self_consistency: float | None, classifier: float | None) -> float:
    signals = [x for x in (self_consistency, classifier) if x is not None]
    return float(sum(signals) / len(signals)) if signals else 0.0


@dataclass
class Calibrator:
    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)

    def __call__(self, raw: float) -> float:
        if not self.x:
            return raw
        return float(np.interp(raw, self.x, self.y))

    def dump(self) -> dict:
        return {"x": self.x, "y": self.y}

    @classmethod
    def load(cls, data: dict | None) -> "Calibrator":
        return cls(list((data or {}).get("x", [])), list((data or {}).get("y", [])))


def fit_calibrator(raws: list[float], agreed: list[bool]) -> Calibrator:
    if len(raws) < MIN_TRAINING or len(set(agreed)) < 2:
        return Calibrator()  # too little to calibrate, or nothing to separate: use raw scores
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(raws, [float(a) for a in agreed])
    return Calibrator([float(v) for v in iso.X_thresholds_], [float(v) for v in iso.y_thresholds_])
