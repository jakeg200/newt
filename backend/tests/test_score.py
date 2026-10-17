from app.eval.score import compare, field_matches
from app.task_types import FieldSpec, TaskTypeConfig

TASK = TaskTypeConfig.model_validate({
    "name": "t", "trigger": "x", "inputs": ["a"], "decision": ["approve", "query"],
    "fields": {"reason": {"type": "enum", "critical": True, "options": ["price", "quantity"]},
               "amount": {"type": "number", "critical": True},
               "note": {"type": "text"}},
    "text_outputs": ["email"], "alpha": 0.02, "min_cases": 10,
})


def test_numbers_and_text_are_normalised():
    num, text = FieldSpec(type="number"), FieldSpec(type="string")
    assert field_matches(num, "£1,200.00", 1200)
    assert field_matches(num, 1200, "1203")  # within 0.5%
    assert not field_matches(num, 1200, 1250)
    assert field_matches(text, " GL 6400. ", "gl   6400")
    assert not field_matches(text, "6400", None)


def test_agreement_needs_decision_and_observed_critical_fields():
    out = {"decision": "approve", "fields": {"reason": "price", "amount": 99, "note": "x"}}
    ok = compare(TASK, out, "approve", {"reason": "price", "amount": "99.00"}, {})
    assert ok["agreement"] and ok["critical_match"] is True and "note" not in ok["field_scores"]

    wrong_field = compare(TASK, out, "approve", {"reason": "quantity"}, {})
    assert wrong_field["decision_match"] and not wrong_field["agreement"]

    unobserved = compare(TASK, out, "approve", {}, {})
    assert unobserved["agreement"] and unobserved["critical_match"] is None and unobserved["field_scores"] == {}

    wrong_decision = compare(TASK, out, "query", {"reason": "price"}, {"email": "Please resend"})
    assert not wrong_decision["agreement"]
    assert wrong_decision["text_judgement"] == {"status": "pending", "outputs": ["email"]}
