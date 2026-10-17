"""Similar-case retrieval. TF-IDF cosine over redacted text: no external service, works on SQLite,
good enough for "show the agent how the mentor handled cases like this". Embeddings can replace
it behind the same interface."""

import math
import re
from collections import Counter

from app.capture.redact import strip_placeholders

_WORD = re.compile(r"[a-z][a-z0-9_-]{2,}")
_STOP = frozenset(
    "the and for with that this from have has are was were not but you your our out per any all can will "
    "please thanks regards kind hello dear".split()
)


def tokens(text: str) -> Counter[str]:
    """Words that describe the situation. Reference numbers (anything with a digit, like INV-30012
    or PO-7700) are left out: they identify one document, so matching on them finds the invoice a
    case mentions rather than cases like it."""
    return Counter(w for w in _WORD.findall(strip_placeholders(text).lower()) if w not in _STOP and not any(ch.isdigit() for ch in w))


class Index:
    def __init__(self, docs: dict[str, str]) -> None:
        self.tf = {doc_id: tokens(text) for doc_id, text in docs.items()}
        df: Counter[str] = Counter()
        for counts in self.tf.values():
            df.update(counts.keys())
        n = max(len(self.tf), 1)
        self.idf = {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}
        self.vec = {doc_id: self._weigh(counts) for doc_id, counts in self.tf.items()}

    def _weigh(self, counts: Counter[str]) -> dict[str, float]:
        v = {w: (1 + math.log(c)) * self.idf.get(w, 1.0) for w, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    def top_k(self, doc_id: str, candidates: list[str], k: int) -> list[tuple[str, float]]:
        query = self.vec.get(doc_id, {})
        scored = []
        for cid in candidates:
            other = self.vec.get(cid, {})
            small, large = (query, other) if len(query) < len(other) else (other, query)
            score = sum(x * large.get(w, 0.0) for w, x in small.items())
            if score > 0:
                scored.append((cid, score))
        scored.sort(key=lambda t: (-t[1], t[0]))
        return scored[:k]
