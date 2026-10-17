import json
import shutil
from pathlib import Path

import pytest

from app.config import get_settings
from app.task_types import TaskTypeConfigError, load_all, load_task_type

TASK_TYPES_DIR = get_settings().task_types_dir


def test_both_synthetic_task_types_load_from_config():
    configs = load_all(TASK_TYPES_DIR)
    assert set(configs) == {"invoice_mismatch", "repair_request"}
    invoice, repair = configs["invoice_mismatch"], configs["repair_request"]
    # Genuinely different task types, not copies.
    assert invoice.decision != repair.decision
    assert invoice.inputs != repair.inputs
    assert invoice.critical_fields == ["variance_reason", "gl_code"]
    assert repair.critical_fields == ["urgency", "trade"]


def test_new_task_type_needs_no_code_change(tmp_path: Path):
    for f in TASK_TYPES_DIR.glob("*.json"):
        shutil.copy(f, tmp_path)
    (tmp_path / "nda_review.json").write_text(
        json.dumps(
            {
                "name": "Incoming NDA",
                "trigger": "counterparty sends an NDA",
                "inputs": ["nda_text", "counterparty_record"],
                "decision": ["sign_standard", "mark_up", "send_to_lawyer"],
                "fields": {"deviation": {"type": "enum", "critical": True, "options": ["none", "term", "scope"]}},
                "text_outputs": ["reply"],
                "allowed_actions": ["draft_reply"],
                "alpha": 0.02,
                "min_cases": 150,
            }
        ),
        encoding="utf-8",
    )
    assert set(load_all(tmp_path)) == {"invoice_mismatch", "repair_request", "nda_review"}


def _write(tmp_path: Path, **overrides) -> Path:
    base = json.loads((TASK_TYPES_DIR / "invoice_mismatch.json").read_text(encoding="utf-8"))
    base.update(overrides)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "overrides",
    [
        {"decision": ["approve"]},  # needs at least two options
        {"decision": ["approve", "approve"]},  # unique
        {"alpha": 0},
        {"alpha": 0.6},
        {"min_cases": 0},
        {"allowed_actions": ["forward_to_all_staff"]},  # not a known action
        {"typo_key": 1},  # unknown keys fail loudly
        {"fields": {"x": {"type": "string", "options": ["a"]}}},  # options only on enums
    ],
)
def test_invalid_configs_are_rejected(tmp_path: Path, overrides: dict):
    with pytest.raises(TaskTypeConfigError):
        load_task_type(_write(tmp_path, **overrides))


def test_duplicate_names_rejected(tmp_path: Path):
    shutil.copy(TASK_TYPES_DIR / "invoice_mismatch.json", tmp_path / "a.json")
    shutil.copy(TASK_TYPES_DIR / "invoice_mismatch.json", tmp_path / "b.json")
    with pytest.raises(TaskTypeConfigError, match="duplicate name"):
        load_all(tmp_path)


def test_config_hash_is_stable_and_sensitive(tmp_path: Path):
    a = load_task_type(TASK_TYPES_DIR / "invoice_mismatch.json")
    b = load_task_type(TASK_TYPES_DIR / "invoice_mismatch.json")
    c = load_task_type(_write(tmp_path, alpha=0.05))
    assert a.config_hash() == b.config_hash() != c.config_hash()
