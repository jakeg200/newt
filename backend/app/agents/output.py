"""The one output shape every agent returns, built-in or external, derived from the task config."""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.task_types import TaskTypeConfig


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision: str
    fields: dict[str, Any] = Field(default_factory=dict)
    text_outputs: dict[str, str] = Field(default_factory=dict)
    rationale: str = ""
    missing_info: list[str] = Field(default_factory=list)
    self_reported_confidence: float | None = None


@dataclass
class PredictionResult:
    output: dict[str, Any] | None
    confidence: float | None
    model: str
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    samples: list[str] = field(default_factory=list)  # decisions from self-consistency samples
    trajectory: list[dict[str, Any]] | None = None  # tool steps, when the agent worked the case with tools


def _field_schema(spec) -> dict[str, Any]:
    if spec.type == "enum":
        return {"type": "string", "enum": [*spec.options, "unknown"]} if spec.options else {"type": "string"}
    if spec.type == "number":
        return {"type": "number"}
    if spec.type == "boolean":
        return {"type": "boolean"}
    return {"type": "string"}


def output_schema(task: TaskTypeConfig) -> dict[str, Any]:
    """JSON schema for structured output: every property required, no extras."""

    def obj(props: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}

    return obj({
        "decision": {"type": "string", "enum": task.decision},
        "fields": obj({name: _field_schema(spec) for name, spec in task.fields.items()}),
        "text_outputs": obj({name: {"type": "string"} for name in task.text_outputs}),
        "rationale": {"type": "string"},
        "missing_info": {"type": "array", "items": {"type": "string"}},
        "self_reported_confidence": {"type": "number"},
    })


def validate_output(raw: Any, task: TaskTypeConfig) -> AgentOutput:
    """Check an agent's answer against the task. Raises ValueError with a short reason."""
    try:
        out = AgentOutput.model_validate(raw)
    except ValidationError as exc:
        err = exc.errors()[0]
        raise ValueError(f"output {'.'.join(str(x) for x in err['loc'])}: {err['msg']}") from exc
    if out.decision not in task.decision:
        raise ValueError(f"decision {out.decision!r} is not one of {task.decision}")
    for name, value in out.fields.items():
        spec = task.fields.get(name)
        if spec and spec.type == "enum" and spec.options and value not in [*spec.options, "unknown", None]:
            raise ValueError(f"field {name} = {value!r} is not one of {spec.options}")
    out.fields = {k: v for k, v in out.fields.items() if k in task.fields and v not in (None, "unknown", "")}
    out.text_outputs = {k: v for k, v in out.text_outputs.items() if k in task.text_outputs and v}
    if out.self_reported_confidence is not None:
        out.self_reported_confidence = min(1.0, max(0.0, float(out.self_reported_confidence)))
    return out
