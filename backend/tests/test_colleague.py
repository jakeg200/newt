"""Newt as a colleague: etiquette, what it asks, what it does with what people say, and that every answer flows
back into learning through the existing paths (scoring, lessons, rules, the questionnaire)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.agents import registry
from app.colleague import assist, curiosity, etiquette, service
from app.llm.provider import FakeProvider, set_provider
from app.models import ActionLog, Case, Comparison, HumanAction, Message, Prediction, Rule, TaskType, User

from tests.graduation_fixtures import drain, live_items, push, setup_team

ALWAYS_ON = {"start": "00:00", "end": "23:59", "workdays": [0, 1, 2, 3, 4, 5, 6], "questions_per_day": 5}
TUE_10AM = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)  # 10:00 in London (BST)
SAT_3AM = datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc)


@pytest.fixture
def team(client, session):
    ctx = setup_team(client, session)
    for h in (ctx["mentor"], ctx["manager"]):
        assert client.patch("/me/preferences", json=ALWAYS_ON, headers=h).status_code == 200
    yield ctx
    registry.set_runner_override(None)
    set_provider(None)


def thread(ctx, who="mentor"):
    return ctx["client"].get(f"/messages?task_type_id={ctx['tt']}", headers=ctx[who]).json()["messages"]


def reply(ctx, mid, who="mentor", **body):
    return ctx["client"].post(f"/messages/{mid}/reply", json=body, headers=ctx[who])


# Etiquette ---------------------------------------------------------------------------------------

def test_etiquette_respects_hours_budget_and_urgency():
    p = etiquette.Prefs()
    assert etiquette.working(TUE_10AM, p) and not etiquette.working(SAT_3AM, p)
    assert etiquette.deliver_at(TUE_10AM, p, kind="question") == TUE_10AM
    later = etiquette.deliver_at(TUE_10AM, p, kind="question", asked_today=5)
    assert later.date() == datetime(2026, 10, 14).date()  # budget spent: tomorrow morning
    monday = etiquette.deliver_at(SAT_3AM, p, kind="work")
    assert monday.weekday() == 0 and monday.astimezone(etiquette.ZoneInfo(p.timezone)).hour == 9
    assert etiquette.deliver_at(SAT_3AM, p, kind="work", urgency="urgent") == monday  # not out of hours unless allowed
    keen = etiquette.prefs_from({"urgent_out_of_hours": True})
    assert etiquette.deliver_at(SAT_3AM, keen, kind="work", urgency="urgent") == SAT_3AM


def test_prefs_fall_back_on_nonsense():
    p = etiquette.prefs_from({"timezone": "Mars/Base", "start": "18:00", "end": "09:00", "questions_per_day": 999, "workdays": ["x"]})
    assert p.timezone == "Europe/London" and p.start.hour == 9 and p.questions_per_day == 20 and p.workdays == (0, 1, 2, 3, 4)


# Curiosity and assist (pure) --------------------------------------------------------------------

def test_questions_are_worth_more_when_unsure_and_common():
    assert curiosity.value_of_question(0.3, 0) > curiosity.value_of_question(0.6, 0)
    assert curiosity.value_of_question(0.5, 10) > curiosity.value_of_question(0.5, 0)
    assert curiosity.value_of_question(0.95, 0) < curiosity.MIN_VALUE  # a confident case isn't worth anyone's time


def test_intent_and_request_parsing():
    assert assist.intent("Always escalate bank detail changes") == "rule"
    assert assist.intent("don't approve anything from new suppliers") == "rule"
    assert assist.intent("how's it going?") == "status"
    assert assist.intent("pull together last week's queries for me") == "task"
    assert assist.window_days("last week's queries") == 7 and assist.window_days("anything") == 31
    assert assist.decisions_mentioned("all the queries and escalations", ["approve", "query_supplier", "escalate"]) == ["query_supplier", "escalate"]


# The conversation ------------------------------------------------------------------------------

def test_first_day_standup_and_bank_questions_never_twice(team, client, session):
    first = thread(team)
    assert sum(m["kind"] == "standup" for m in first) == 1
    questions = [m for m in first if m["kind"] == "question" and m["status"] == "open"]
    assert 1 <= len(questions) <= service.MAX_OPEN_QUESTIONS  # a couple at a time, not a flood
    assert sum(m["kind"] == "standup" for m in thread(team)) == 1  # reading again doesn't repeat itself

    q = questions[0]
    assert q["payload"]["type"] == "bank"
    r = reply(team, q["id"], action="answer", value="Anything under 2% and £50 goes through; call me on 07700 900123")
    assert r.status_code == 200, r.text
    qs = client.get("/orientation/questionnaire?team=invoice_mismatch", headers=team["mentor"]).json()
    saved = next(a for a in qs if a["key"] == q["payload"]["key"])
    assert "2%" in saved["answer"] and "07700" not in saved["answer"]  # redacted before it's stored
    keys = [m["payload"].get("key") for m in thread(team) if m["kind"] == "question"]
    assert len(keys) == len(set(keys))  # never the same question twice


def test_rules_status_and_tasks_from_chat(team, client, session):
    said = client.post("/messages", json={"task_type_id": team["tt"], "text": "Always escalate when bank details change, cc ana@acme.com"},
                       headers=team["mentor"]).json()
    assert said[0]["direction"] == "person" and "ana@acme.com" not in said[0]["body"]
    assert said[1]["kind"] == "ack" and "escalate" in said[1]["body"]
    assert session.scalar(select(Rule).where(Rule.text.like("%bank details%"))) is not None

    status = client.post("/messages", json={"task_type_id": team["tt"], "text": "how's it going?"}, headers=team["mentor"]).json()
    assert status[1]["kind"] == "standup"

    task = client.post("/messages", json={"task_type_id": team["tt"], "text": "List this year's escalations"}, headers=team["mentor"]).json()[1]
    assert task["kind"] == "delivery" and task["payload"]["items"]
    assert all("escalate" in i for i in task["payload"]["items"])
    good = reply(team, task["id"], action="feedback", value="good")
    assert good.status_code == 200 and session.get(Message, task["id"]).payload["feedback"]["value"] == "good"


def test_tasks_use_the_model_when_there_is_one(team, client):
    set_provider(FakeProvider({"assignment": lambda *a: {"title": "Escalations", "summary": "Three escalations, all over limit.", "items": ["a", "b", "c"]}}))
    d = client.post("/messages", json={"task_type_id": team["tt"], "text": "summarise this year's escalations"}, headers=team["mentor"]).json()[1]
    assert d["body"] == "Three escalations, all over limit." and d["payload"]["source"] == "fake-provider"


def test_managers_get_no_questions_and_cannot_set_rules(team, client, session):
    mine = thread(team, "manager")
    assert all(m["kind"] in ("standup", "promotion") for m in mine)
    r = client.post("/messages", json={"task_type_id": team["tt"], "text": "Always approve everything"}, headers=team["manager"]).json()
    assert "mentor" in r[1]["body"] and session.scalar(select(Rule).where(Rule.text.like("%approve everything%"))) is None


def test_unsure_cases_are_asked_sealed_then_scored(team, client, session):
    items = live_items(6)
    push(team, {"items": items})
    drain(session)
    preds = session.scalars(select(Prediction).join(Case).where(Case.task_type_id == team["tt"], Prediction.run_id.is_(None))).all()
    unsure = preds[0]
    unsure.confidence = 0.35
    session.commit()
    q = next(m for m in thread(team) if m["kind"] == "question" and m["payload"].get("type") == "case")
    guess = unsure.output["decision"]
    assert "decision" not in q["payload"] and guess.replace("_", " ") not in q["body"]  # its own answer stays sealed
    r = reply(team, q["id"], action="decide", value="escalate")
    assert r.status_code == 200, r.text
    case = session.get(Case, unsure.case_id)
    assert case.status == "decided"
    assert session.scalar(select(HumanAction).where(HumanAction.case_id == case.id, HumanAction.source == "conversation"))
    assert session.scalar(select(Comparison).where(Comparison.prediction_id == unsure.id)) is not None  # revealed and scored
    assert reply(team, q["id"], action="decide", value="escalate").status_code == 400  # already dealt with


def test_drafts_and_handbacks_arrive_as_work_and_are_handled_inline(team, client, session):
    tt = session.get(TaskType, team["tt"])
    tt.status, tt.tau, tt.calibration = "supervised", 0.2, {}
    session.commit()
    push(team, {"items": live_items(12)})
    drain(session)
    msgs = thread(team)
    drafts = [m for m in msgs if m["kind"] == "draft"]
    handbacks = [m for m in msgs if m["kind"] == "handback"]
    assert drafts and handbacks  # over-limit invoices always come back
    assert reply(team, drafts[0]["id"], action="approve").status_code == 200
    assert session.scalars(select(ActionLog).where(ActionLog.prediction_id == drafts[0]["payload"]["prediction_id"])).first().status == "approved"
    hb = handbacks[0]
    assert reply(team, hb["id"], action="decide", value="escalate").status_code == 200
    assert session.get(Case, hb["payload"]["case"]["id"]).status == "decided"
    # Dealt with elsewhere: the thread notices and closes the message.
    other = drafts[1]
    client.post(f"/supervised/{other['payload']['prediction_id']}/approve", json={}, headers=team["mentor"])
    assert next(m for m in thread(team) if m["id"] == other["id"])["status"] == "done"


def test_out_of_hours_nothing_interrupts(team, session):
    mentor = session.scalar(select(User).where(User.email == "mentor+invoice_mismatch@synthetic.test"))
    mentor.preferences = {}  # defaults: weekdays 9 to 5:30, London
    session.commit()
    tt = session.get(TaskType, team["tt"])
    assert service.thread(session, mentor, tt, now=SAT_3AM) == []  # no stand-up, no questions at 3am on a Saturday
    assert any(m["kind"] == "standup" for m in service.thread(session, mentor, tt, now=TUE_10AM))


def test_work_held_back_arrives_when_hours_open_up(team, session):
    tt = session.get(TaskType, team["tt"])
    tt.status, tt.tau, tt.calibration = "supervised", 0.2, {}
    session.commit()
    push(team, {"items": live_items(6)})
    drain(session)
    mentor = session.scalar(select(User).where(User.email == "mentor+invoice_mismatch@synthetic.test"))
    mentor.preferences = {}
    session.commit()
    assert service.thread(session, mentor, tt, now=SAT_3AM) == []  # drafts wait for Monday morning
    mentor.preferences = ALWAYS_ON  # the mentor says weekends are fine
    session.commit()
    assert any(m["kind"] == "draft" for m in service.thread(session, mentor, tt, now=SAT_3AM))
