"""A team whose history is clean enough to graduate on, an agent that follows the mentor's
patterns, and helpers to push live work through the REST connection."""

from datetime import datetime

from sqlalchemy import select

from app.agents import registry
from app.agents.output import PredictionResult
from app.models import User
from app.seed import seed
from app.worker import run_once
from demo.ap_data import COLUMNS, ledger_csv, ledger_rows, mentor_actions, mentor_answer
from demo.ap_data import live_items as _live_items

answer = mentor_answer


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


def live_items(n: int, **kwargs) -> list[dict]:
    if "seed_" in kwargs:
        kwargs["seed"] = kwargs.pop("seed_")
    return _live_items(n, **kwargs)


def push(ctx, body: dict) -> dict:
    token = ctx["rest"]["push_token"]
    resp = ctx["client"].post(f"/capture/push/{ctx['rest']['id']}", json=body, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def mentor_decides(ctx, items: list[dict], at: datetime | None = None) -> dict:
    """The mentor's real decisions on live items, as the source system reports them."""
    return push(ctx, {"actions": mentor_actions(items, at)})
