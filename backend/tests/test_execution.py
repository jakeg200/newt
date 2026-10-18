"""Doing the work: actions carried out in the firm's systems (signed, policy re-checked, confirmed), failures handed
back, follow-ups, routines, outcome KPIs, and Newt's career ladder."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.agents import registry
from app.agents.context import utc
from app.agents.external import sign
from app.colleague import career
from app.execution import executor, routines
from app.execution import service as execution
from app.models import ActionLog, Apprenticeship, Case, Job, Message, Prediction, TaskType, User
from app.outcomes import kpis

from tests.graduation_fixtures import drain, live_items, push, setup_team

ALWAYS_ON = {"start": "00:00", "end": "23:59", "workdays": [0, 1, 2, 3, 4, 5, 6]}


class FakeSystem:
    """The firm's system on the other end of the webhook."""

    def __init__(self, answer=lambda req: httpx.Response(200, json={"status": "done", "ref": "SYS-1"})) -> None:
        self.answer, self.requests = answer, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.answer(request)


@pytest.fixture
def team(client, session):
    ctx = setup_team(client, session)
    client.patch("/me/preferences", json=ALWAYS_ON, headers=ctx["mentor"])
    yield ctx
    registry.set_runner_override(None)
    executor.set_http(None)


def connect(ctx, system: FakeSystem, actions=("set_status", "draft_reply")) -> dict:
    executor.set_http(httpx.Client(transport=httpx.MockTransport(system)))
    r = ctx["client"].post("/destinations", json={"task_type_id": ctx["tt"], "name": "AP system", "url": "https://hooks.example.com/newt",
                                                  "actions": list(actions)}, headers=ctx["mentor"])
    assert r.status_code == 201, r.text
    return r.json()


def stage(session, ctx, status: str) -> TaskType:
    tt = session.get(TaskType, ctx["tt"])
    tt.status, tt.tau, tt.calibration = status, 0.2, {}
    session.commit()
    return tt


def first_draft(ctx) -> dict:
    return ctx["client"].get(f"/supervised?task_type_id={ctx['tt']}", headers=ctx["mentor"]).json()[0]


# Destinations -------------------------------------------------------------------------------------

def test_destinations_refuse_private_addresses_and_sign_requests(team, client, session):
    bad = client.post("/destinations", json={"task_type_id": team["tt"], "name": "x", "url": "https://10.0.0.5/hook", "actions": ["set_status"]},
                      headers=team["mentor"])
    assert bad.status_code == 400
    nope = client.post("/destinations", json={"task_type_id": team["tt"], "name": "x", "url": "https://h.example.com", "actions": ["send_reply"]},
                       headers=team["mentor"])
    assert nope.status_code == 400  # not an allowed action for this role
    system = FakeSystem()
    d = connect(team, system)
    assert d["secret"].startswith("newt_") and "secret" not in client.get(f"/destinations?task_type_id={team['tt']}", headers=team["mentor"]).json()[0]
    assert client.post(f"/destinations/{d['id']}/test", headers=team["mentor"]).json()["ok"] is True
    req = system.requests[-1]
    assert req.headers[executor.SIGNATURE_HEADER] == sign(d["secret"], req.content)


# Doing the work -----------------------------------------------------------------------------------

def test_approved_work_is_carried_out_and_completed(team, client, session):
    system = FakeSystem()
    connect(team, system)
    stage(session, team, "supervised")
    push(team, {"items": live_items(6)})
    drain(session)
    assert not system.requests  # nothing runs before the mentor approves
    d = first_draft(team)
    client.post(f"/supervised/{d['prediction_id']}/approve", json={}, headers=team["mentor"])
    drain(session)
    rows = session.scalars(select(ActionLog).where(ActionLog.prediction_id == d["prediction_id"])).all()
    assert rows and all(r.exec_status == "done" and r.external_ref == "SYS-1" for r in rows)
    sent = [json.loads(r.content) for r in system.requests]
    assert {s["item_ref"] for s in sent} == {session.get(Case, d["case"]["id"]).source_ref}  # refers to the item, not a person
    assert all("@" not in json.dumps(s) for s in sent)
    assert session.get(Case, d["case"]["id"]).completed_at is not None


def test_shadow_never_acts_and_autonomous_is_simulated_without_a_system(team, client, session):
    push(team, {"items": live_items(4)})
    drain(session)
    assert not session.scalars(select(ActionLog).where(ActionLog.exec_status.is_not(None))).all()
    stage(session, team, "autonomous")
    push(team, {"items": live_items(6)})
    drain(session)
    done = session.scalars(select(ActionLog).where(ActionLog.exec_status == "done")).all()
    assert done and all(r.result.get("simulated") for r in done)
    o = client.get(f"/task-types/{team['tt']}/outcomes", headers=team["manager"]).json()
    assert o["simulated"] is True and o["weeks"][-1]["completed_by_newt"] > 0


def test_accepted_work_completes_only_on_a_signed_confirmation(team, client, session):
    system = FakeSystem(lambda req: httpx.Response(202, json={"status": "accepted"}))
    d = connect(team, system)
    stage(session, team, "supervised")
    push(team, {"items": live_items(4)})
    drain(session)
    draft = first_draft(team)
    client.post(f"/supervised/{draft['prediction_id']}/approve", json={}, headers=team["mentor"])
    drain(session)
    row = session.scalars(select(ActionLog).where(ActionLog.prediction_id == draft["prediction_id"])).first()
    assert row.exec_status == "running" and session.get(Case, row.case_id).completed_at is None
    body = json.dumps({"status": "done", "ref": "PAID-9"}).encode()
    forged = client.post(f"/execution/callback/{row.id}", content=body, headers={executor.SIGNATURE_HEADER: "sha256=nope"})
    assert forged.status_code == 401
    for r in session.scalars(select(ActionLog).where(ActionLog.prediction_id == draft["prediction_id"])):
        ok = client.post(f"/execution/callback/{r.id}", content=body, headers={executor.SIGNATURE_HEADER: sign(d["secret"], body)})
        assert ok.status_code == 200
    session.expire_all()
    assert session.get(Case, row.case_id).completed_at is not None


def test_failures_retry_then_come_back_with_the_reason(team, client, session, monkeypatch):
    monkeypatch.setattr(execution, "BACKOFF_S", 0)
    connect(team, FakeSystem(lambda req: httpx.Response(500)))
    stage(session, team, "supervised")
    push(team, {"items": live_items(4)})
    drain(session)
    d = first_draft(team)
    client.post(f"/supervised/{d['prediction_id']}/approve", json={}, headers=team["mentor"])
    drain(session)
    row = session.scalars(select(ActionLog).where(ActionLog.prediction_id == d["prediction_id"])).first()
    assert row.exec_status == "failed" and row.attempts == execution.MAX_ATTEMPTS
    case = session.get(Case, row.case_id)
    assert case.status == "open" and case.completed_at is None
    assert session.get(Prediction, d["prediction_id"]).output["hand_back"]["hand_back"]
    msgs = client.get(f"/messages?task_type_id={team['tt']}", headers=team["mentor"]).json()["messages"]
    failed = next(m for m in msgs if m["kind"] == "handback" and m["payload"].get("retry"))
    assert "HTTP 500" in failed["body"]
    about_it = [m for m in msgs if m["kind"] == "handback" and (m["payload"].get("case") or {}).get("id") == case.id]
    assert len(about_it) == 1  # one message about the failure, not a second generic hand-back
    executor.set_http(httpx.Client(transport=httpx.MockTransport(FakeSystem())))
    assert client.post(f"/messages/{failed['id']}/reply", json={"action": "retry"}, headers=team["mentor"]).status_code == 200
    drain(session)
    session.expire_all()
    assert all(r.exec_status == "done" for r in session.scalars(select(ActionLog).where(ActionLog.case_id == case.id)))
    assert session.get(Case, case.id).completed_at is not None


def test_the_policy_is_checked_again_when_acting(team, session):
    system = FakeSystem()
    connect(team, system)
    stage(session, team, "autonomous")
    push(team, {"items": live_items(2)})
    drain(session)
    case = session.scalars(select(Case).where(Case.task_type_id == team["tt"], Case.is_backtest.is_(False))).first()
    row = ActionLog(case_id=case.id, mode="autonomous", action="draft_reply", status="executed", exec_status="queued", policy_check={},
                    payload={"to": [(case.snapshot or {}).get("from")], "body": "Pay at https://evil.example/now", "output": "supplier_email"})
    session.add(row)
    session.commit()
    before = len(system.requests)
    assert execution.run(session, row.id) == "failed"
    assert len(system.requests) == before  # never reached the system


def test_follow_ups_ask_until_newt_has_earned_chasing(team, client, session):
    stage(session, team, "supervised")
    items = [i for i in live_items(30) if "units" in i["inputs"]["invoice_text"]][:2]  # quantity queries: query_supplier
    push(team, {"items": items})
    drain(session)
    drafts = [d for d in client.get(f"/supervised?task_type_id={team['tt']}", headers=team["mentor"]).json() if d["agent"]["decision"] == "query_supplier"]
    assert drafts
    client.post(f"/supervised/{drafts[0]['prediction_id']}/approve", json={}, headers=team["mentor"])
    drain(session)
    case = session.get(Case, drafts[0]["case"]["id"])
    job = session.scalars(select(Job).where(Job.type == "follow_up")).first()
    assert job is not None and utc(job.run_at) > datetime.now(timezone.utc) + timedelta(days=2)  # waits 3 days
    assert execution.follow_up(session, case.id, job.payload["since"]) == "asked"
    assert session.scalar(select(Message).where(Message.kind == "followup"))
    tt = session.get(TaskType, team["tt"])
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    app_.settings = {**app_.settings, "responsibilities": {tt.id: {"follow_ups": {"granted_by": "x"}}}}
    session.commit()
    assert execution.follow_up(session, case.id, job.payload["since"]) == "chased"  # now its own responsibility
    chase = session.scalars(select(ActionLog).where(ActionLog.case_id == case.id, ActionLog.prediction_id.is_(None))).all()
    assert chase and chase[-1].payload.get("follow_up") and "following up" in chase[-1].payload["body"]


def test_routines_are_proposed_from_history_and_enforced(team, client, session):
    r = client.get(f"/task-types/{team['tt']}/routines", headers=team["mentor"]).json()
    assert "draft_reply" in r["query_supplier"]["steps"] and "draft_reply" not in r["approve"]["steps"]
    assert r["query_supplier"]["follow_up_days"] == 3
    assert client.put(f"/task-types/{team['tt']}/routines/query_supplier", json={"steps": ["send_reply"]}, headers=team["mentor"]).status_code == 400
    ok = client.put(f"/task-types/{team['tt']}/routines/query_supplier", json={"steps": ["set_status"], "follow_up_days": None}, headers=team["mentor"])
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert routines.steps_for(session, session.get(TaskType, team["tt"]), "query_supplier") == {"set_status"}
    stage(session, team, "supervised")
    push(team, {"items": [i for i in live_items(30) if "units" in i["inputs"]["invoice_text"]][:2]})
    drain(session)
    drafts = [d for d in client.get(f"/supervised?task_type_id={team['tt']}", headers=team["mentor"]).json() if d["agent"]["decision"] == "query_supplier"]
    assert drafts and all({a["action"] for a in d["actions"]} == {"set_status"} for d in drafts)


# Outcomes -----------------------------------------------------------------------------------------

def test_kpi_maths():
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    w = kpis.week_windows(now, 3)
    assert len(w) == 3 and w[-1][1] == now and w[0][0] == now - timedelta(days=21)
    assert kpis.median([1, 3, 10]) == 3 and kpis.median([]) is None
    assert kpis.on_track(0.6, 0.5, "up") and not kpis.on_track(30, 24, "down") and kpis.on_track(1, None, "up") is None
    assert kpis.trend(5, 3) == 2 and kpis.trend(None, 3) is None
    week = kpis._week([(now - timedelta(hours=10), now - timedelta(hours=4))], [now - timedelta(hours=1)], now - timedelta(days=7), now, 6, 45)
    assert week["completed_by_newt"] == 1 and week["completed_total"] == 2 and week["share_by_newt"] == 0.5
    assert week["median_hours_to_complete"] == 6 and week["hours_returned"] == 0.1 and week["value"] == 4.5


def test_manager_sets_kpi_targets(team, client):
    assert client.put(f"/task-types/{team['tt']}/kpi-targets", json={"share_by_newt": 0.8}, headers=team["mentor"]).status_code == 403
    assert client.put(f"/task-types/{team['tt']}/kpi-targets", json={"nonsense": 1}, headers=team["manager"]).status_code == 400
    client.put(f"/task-types/{team['tt']}/kpi-targets", json={"share_by_newt": 0.8}, headers=team["manager"])
    share = next(k for k in client.get(f"/task-types/{team['tt']}/outcomes", headers=team["manager"]).json()["kpis"] if k["metric"] == "share_by_newt")
    assert share["target"] == 0.8


# Career -------------------------------------------------------------------------------------------

def test_career_ladder_and_earned_responsibility(team, client, session):
    tt = session.get(TaskType, team["tt"])
    assert career.rank(session, tt) in ("new_starter", "intern")
    stage(session, team, "supervised")
    assert career.rank(session, tt) == "junior"
    stage(session, team, "autonomous")
    assert career.rank(session, tt) == "graduate"
    manager = session.scalar(select(User).where(User.role == "manager"))
    mentor = session.scalar(select(User).where(User.email == "mentor+invoice_mismatch@synthetic.test"))
    with pytest.raises(PermissionError):
        career.grant(session, mentor, tt, "follow_ups")
    with pytest.raises(career.CareerError):
        career.grant(session, manager, tt, "follow_ups")  # not earned yet: no clean run of spot checks
    assert client.get(f"/task-types/{team['tt']}/career", headers=team["manager"]).json()["title"] == "Graduate"
