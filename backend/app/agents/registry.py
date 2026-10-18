"""Agents an org can onboard: the built-in apprentice, or an external agent behind a webhook."""

import secrets
from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crypto
from app.agents.builtin import BuiltinApprentice
from app.agents.context import CaseContext
from app.agents.external import ExternalAgent, check_endpoint
from app.agents.offline import NearestCasesAgent
from app.agents.output import PredictionResult
from app.config import get_settings
from app.models import Agent, User


class Runner(Protocol):
    model: str

    def predict(self, ctx: CaseContext) -> PredictionResult: ...


_override: Callable[[Agent], Runner] | None = None


def set_runner_override(factory: Callable[[Agent], Runner] | None) -> None:
    """Tests can swap in their own agent behaviour; None restores the default."""
    global _override
    _override = factory


def runner_for(agent: Agent, samples: int | None = None) -> Runner:
    if _override is not None:
        return _override(agent)
    settings = get_settings()
    if agent.kind == "external":
        secret = crypto.decrypt(agent.config["secret"])
        return ExternalAgent(agent.endpoint or "", secret, agent.model,
                             timeout_s=float(agent.config.get("timeout_s", settings.external_agent_timeout_s)))
    if settings.anthropic_api_key:
        from app.llm.provider import AnthropicProvider

        from app.agents.tool_agent import ToolApprentice

        model = (agent.config or {}).get("model") or settings.apprentice_model  # set by a model swap
        provider = AnthropicProvider(model=model, api_key=settings.anthropic_api_key)
        plain = BuiltinApprentice(provider, samples=samples or settings.apprentice_samples, effort=settings.apprentice_effort)
        return ToolApprentice(provider, fallback=plain, effort=settings.apprentice_effort)  # tools when the role has them
    from app.agents.tool_agent import WorkbenchPlanner

    return WorkbenchPlanner(fallback=NearestCasesAgent())


def describe_runner(agent: Agent, samples: int | None = None) -> dict[str, Any]:
    """What a run with this agent will use, before it starts."""
    settings = get_settings()
    if agent.kind == "external":
        return {"kind": "external", "model": agent.model, "samples": 1, "billed_here": False}
    if settings.anthropic_api_key:
        return {"kind": "built_in", "model": (agent.config or {}).get("model") or settings.apprentice_model,
                "samples": samples or settings.apprentice_samples,
                "effort": settings.apprentice_effort, "billed_here": True}
    return {"kind": "built_in", "model": NearestCasesAgent.model, "samples": 1, "billed_here": False}


def org_agents(session: Session, org_id: str) -> list[Agent]:
    return list(session.scalars(select(Agent).where(Agent.org_id == org_id).order_by(Agent.kind, Agent.created_at)))


def create_external(session: Session, user: User, *, name: str, endpoint: str, version: str, model: str) -> tuple[Agent, str]:
    url = check_endpoint(endpoint, allow_http_localhost=get_settings().env == "dev")
    secret = "whsec_" + secrets.token_urlsafe(32)
    agent = Agent(org_id=user.org_id, kind="external", name=name, endpoint=url, model=model or "external",
                  version=version, config={"secret": crypto.encrypt(secret)})
    session.add(agent)
    session.commit()
    return agent, secret


def agent_out(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id, "kind": agent.kind, "name": agent.name or ("Built-in apprentice" if agent.kind == "built_in" else "External agent"),
        "endpoint": agent.endpoint, "model": agent.model, "version": agent.version, "created_at": agent.created_at,
        "runs_with": describe_runner(agent),
    }
