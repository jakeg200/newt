"""CSV and JSON imports: one row per item, optionally with the decision the mentor made.

A column map in the connection config says which column is which, so any export (a ledger, a
ticket system, a spreadsheet) works without code changes:

    {
      "item_ref": "invoice_id",            # required: stable id per row
      "received_at": "received",           # required: when the item arrived
      "inputs": {"invoice_text": "description", "po_record": "po"},
      "subject": "supplier_name",
      "decision": "outcome",               # optional: the mentor's decision
      "decision_map": {"Approved": "approve", "Queried": "query_supplier"},
      "acted_at": "decided_at",            # required when decision is mapped
      "fields": {"variance_reason": "reason", "gl_code": "gl"},
      "text_outputs": {"supplier_email": "email_sent"}
    }

Nested JSON values can be addressed with dots: "invoice.lines".
"""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.capture.types import Action, Batch, Item

_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y")


class ColumnMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_ref: str
    received_at: str
    inputs: dict[str, str] = Field(min_length=1)
    subject: str | None = None
    decision: str | None = None
    decision_map: dict[str, str] = Field(default_factory=dict)
    acted_at: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    text_outputs: dict[str, str] = Field(default_factory=dict)


def parse_time(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in _FORMATS:
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"unrecognised date {text[:30]!r}") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _get(row: dict[str, Any], path: str | None) -> Any:
    if not path:
        return None
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def read_rows(filename: str, data: bytes) -> list[dict[str, Any]]:
    if filename.lower().endswith(".json"):
        loaded = json.loads(data.decode("utf-8-sig"))
        rows = loaded.get("items", loaded) if isinstance(loaded, dict) else loaded
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise ValueError("JSON must be a list of objects (or {\"items\": [...]})")
        return rows
    if filename.lower().endswith(".csv"):
        return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    raise ValueError("use a .csv or .json file")


def rows_to_batch(rows: list[dict[str, Any]], columns: ColumnMap, decisions: list[str]) -> Batch:
    batch = Batch()
    for n, row in enumerate(rows, start=1):
        ref = _text(_get(row, columns.item_ref)).strip()
        if not ref:
            batch.errors.append(f"row {n}: no {columns.item_ref}")
            continue
        try:
            received = parse_time(_get(row, columns.received_at))
        except ValueError as exc:
            batch.errors.append(f"row {n}: {columns.received_at}: {exc}")
            continue
        batch.items.append(
            Item(
                source_ref=ref,
                received_at=received,
                inputs={name: _text(_get(row, col)) for name, col in columns.inputs.items()},
                subject=_text(_get(row, columns.subject)),
            )
        )

        raw_decision = _text(_get(row, columns.decision)).strip()
        if not raw_decision:
            continue
        decision = columns.decision_map.get(raw_decision, raw_decision)
        if decision not in decisions:
            batch.errors.append(f"row {n}: decision {raw_decision!r} isn't mapped to one of {decisions}")
            continue
        try:
            acted = parse_time(_get(row, columns.acted_at)) if columns.acted_at else None
        except ValueError as exc:
            batch.errors.append(f"row {n}: {columns.acted_at}: {exc}")
            continue
        if acted is None:
            batch.errors.append(f"row {n}: a decision needs an acted_at column")
            continue
        batch.actions.append(
            Action(
                source_ref=f"{ref}#decision",
                acted_at=acted,
                kind="decision",
                item_ref=ref,
                decision=decision,
                fields={name: _get(row, col) for name, col in columns.fields.items() if _get(row, col) not in (None, "")},
                text_outputs={name: _text(_get(row, col)) for name, col in columns.text_outputs.items() if _get(row, col)},
            )
        )
    return batch
