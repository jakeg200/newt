"""M6 acceptance, on synthetic data until a design partner's is in: the whole programme runs end
to end with no database edits (provisioning aside), using the real built-in agent (offline
baseline here, since tests never call the API)."""

from app.worker import run_once
from demo.programme import People, provision, run


def test_whole_programme_runs_end_to_end(client, session):
    people: People = provision(session)

    def drain() -> None:
        for _ in range(200):
            if not run_once(session):
                return

    log: list[str] = []
    out = run(client, drain, people, log=log.append)
    assert "stopped" not in out, (out, log)
    assert out["handbook_version"] == 1 and out["history_cases"] == 420, out
    assert out["evaluation"]["eligible"] and out["evaluation"]["ucb"] <= 0.02, out
    assert out["supervised_cases"] >= 50, out
    assert out["autonomous"]["cases_handled"] > 0 and out["autonomous"]["audits"]["failed"] == 0, out
    assert out["track_record"]["status"] == "autonomous" and set(out["track_record"]["signoffs"]) == {"mentor", "manager"}, out
    assert out["dashboard"]["cases_handled"] > 0 and out["dashboard"]["hours_returned"] > 0, out
    assert out["model_swap"]["recertified"] is True and out["model_swap"]["status"] == "autonomous", out
    assert out["model_swap"]["duration_s"] < 600, out
