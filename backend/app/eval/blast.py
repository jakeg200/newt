"""Blast radius: what a change does to past cases, before it goes live.

Each case in the suite is answered twice, without and with the change, on the same recordings, so the only
difference is the change. A case is right when the decision matches the team's and the role's evidence steps were
taken (the same standard as certification).

  fixed      wrong before, right after
  broke      right before, wrong after
  moved      a different answer, wrong both times
  unchanged  the same answer

The suite over-represents the cases the change touches, so it says nothing about the overall error bound; that is
re-certified on the frozen record when the change goes live.
"""

from dataclasses import dataclass
from typing import Any

EXAMPLES = 5


@dataclass(frozen=True)
class Answer:
    decision: str | None
    steps_ok: bool = True

    def right(self, truth: str | None) -> bool:
        return truth is not None and self.decision == truth and self.steps_ok


def classify(before: Answer, after: Answer, truth: str | None) -> str:
    was, now = before.right(truth), after.right(truth)
    if was and not now:
        return "broke"
    if now and not was:
        return "fixed"
    if before.decision != after.decision:
        return "moved"
    return "unchanged"


def radius(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """rows: {case_id, subject, truth, before: Answer, after: Answer}. Counts, agreement before and after, and a few
    examples of what was fixed and what broke, for the mentor to look at."""
    counts = {"fixed": 0, "broke": 0, "moved": 0, "unchanged": 0}
    examples: dict[str, list[dict[str, Any]]] = {"fixed": [], "broke": [], "moved": []}
    right_before = right_after = scored = 0
    for r in rows:
        kind = classify(r["before"], r["after"], r["truth"])
        counts[kind] += 1
        if r["truth"] is not None:
            scored += 1
            right_before += r["before"].right(r["truth"])
            right_after += r["after"].right(r["truth"])
        if kind in examples and len(examples[kind]) < EXAMPLES:
            examples[kind].append({"case_id": r["case_id"], "subject": r["subject"], "team": r["truth"],
                                   "before": r["before"].decision, "after": r["after"].decision})
    return {"cases": len(rows), **counts,
            "agreement_before": round(right_before / scored, 3) if scored else None,
            "agreement_after": round(right_after / scored, 3) if scored else None,
            "examples": examples}


def sentence(b: dict[str, Any]) -> str:
    """'Tested on 84 past cases: fixes 6, breaks none.'"""
    parts = [f"fixes {b['fixed']}" if b["fixed"] else "fixes none",
             f"breaks {b['broke']}" if b["broke"] else "breaks none"]
    if b.get("moved"):
        parts.append(f"changes {b['moved']} other answer{'s' if b['moved'] != 1 else ''}")
    return f"Tested on {b['cases']} past case{'s' if b['cases'] != 1 else ''}: " + ", ".join(parts) + "."
