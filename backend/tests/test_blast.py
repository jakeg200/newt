"""Blast radius maths: fixed, broke, moved, unchanged, and the sentence Newt says."""

from app.eval.blast import Answer, classify, radius, sentence


def test_a_case_is_right_only_with_the_teams_decision_and_the_evidence():
    assert classify(Answer("escalate"), Answer("approve"), "approve") == "fixed"
    assert classify(Answer("approve"), Answer("escalate"), "approve") == "broke"
    assert classify(Answer("approve", steps_ok=True), Answer("approve", steps_ok=False), "approve") == "broke"  # luck isn't right
    assert classify(Answer("escalate"), Answer("query_supplier"), "approve") == "moved"
    assert classify(Answer("approve"), Answer("approve"), "approve") == "unchanged"
    assert classify(Answer("approve"), Answer("escalate"), None) == "moved"  # no team answer: never fixed or broke


def test_radius_counts_and_keeps_examples():
    rows = [{"case_id": f"c{i}", "subject": f"s{i}", "truth": "approve", "before": Answer(b), "after": Answer(a)}
            for i, (b, a) in enumerate([("escalate", "approve")] * 7 + [("approve", "escalate"), ("approve", "approve")])]
    b = radius(rows)
    assert (b["cases"], b["fixed"], b["broke"], b["unchanged"]) == (9, 7, 1, 1)
    assert len(b["examples"]["fixed"]) == 5 and b["examples"]["broke"][0]["subject"] == "s7"
    assert b["agreement_before"] == round(2 / 9, 3) and b["agreement_after"] == round(8 / 9, 3)
    assert sentence(b) == "Tested on 9 past cases: fixes 7, breaks 1."
    assert sentence(radius(rows[-1:])) == "Tested on 1 past case: fixes none, breaks none."
