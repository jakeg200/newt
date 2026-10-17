"""A team whose history is clean enough to graduate on, an agent that follows the mentor's
patterns, and helpers to push live work through the REST connection."""

import random
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.agents import registry
from app.agents.output import PredictionResult
from app.models import User
from app.seed import seed
from app.worker import run_once

from tests.backtest_fixtures import COLUMNS, SUPPLIERS, ledger_csv, ledger_rows


def answer(item: dict) -> dict:
    """What the mentor does, by pattern (the history's rules)."""
    text = " ".join(str(v) for v in item["inputs"].values())
    if "units" in text:
        decision, reason = "query_supplier", "quantity"
    elif "purchase order" in text:
        decision, reason = "escalate", "missing_po"
    elif "approval limit" in text:
        decision, reason = "escalate", "other"
    elif "duplicate" in text:
        decision, reason = "query_supplier", "duplicate"
    else:
        decision, reason = "approve", "price"
    gl = next((code for name, code in SUPPLIERS if item.get("subject", "").startswith(name)), "6400")
    inv = (re.findall(r"INV-\d+", item.get("subject", "")) or ["INV-0"])[0]
    nums = re.findall(r"\d+", text)
    email = ""
    if reason == "quantity":
        email = f"Hello, invoice {inv} bills {nums[0]} units but we received {nums[1]}. Please send a credit note for the difference."
    elif reason == "duplicate":
        prev = re.search(r"INV-\d+", text).group(0)
        email = f"Hello, invoice {inv} looks like a duplicate of {prev}, which we've already paid. Please confirm or cancel it."
    return {"decision": decision, "fields": {"variance_reason": reason, "gl_code": gl}, "text_outputs": {"supplier_email": email}}


class PatternAgent:
    """Follows the mentor's patterns; `wrong_every` makes it a worse model for swap tests."""

    def __init__(self, model: str = "pattern-agent", wrong_every: int = 0) -> None:
        self.model, self.wrong_every, self.n = model, wrong_every, 0

    def predict(self, ctx) -> PredictionResult:
        self.n += 1
        item = ctx.payload()["item"]
        out = answer(item)
        if self.wrong_every and self.n % self.wrong_every == 0:
            out["decision"] = "approve" if out["decision"] != "approve" else "escalate"
        return PredictionResult({**out, "rationale": "pattern", "missing_info": [], "self_reported_confidence": 0.95},
                                0.95, self.model)


def setup_team(client, session, *, history: int = 400, noise: float = 0.0) -> dict:
    seed(session)
    mentor = session.scalar(select(User).where(User.email == "mentor+invoice_mismatch@synthetic.test"))
    manager = session.scalar(select(User).where(User.role == "manager"))
    h = {"X-Dev-User": mentor.id}
    tt = next(t for t in client.get("/task-types", headers=h).json() if t["team"] == "invoice_mismatch")
    csv_conn = client.post("/connections", json={"name": "Ledger", "provider": "csv", "task_type_id": tt["id"], "columns": COLUMNS}, headers=h).json()
    client.post(f"/connections/{csv_conn['id']}/import", files=[("files", ("l.csv", ledger_csv(ledger_rows(history, noise=noise))))], headers=h)
    rest = client.post("/connections", json={"name": "AP queue", "provider": "rest", "task_type_id": tt["id"]}, headers=h).json()
    registry.set_runner_override(lambda agent: PatternAgent())
    agent_id = next(a["id"] for a in client.get("/agents", headers=h).json() if a["kind"] == "built_in")
    return {"mentor": h, "manager": {"X-Dev-User": manager.id}, "tt": tt["id"], "rest": rest, "client": client, "agent_id": agent_id}


def backtest(ctx, session, limit: int = 300) -> dict:
    run = ctx["client"].post("/backtests", json={"task_type_id": ctx["tt"], "limit": limit}, headers=ctx["mentor"]).json()
    drain(session)
    return ctx["client"].get(f"/backtests/{run['id']}", headers=ctx["mentor"]).json()


def drain(session, limit: int = 50) -> None:
    for _ in range(limit):
        if not run_once(session):
            return


_counter = [0]


def live_items(n: int, *, start: datetime | None = None, seed_: int = 5, text: str | None = None,
               subject: str | None = None) -> list[dict]:
    """New supplier invoices arriving now, in the history's patterns (or with fixed text)."""
    rng = random.Random(seed_ + _counter[0])
    start = start or datetime.now(timezone.utc)
    rows = ledger_rows(n, seed=seed_ + 100 + _counter[0], noise=0.0)
    items = []
    for i, r in enumerate(rows):
        _counter[0] += 1
        ref = f"LIVE-{_counter[0]}"
        supplier = r["supplier"].split(" invoice ")[0]
        items.append({"ref": ref, "received_at": (start + timedelta(minutes=i)).isoformat(),
                      "subject": subject or f"{supplier} invoice INV-{90000 + _counter[0]}",
                      "inputs": {"invoice_text": text or r["description"],
                                 "po_record": f"PO-{80000 + _counter[0]}" if r["po"] else ""},
                      "sender": f"billing{rng.randint(1, 5)}@supplier.example"})
    return items


def push(ctx, body: dict) -> dict:
    token = ctx["rest"]["push_token"]
    resp = ctx["client"].post(f"/capture/push/{ctx['rest']['id']}", json=body, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def mentor_decides(ctx, items: list[dict], at: datetime | None = None) -> dict:
    """The mentor's real decisions on live items, as the source system reports them."""
    at = at or datetime.now(timezone.utc) + timedelta(hours=2)
    actions = []
    for it in items:
        a = answer(it)
        actions.append({"ref": f"{it['ref']}#done", "item_ref": it["ref"], "acted_at": at.isoformat(), "decision": a["decision"],
                        "fields": a["fields"], "text_outputs": {k: v for k, v in a["text_outputs"].items() if v}})
    return push(ctx, {"actions": actions})
