"""The whole onboarding programme, end to end, through the HTTP API only.

Provisioning (an org, two people, a team) is the one step done directly, as an administrator
would. Everything after that goes through the same API the web app uses: no database edits.

Orientation → capture → backtest → teaching → rules → live shadowing → graduation (mentor) →
supervised practice → autonomy (manager) → autonomous work with blind audits → manager dashboard →
track record → model swap re-certified on the frozen record.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import admin
from app.config import REPO_DIR, get_settings
from app.models import Org, User
from app.task_types import load_task_type
from demo.ap_data import COLUMNS, ledger_csv, ledger_rows, live_items, mentor_actions, mentor_answer

ORG = "Demo Co"
TEAM = "accounts_payable"
MENTOR_EMAIL, MANAGER_EMAIL = "sarah.k@demo.test", "morgan@demo.test"
SAMPLES = REPO_DIR / "samples" / "accounts_payable"


@dataclass
class People:
    mentor: dict[str, str]
    manager: dict[str, str]


def provision(session: Session) -> People:
    """Create the synthetic demo org, or reuse it if it's already there (with nothing run yet)."""
    org = session.scalar(select(Org).where(Org.name == ORG))
    if org is None:
        admin.create_org(session, ORG)
        org = session.scalar(select(Org).where(Org.name == ORG))
        org.is_synthetic = True  # demo data must never pass for evidence about a real team
        session.commit()
        admin.add_user(session, ORG, MENTOR_EMAIL, "Sarah K (demo mentor)", "mentor")
        admin.add_user(session, ORG, MANAGER_EMAIL, "Morgan (demo manager)", "manager")
        admin.add_team(session, ORG, TEAM, MENTOR_EMAIL, load_task_type(get_settings().task_types_dir / "invoice_mismatch.json"))
    mentor = session.scalar(select(User).where(User.email == MENTOR_EMAIL))
    manager = session.scalar(select(User).where(User.email == MANAGER_EMAIL))
    return People({"X-Dev-User": mentor.id}, {"X-Dev-User": manager.id})


class StepError(RuntimeError):
    pass


def _ok(resp, step: str) -> Any:
    if resp.status_code >= 400:
        raise StepError(f"{step}: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.content and resp.headers.get("content-type", "").startswith("application/json") else None


STOPS = ("approve-handbook", "graduate", "autonomy", "swap")


def run(http, drain: Callable[[], None], people: People, *, log: Callable[[str], None] = print,
        history: int = 420, noise: float = 0.0, stop_before: str | None = None) -> dict[str, Any]:
    """`stop_before` (one of STOPS) leaves that step for a person to do on screen, e.g. for a demo video."""
    m, mg = people.mentor, people.manager
    out: dict[str, Any] = {}

    def pause(step: str) -> bool:
        if stop_before == step:
            out["stopped"] = f"paused before '{step}' for you to do it in the app"
            log(f"   {out['stopped']}")
            return True
        return False
    tt = next(t for t in _ok(http.get("/task-types", headers=m), "task types") if t["team"] == TEAM)
    tid = tt["id"]
    if tt["status"] != "shadow" or _ok(http.get(f"/orientation/sources?team={TEAM}", headers=m), "sources"):
        raise StepError(f"{ORG} has already been through the programme; start from a fresh database to run it again")

    log("1. Orientation: the team's documents become the agent's handbook")
    files = [("files", (p.name, p.read_bytes())) for p in sorted(Path(SAMPLES).iterdir()) if p.is_file()]
    _ok(http.post("/orientation/sources", data={"team": TEAM}, files=files, headers=m), "upload documents")
    _ok(http.put(f"/orientation/questionnaire?team={TEAM}", json={"answers": {
        "purpose": "We check supplier invoices against purchase orders and pay them.",
        "first_check": "The PO number, then whether the amount is over my £5,000 limit.",
        "always_escalate": "Anything over £5,000, and any bank detail change.",
    }}, headers=m), "questionnaire")
    handbook = _ok(http.post("/orientation/handbook/draft", json={"team": TEAM}, headers=m), "draft handbook")
    if pause("approve-handbook"):
        return out
    approved = _ok(http.post(f"/orientation/handbook/{handbook['id']}/approve", headers=mg), "approve handbook")
    out["handbook_version"] = approved["version"]

    log("2. Capture: a year of decided history, and a live queue")
    conn = _ok(http.post("/connections", json={"name": "AP ledger", "provider": "csv", "task_type_id": tid, "columns": COLUMNS},
                         headers=m), "csv connection")
    run_ = _ok(http.post(f"/connections/{conn['id']}/import", files=[("files", ("ledger.csv", ledger_csv(ledger_rows(history, noise=noise))))],
                         headers=m), "import history")
    out["history_cases"] = run_["stats"]["cases_created"]
    rest = _ok(http.post("/connections", json={"name": "AP queue", "provider": "rest", "task_type_id": tid}, headers=m), "rest connection")
    auth = {"Authorization": f"Bearer {rest['push_token']}"}

    def push(body: dict) -> None:
        _ok(http.post(f"/capture/push/{rest['id']}", json=body, headers=auth), "push")

    log("3. Backtest: replay 300 decided cases")
    bt = _ok(http.post("/backtests", json={"task_type_id": tid, "limit": 300}, headers=m), "start backtest")
    drain()
    bt = _ok(http.get(f"/backtests/{bt['id']}", headers=m), "backtest result")
    if bt["status"] != "done":
        raise StepError(f"backtest {bt['status']}: {bt['error']}")
    out["backtest_agreement"] = bt["stats"]["agreement_rate"]

    log("4. Teaching: one tap per disagreement")
    queue = _ok(http.get(f"/teaching/queue?task_type_id={tid}&limit=10", headers=m), "queue")
    for card in queue["cards"]:
        same = card["mentor"]["decision"] == card["agent"]["decision"]
        _ok(http.post("/lessons", json={"prediction_id": card["prediction_id"], "attribution": "both_fine" if same else "intern_wrong"},
                      headers=m), "lesson")
    out["lessons"] = len(queue["cards"])

    log("5. Rules: accept what the intern learned")
    proposed = _ok(http.post("/rules/infer", json={"task_type_id": tid}, headers=m), "infer rules")
    for rule in sorted(proposed, key=lambda r: -(r["stats"].get("support") or 0))[:2]:
        _ok(http.patch(f"/rules/{rule['id']}", json={"status": "active"}, headers=m), "accept rule")
    drain()
    out["rules_active"] = min(2, len(proposed))

    log("6. Live shadowing: sealed predictions on new work, revealed when the mentor acts")
    items = live_items(60)
    push({"items": items})
    drain()
    push({"actions": mentor_actions(items)})
    drain()

    log("7. Graduation: the mentor signs supervised practice")
    ev = _ok(http.get(f"/task-types/{tid}/evaluation", headers=m), "evaluation")
    out["evaluation"] = {k: ev[k] for k in ("n_above", "errors_above", "ucb", "coverage", "live_above", "eligible")}
    if not ev["eligible"]:
        out["stopped"] = "not eligible: " + "; ".join(c["detail"] for c in ev["checks"] if not c["ok"])
        log(f"   stopped: {out['stopped']}")
        return out
    if pause("graduate"):
        return out
    _ok(http.post(f"/task-types/{tid}/graduate", json={"to": "supervised"}, headers=m), "graduate to supervised")

    log("8. Supervised practice: the intern drafts, the mentor approves in one tap")
    approved_n = 0
    while approved_n < 55:
        items = live_items(40)
        push({"items": items})
        drain()
        for d in _ok(http.get(f"/supervised?task_type_id={tid}", headers=m), "drafts"):
            right = mentor_answer({"subject": d["case"]["subject"], "inputs": d["case"]["inputs"]})
            if d["agent"]["decision"] == right["decision"]:
                _ok(http.post(f"/supervised/{d['prediction_id']}/approve", json={}, headers=m), "approve")
            else:
                _ok(http.post(f"/supervised/{d['prediction_id']}/reject", json={"decision": right["decision"]}, headers=m), "reject")
            approved_n += 1
        push({"actions": mentor_actions([i for i in items if "approval limit" in i["inputs"]["invoice_text"]])})  # hand-backs, done by hand
        drain()
    out["supervised_cases"] = approved_n

    log("9. Autonomy: the manager signs")
    if pause("autonomy"):
        return out
    _ok(http.post(f"/task-types/{tid}/graduate", json={"to": "autonomous"}, headers=mg), "graduate to autonomous")

    log("10. Autonomous work, with blind audits")
    push({"items": live_items(40)})
    drain()
    audits = _ok(http.get(f"/audits?task_type_id={tid}", headers=m), "audits")
    results = []
    for a in audits:
        right = mentor_answer({"subject": a["case"]["subject"], "inputs": a["case"]["inputs"]})
        results.append(_ok(http.post(f"/audits/{a['audit_id']}", json={"decision": right["decision"], "fields": right["fields"]},
                                     headers=m), "audit")["result"])
    digest = _ok(http.get(f"/autonomy/digest?task_type_id={tid}", headers=mg), "digest")
    out["autonomous"] = {"cases_handled": digest["cases_handled"], "actions_blocked": digest["actions_blocked"],
                         "audits": {"passed": results.count("pass"), "failed": results.count("fail")}}

    log("11. Manager dashboard and track record")
    _ok(http.patch(f"/manager/settings/{TEAM}", json={"minutes_per_case": 6, "hourly_cost": 45, "currency": "GBP", "usd_rate": 0.79},
                   headers=mg), "manager settings")
    dash = next(t for t in _ok(http.get("/manager/dashboard", headers=mg), "dashboard")["teams"] if t["team"] == TEAM)
    out["dashboard"] = {k: dash[k] for k in ("cases_handled", "hours_returned", "value_of_hours", "running_cost", "net")}
    record = _ok(http.get(f"/task-types/{tid}/track-record", headers=mg), "track record")
    out["track_record"] = {k: record[k] for k in ("status", "error_upper_bound_95", "coverage", "audits", "signoffs")}

    log("12. Model swap: re-certified on the frozen record")
    if pause("swap"):
        return out
    agent_id = next(a["id"] for a in _ok(http.get("/agents", headers=mg), "agents") if a["kind"] == "built_in")
    swap = _ok(http.post(f"/agents/{agent_id}/swap", json={"model": "claude-opus-5-5", "version": "2"}, headers=mg), "swap")
    drain()
    result = {}
    for run_id in swap["reprobation_runs"]:
        result = _ok(http.get(f"/backtests/{run_id}", headers=mg), "re-probation")["stats"].get("reprobation", {})
    out["model_swap"] = {"runs": len(swap["reprobation_runs"]), "recertified": result.get("passed"),
                         "duration_s": result.get("duration_s"), "result": result,
                         "status": _ok(http.get(f"/task-types/{tid}/track-record", headers=mg), "track record")["status"]}
    log("Done.")
    return out
