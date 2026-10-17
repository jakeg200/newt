"""External agents: we POST each case to the agent's endpoint and it returns its answer in the
task's output shape. Requests are signed so the agent can check they came from us:

    X-Agent-Onboarding-Signature: sha256=<hex HMAC-SHA256 of the raw body, keyed with the signing secret>

The same scoring applies whoever built the agent."""

import hashlib
import hmac
import ipaddress
import json
import time
from urllib.parse import urlparse

import httpx

from app.agents.context import CaseContext
from app.agents.output import PredictionResult, output_schema, validate_output

SIGNATURE_HEADER = "X-Agent-Onboarding-Signature"


class EndpointError(ValueError):
    pass


def check_endpoint(url: str, *, allow_http_localhost: bool) -> str:
    """HTTPS only (plain HTTP to localhost in development), and never link-local or metadata
    addresses, so a registered endpoint can't be used to probe our own network."""
    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    if not host:
        raise EndpointError("endpoint needs a host")
    local = host in ("localhost", "127.0.0.1", "::1")
    if local and not allow_http_localhost:
        raise EndpointError("endpoint can't be this server's own machine")
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        raise EndpointError("endpoint must use https")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and (ip.is_link_local or ip.is_multicast or ip.is_unspecified or (ip.is_private and not local)):
        raise EndpointError("endpoint can't be a private or link-local address")
    return url.strip()


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class ExternalAgent:
    def __init__(self, endpoint: str, secret: str, model: str, timeout_s: float = 30.0, http: httpx.Client | None = None) -> None:
        self.endpoint, self.secret, self.model = endpoint, secret, model
        self.http = http or httpx.Client(timeout=timeout_s, follow_redirects=False)

    def predict(self, ctx: CaseContext) -> PredictionResult:
        body = json.dumps({**ctx.payload(), "response_schema": output_schema(ctx.task)}, ensure_ascii=False,
                          sort_keys=True).encode()
        started = time.monotonic()
        try:
            resp = self.http.post(self.endpoint, content=body, headers={
                "Content-Type": "application/json", SIGNATURE_HEADER: sign(self.secret, body),
                "X-Agent-Onboarding-Case": ctx.case_id,
            })
        except httpx.TimeoutException:
            return self._fail("the agent timed out", started)
        except httpx.HTTPError:
            return self._fail("couldn't reach the agent", started)
        if resp.status_code != 200:
            return self._fail(f"the agent answered HTTP {resp.status_code}", started)
        try:
            out = validate_output(resp.json(), ctx.task)
        except (ValueError, json.JSONDecodeError) as exc:
            return self._fail(f"the agent's answer didn't fit the task: {exc}"[:300], started)
        return PredictionResult(out.model_dump(), out.self_reported_confidence, self.model,
                                latency_ms=int((time.monotonic() - started) * 1000))

    def _fail(self, error: str, started: float) -> PredictionResult:
        return PredictionResult(None, None, self.model, error=error, latency_ms=int((time.monotonic() - started) * 1000))
