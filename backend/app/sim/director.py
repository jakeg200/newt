"""The director: the firm's system and the outside world during a replay.

It answers Newt's actions the way the system did (done, at the simulated moment), and lets the recorded world happen
at its recorded times: a supplier's reply is already in the history, and `execution.service.moved_on` only sees it
once the clock has reached it. Where the history has no answer (Newt chased and the recording has no reply), there is
silence. The director never invents a reply, a record or a person's answer.
"""

from typing import Any

from app.clock import SimClock
from app.execution.executor import ExecResult

ACTION_WHAT = {"send_reply": "replied", "draft_reply": "drafted a reply", "set_status": "set the status",
               "add_label": "labelled it", "forward": "forwarded it", "query": "looked it up"}


class Director:
    def __init__(self, clock: SimClock) -> None:
        self.clock = clock
        self.events: list[dict[str, Any]] = []

    def execute(self, payload: dict[str, Any]) -> ExecResult:
        params = payload.get("params") or {}
        what = "chased" if params.get("follow_up") else ACTION_WHAT.get(payload["action"], payload["action"].replace("_", " "))
        if payload["action"] == "set_status" and params.get("value"):
            what = f"set the status to {params['value']}"
        self.events.append({"at": self.clock.t, "who": "newt", "what": what, "action": payload["action"],
                            "follow_up": bool(params.get("follow_up"))})
        return ExecResult("done", ref=f"replay:{payload['action_id'][:8]}")
