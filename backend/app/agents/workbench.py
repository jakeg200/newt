"""The workbench: the tools Newt uses to work a case like a person would, before deciding.

Every tool answers only from what existed before the item arrived (the same window as `ContextBuilder`), so the
time-travel guard holds for tool use too. Records in the firm's own systems are looked up live only for live work;
backtests and replays answer from recordings of earlier live lookups, or say "unavailable": a live system knows the
future, so it is never asked about the past.

Each call is recorded as a step (redacted input and output). The steps are the trajectory: stored, checked
(`eval/score.step_checks`) and replayable.
"""

import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.retrieval import Index, tokens
from app.capture.redact import Redactor
from app.task_types import TaskTypeConfig

MAX_TEXT = 600

TOOL_SPECS: dict[str, dict[str, Any]] = {
    "search_past_cases": {"description": "Find earlier decided cases like a description, with what the team decided.",
                          "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    "get_case": {"description": "Read one earlier case by its reference, with what the team decided.",
                 "input_schema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}},
    "lookup_record": {"description": "Look up a record in the firm's own system (e.g. a purchase order) by kind and reference.",
                      "input_schema": {"type": "object", "properties": {"kind": {"type": "string"}, "ref": {"type": "string"}}, "required": ["kind", "ref"]}},
    "check_rule": {"description": "Which of the team's rules and always-hand-back rules apply to a piece of text.",
                   "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    "calculate": {"description": "Arithmetic on numbers, e.g. '412.50 * 1.2 - 400'.",
                  "input_schema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}},
}

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_eval(expression: str) -> float:
    """Arithmetic only: numbers and + - * / % ** and brackets. Anything else is refused."""
    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            if isinstance(node.op, ast.Pow) and abs(ev(node.right)) > 6:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("only arithmetic is allowed")
    if len(expression) > 200:
        raise ValueError("expression too long")
    return round(ev(ast.parse(expression.replace(",", ""), mode="eval")), 6)


def _clip(text: Any) -> str:
    s = str(text or "")
    return s if len(s) <= MAX_TEXT else s[:MAX_TEXT] + "…"


@dataclass
class PastCase:
    case_id: str
    ref: str
    subject: str
    inputs: dict[str, Any]
    decision: str
    fields: dict[str, Any]


@dataclass
class Workbench:
    task: TaskTypeConfig
    case_id: str
    item_text: str
    past: list[PastCase]  # decided before the item arrived, and only those
    index: Index
    rules: list[dict[str, Any]]
    live: bool = False
    lookup: Callable[[str, str], dict[str, Any] | None] | None = None  # the firm's system, for live work only
    recorded: dict[str, Any] = field(default_factory=dict)  # "kind:ref" -> earlier live answer, for replay
    steps: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tools(self) -> list[str]:
        return list(self.task.tools)

    def specs(self) -> list[dict[str, Any]]:
        return [{"name": t, **TOOL_SPECS[t]} for t in self.tools]

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self.tools:
            out: dict[str, Any] = {"error": f"{name} isn't one of this role's tools"}
        else:
            try:
                out = getattr(self, f"_{name}")(**{k: v for k, v in args.items() if isinstance(k, str)})
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                out = {"error": str(exc)[:200]}
        self.steps.append({"n": len(self.steps) + 1, "tool": name, "input": {k: _clip(v) for k, v in args.items()},
                           "output": out})
        return out

    # The tools ---------------------------------------------------------------------------------

    def _search_past_cases(self, query: str, k: int = 5) -> dict[str, Any]:
        q = self.index._weigh(tokens(query))
        scored = []
        for p in self.past:
            vec = self.index.vec.get(p.case_id, {})
            score = sum(x * vec.get(w, 0.0) for w, x in q.items())
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda t: (-t[0], t[1].case_id))
        return {"cases": [{"ref": p.ref, "subject": p.subject, "decision": p.decision, "fields": p.fields,
                           "similarity": round(s, 3)} for s, p in scored[:max(1, min(int(k), 10))]]}

    def _get_case(self, ref: str) -> dict[str, Any]:
        p = next((p for p in self.past if p.ref == ref), None)
        if p is None:
            return {"found": False, "note": "no earlier decided case with that reference"}
        return {"found": True, "ref": p.ref, "subject": p.subject, "inputs": {k: _clip(v) for k, v in p.inputs.items()},
                "decision": p.decision, "fields": p.fields}

    def _lookup_record(self, kind: str, ref: str) -> dict[str, Any]:
        key = f"{kind}:{ref}"
        if key in self.recorded:
            return {"found": True, "record": self.recorded[key], "source": "recorded"}
        if self.live and self.lookup is not None:
            record = self.lookup(kind, ref)
            if record is None:
                return {"found": False, "source": "system", "note": "the system has no such record"}
            redact = Redactor()
            clean = {k: (redact(v) if isinstance(v, str) else v) for k, v in record.items()}
            return {"found": True, "record": clean, "source": "system"}
        return {"found": False, "source": "unavailable", "note": "the system can't be asked about the past; no recording"}

    def _check_rule(self, text: str) -> dict[str, Any]:
        from app.graduation.handback import hard_rule_hits
        from app.learning.rules import parse

        applies = []
        for r in self.rules:
            parsed = parse(r["text"], self.task)
            if parsed.decision and parsed.matches(text):
                applies.append({"rule": r["text"], "decision": parsed.decision})
        return {"rules": applies, "always_hand_back": hard_rule_hits(self.task.hard_rules, text)}

    def _calculate(self, expression: str) -> dict[str, Any]:
        return {"result": safe_eval(expression)}

    def recording(self) -> dict[str, Any]:
        """Live lookup answers, kept so the same work can be replayed later without the live system."""
        return {f"{s['input'].get('kind')}:{s['input'].get('ref')}": s["output"]["record"] for s in self.steps
                if s["tool"] == "lookup_record" and s["output"].get("found") and s["output"].get("source") == "system"}
