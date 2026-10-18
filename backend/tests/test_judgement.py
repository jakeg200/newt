"""Judgement capture: the ledger of written and unwritten knowledge, exceptions mined from disagreements and confirmed
by the mentor, contradictions, the "why" behind corrections, and the exported playbook."""

import pytest
from sqlalchemy import select

from app.agents import registry
from app.agents.output import PredictionResult
from app.learning import judgement
from app.models import Apprenticeship, Lesson, Rule, TaskType

from tests.graduation_fixtures import backtest, setup_team

ALWAYS_ON = {"start": "00:00", "end": "23:59", "workdays": [0, 1, 2, 3, 4, 5, 6], "questions_per_day": 10}


class AlwaysApprove:
    """An intern that hasn't learned the exceptions yet."""

    model = "always-approve"

    def predict(self, ctx) -> PredictionResult:
        return PredictionResult({"decision": "approve", "fields": {"variance_reason": "price", "gl_code": "6400"}, "text_outputs": {},
                                 "rationale": "", "missing_info": [], "self_reported_confidence": 0.9}, 0.9, self.model)


@pytest.fixture
def team(client, session):
    ctx = setup_team(client, session)
    client.patch("/me/preferences", json=ALWAYS_ON, headers=ctx["mentor"])
    registry.set_runner_override(lambda agent: AlwaysApprove())
    backtest(ctx, session, limit=150)
    yield ctx
    registry.set_runner_override(None)


def test_ledger_separates_written_and_unwritten_with_evidence(team, client, session):
    client.post("/rules", json={"task_type_id": team["tt"], "text": 'When an item mentions "units", choose query supplier.'}, headers=team["mentor"])
    led = client.get(f"/task-types/{team['tt']}/judgement", headers=team["manager"]).json()
    rule = next(u for u in led["unwritten"] if '"units"' in u["text"])
    assert rule["learned"] == "told by the mentor" and rule["coverage"] > 10 and rule["passes"] is True
    assert led["decisions"] > 100 and 0 < led["explicit_share"] < 1


def test_exceptions_are_mined_from_mistakes_and_confirmed_by_the_mentor(team, client, session):
    tt = session.get(TaskType, team["tt"])
    found = judgement.exceptions(session, tt)
    assert found and all(e["misses"] >= judgement.EXCEPTION_MIN and e["agreement"] >= 0.8 for e in found)
    msgs = client.get(f"/messages?task_type_id={team['tt']}", headers=team["mentor"]).json()["messages"]
    q = next(m for m in msgs if m["kind"] == "question" and m["payload"].get("type") == "exception")
    version = session.get(Apprenticeship, tt.apprenticeship_id).rules_version
    r = client.post(f"/messages/{q['id']}/reply", json={"action": "confirm", "value": "yes"}, headers=team["mentor"])
    assert r.status_code == 200, r.text
    session.expire_all()
    assert session.scalar(select(Rule).where(Rule.text == q["payload"]["text"])) is not None
    assert session.get(Apprenticeship, tt.apprenticeship_id).rules_version > version
    assert client.post(f"/messages/{q['id']}/reply", json={"action": "confirm", "value": "yes"}, headers=team["manager"]).status_code == 404  # not theirs


def test_conflicting_rules_are_flagged(team, client):
    for text in ('When an item mentions "units", choose query supplier.', 'When an item mentions "units", choose escalate.'):
        client.post("/rules", json={"task_type_id": team["tt"], "text": text}, headers=team["mentor"])
    led = client.get(f"/task-types/{team['tt']}/judgement", headers=team["mentor"]).json()
    assert led["conflicts"] and led["conflicts"][0]["cases"] >= 2


def test_the_why_behind_a_correction_is_asked_and_kept(team, client, session):
    card = client.get(f"/teaching/queue?task_type_id={team['tt']}&limit=5", headers=team["mentor"]).json()["cards"][0]
    client.post("/lessons", json={"prediction_id": card["prediction_id"], "attribution": "intern_wrong"}, headers=team["mentor"])
    msgs = client.get(f"/messages?task_type_id={team['tt']}", headers=team["mentor"]).json()["messages"]
    why = next(m for m in msgs if m["kind"] == "question" and m["payload"].get("type") == "why")
    r = client.post(f"/messages/{why['id']}/reply", json={"action": "answer", "value": "Short deliveries always go back; call Jo on 07700 900123"},
                    headers=team["mentor"])
    assert r.status_code == 200
    note = session.get(Lesson, why["payload"]["lesson_id"]).note
    assert "Short deliveries" in note and "07700" not in note
    led = client.get(f"/task-types/{team['tt']}/judgement", headers=team["mentor"]).json()
    assert any("Short deliveries" in n["note"] for n in led["notes"])


def test_playbook_exports(team, client):
    md = client.get(f"/task-types/{team['tt']}/judgement.md", headers=team["manager"])
    assert md.status_code == 200 and "how the team decides" in md.text
    pdf = client.get(f"/task-types/{team['tt']}/judgement.pdf", headers=team["manager"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
