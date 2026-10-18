"""Task-type configs: everything industry-specific lives in these files, never in code."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Generic action verbs the actions module knows how to execute. A task type picks from these.
KNOWN_ACTIONS = frozenset({"draft_reply", "send_reply", "set_status", "set_field", "route"})


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["enum", "string", "text", "number", "boolean", "date"]
    critical: bool = False
    options: list[str] | None = None

    @model_validator(mode="after")
    def _options_match_type(self) -> "FieldSpec":
        if self.options is not None and self.type != "enum":
            raise ValueError("options are only allowed on enum fields")
        if self.options is not None and len(set(self.options)) != len(self.options):
            raise ValueError("enum options must be unique")
        return self


class CaptureRule(BaseModel):
    """How an observed mentor action translates into a decision, e.g. a reply to the sender
    means "query_supplier". Rules are checked in order; the first match wins."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["reply", "forward", "label", "status"]
    label: str | None = None  # for "label"
    status: str | None = None  # for "status"
    decision: str


class CaptureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_rules: list[CaptureRule] = Field(default_factory=list)
    reply_text_output: str | None = None  # which text output a mentor's reply fills


class BankQuestion(BaseModel):
    """A question Newt asks its mentor about this role, like a good first-week intern. The answer joins the
    orientation questionnaire, so it also feeds the handbook."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    question: str = Field(min_length=5, max_length=300)


class TaskTypeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    inputs: list[str] = Field(min_length=1)
    decision: list[str] = Field(min_length=2)
    fields: dict[str, FieldSpec] = Field(default_factory=dict)
    text_outputs: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    hard_rules: list[str] = Field(default_factory=list)
    alpha: float = Field(gt=0, lt=0.5)
    min_cases: int = Field(ge=1)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    question_bank: list[BankQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _capture_matches_task(self) -> "TaskTypeConfig":
        for rule in self.capture.decision_rules:
            if rule.decision not in self.decision:
                raise ValueError(f"capture rule decision {rule.decision!r} is not one of {self.decision}")
        out = self.capture.reply_text_output
        if out is not None and out not in self.text_outputs:
            raise ValueError(f"capture.reply_text_output {out!r} is not one of {self.text_outputs}")
        return self

    @field_validator("decision", "inputs")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("values must be unique")
        return v

    @field_validator("allowed_actions")
    @classmethod
    def _known_actions(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - KNOWN_ACTIONS)
        if unknown:
            raise ValueError(f"unknown actions {unknown}; allowed: {sorted(KNOWN_ACTIONS)}")
        return v

    @property
    def critical_fields(self) -> list[str]:
        return [name for name, spec in self.fields.items() if spec.critical]

    def config_hash(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()


class TaskTypeConfigError(ValueError):
    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path.name}: {message}")
        self.path = path


def load_task_type(path: Path) -> TaskTypeConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TaskTypeConfigError(path, f"invalid JSON ({exc})") from exc
    try:
        return TaskTypeConfig.model_validate(raw)
    except ValueError as exc:
        raise TaskTypeConfigError(path, str(exc)) from exc


def load_all(directory: Path) -> dict[str, TaskTypeConfig]:
    """Load every *.json config in a directory, keyed by file stem. Names must be unique."""
    configs: dict[str, TaskTypeConfig] = {}
    seen_names: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        config = load_task_type(path)
        if config.name in seen_names:
            raise TaskTypeConfigError(path, f"duplicate name {config.name!r} (also in {seen_names[config.name]})")
        seen_names[config.name] = path.name
        configs[path.stem] = config
    return configs
