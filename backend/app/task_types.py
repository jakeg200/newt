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


KPI_METRICS = ("completed_by_newt", "completed_total", "share_by_newt", "median_hours_to_complete", "backlog_open",
               "hours_returned", "value")


class KpiSpec(BaseModel):
    """A measure of how the role is going, with an optional weekly target. Metrics are generic; which ones matter
    for a role, and the targets, live here (and the manager can override targets)."""

    model_config = ConfigDict(extra="forbid")

    metric: Literal["completed_by_newt", "completed_total", "share_by_newt", "median_hours_to_complete", "backlog_open",
                    "hours_returned", "value"]
    target: float | None = None
    direction: Literal["up", "down"] = "up"
    label: str | None = Field(default=None, max_length=80)


TOOLS = ("search_past_cases", "get_case", "lookup_record", "check_rule", "calculate")


class LookupSpec(BaseModel):
    """An input that names a record in the firm's system (e.g. a purchase-order number), and what kind of record."""

    model_config = ConfigDict(extra="forbid")

    input: str
    kind: str = Field(pattern=r"^[a-z0-9_]{1,40}$")


class InsightDimension(BaseModel):
    """Something to group the work by when looking for what drives exceptions (e.g. the supplier), read from an
    input, the subject or the sender, optionally with a pattern whose first group is the value."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    source: str
    pattern: str | None = Field(default=None, max_length=200)


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
    follow_up_days: dict[str, int] = Field(default_factory=dict)  # decision -> days to wait before chasing
    kpis: list[KpiSpec] = Field(default_factory=list)
    # Doing the job, not just answering: the tools Newt may use, records it can look up, and the evidence a
    # decision needs before it counts (e.g. "look up the purchase order before approving").
    tools: list[Literal["search_past_cases", "get_case", "lookup_record", "check_rule", "calculate"]] = Field(default_factory=list)
    lookups: list[LookupSpec] = Field(default_factory=list)
    required_steps: dict[str, list[str]] = Field(default_factory=dict)
    insight_dimensions: list[InsightDimension] = Field(default_factory=list)

    @model_validator(mode="after")
    def _tools_are_consistent(self) -> "TaskTypeConfig":
        for spec in self.lookups:
            if spec.input not in self.inputs:
                raise ValueError(f"lookup input {spec.input!r} is not one of {self.inputs}")
        if self.lookups and "lookup_record" not in self.tools:
            raise ValueError("lookups need the lookup_record tool")
        for decision, steps in self.required_steps.items():
            if decision not in self.decision:
                raise ValueError(f"required_steps decision {decision!r} is not one of {self.decision}")
            if set(steps) - set(self.tools):
                raise ValueError(f"required_steps for {decision!r} use tools the role doesn't have")
        for dim in self.insight_dimensions:
            if dim.source not in self.inputs and dim.source not in ("sender", "subject"):
                raise ValueError(f"insight dimension source {dim.source!r} must be an input, 'sender' or 'subject'")
            if dim.pattern:
                import re

                try:
                    re.compile(dim.pattern)
                except re.error as exc:
                    raise ValueError(f"insight dimension pattern is invalid: {exc}") from exc
        return self

    @model_validator(mode="after")
    def _follow_ups_match_decisions(self) -> "TaskTypeConfig":
        for decision, days in self.follow_up_days.items():
            if decision not in self.decision:
                raise ValueError(f"follow_up_days decision {decision!r} is not one of {self.decision}")
            if not 1 <= days <= 60:
                raise ValueError("follow_up_days must be between 1 and 60")
        return self

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


class RoutineDefault(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[str]
    follow_up_days: int | None = Field(default=None, ge=1, le=60)


class RolePack(BaseModel):
    """A role Newt can be hired for: the task-type config plus what a firm needs to get going (description, default
    routines). Industry specifics live here, never in code. Cross-firm priors will hang off packs later (opt-in)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]{1,60}$")
    title: str = Field(min_length=1, max_length=80)
    tagline: str = Field(max_length=200)
    description: str = Field(max_length=1000)
    team: str = Field(pattern=r"^[a-z0-9_]{1,60}$")  # default team name
    task_type: str  # file in the task-types directory
    routines: dict[str, RoutineDefault] = Field(default_factory=dict)


def load_role_packs(roles_dir: Path, task_types_dir: Path) -> dict[str, tuple[RolePack, "TaskTypeConfig"]]:
    """Every pack, validated together with its task type (routines may only use the role's decisions and actions)."""
    out: dict[str, tuple[RolePack, TaskTypeConfig]] = {}
    if not roles_dir.exists():
        return out
    for path in sorted(roles_dir.glob("*.json")):
        pack = RolePack.model_validate(json.loads(path.read_text(encoding="utf-8")))
        config = load_task_type(task_types_dir / pack.task_type)
        for decision, r in pack.routines.items():
            if decision not in config.decision:
                raise ValueError(f"{path.name}: routine for unknown decision {decision!r}")
            if set(r.steps) - set(config.allowed_actions):
                raise ValueError(f"{path.name}: routine for {decision!r} uses actions the role isn't allowed")
        out[pack.id] = (pack, config)
    return out


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
