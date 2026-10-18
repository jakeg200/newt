"""How an action reaches the firm's system.

Actions refer to the source item ("reply to the sender of item INV-91007"), never to people's real details: Newt only
holds redacted text and keyed hashes, and the receiving system knows who the item came from. Requests are signed
like external-agent calls, so the system can check they came from Newt:

    X-Newt-Signature: sha256=<hex HMAC-SHA256 of the raw body, keyed with the destination's secret>

A system answers 2xx with {"status": "done", "ref": "..."} when it finished at once, or {"status": "accepted"} and
confirms later at the callback URL (signed the same way).
"""

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx

from app.agents.external import sign

SIGNATURE_HEADER = "X-Newt-Signature"


@dataclass
class ExecResult:
    status: Literal["done", "accepted", "error"]
    ref: str | None = None
    detail: str = ""
    simulated: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class Executor(Protocol):
    def execute(self, payload: dict[str, Any]) -> ExecResult: ...


class SimulatedExecutor:
    """No system connected yet: the action is recorded as done, and everywhere it shows it was simulated."""

    def execute(self, payload: dict[str, Any]) -> ExecResult:
        return ExecResult("done", ref=f"simulated:{payload['action_id'][:8]}", detail="simulated: no system connected", simulated=True)


_http_override: httpx.Client | None = None


def set_http(client: httpx.Client | None) -> None:
    """Tests (and the demo) can route webhook calls through their own client."""
    global _http_override
    _http_override = client


def lookup_via(session, tt):
    """A lookup function for live work: asks the first destination that answers queries ("query" in its actions).
    Resolved on the calling thread, so the workbench itself never touches the database."""
    from app.execution import destinations

    dest = destinations.for_action(session, tt, "query")
    if dest is None:
        return None
    url, secret = dest.url, destinations.secret_of(dest)

    def ask(kind: str, ref: str) -> dict[str, Any] | None:
        body = json.dumps({"type": "query", "action": "query", "kind": kind, "ref": ref}, sort_keys=True).encode()
        try:
            resp = (_http_override or httpx.Client(timeout=10.0)).post(url, content=body, headers={
                "Content-Type": "application/json", SIGNATURE_HEADER: sign(secret, body)})
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return None
        record = data.get("record") if isinstance(data, dict) else None
        return record if isinstance(record, dict) else None

    return ask


class WebhookExecutor:
    def __init__(self, url: str, secret: str, timeout_s: float = 10.0) -> None:
        self.url, self.secret = url, secret
        self.http = _http_override or httpx.Client(timeout=timeout_s, follow_redirects=False)

    def execute(self, payload: dict[str, Any]) -> ExecResult:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        try:
            resp = self.http.post(self.url, content=body, headers={"Content-Type": "application/json",
                                                                   SIGNATURE_HEADER: sign(self.secret, body)})
        except httpx.TimeoutException:
            return ExecResult("error", detail="the system didn't answer in time")
        except httpx.HTTPError:
            return ExecResult("error", detail="couldn't reach the system")
        if not 200 <= resp.status_code < 300:
            return ExecResult("error", detail=f"the system answered HTTP {resp.status_code}")
        try:
            data = resp.json() if resp.content else {}
        except json.JSONDecodeError:
            data = {}
        status = data.get("status", "done")
        if status == "failed":
            return ExecResult("error", detail=str(data.get("detail") or "the system said it couldn't do it")[:300])
        return ExecResult("accepted" if status == "accepted" else "done", ref=str(data.get("ref") or "")[:200] or None)
