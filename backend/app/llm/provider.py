"""Every model call goes through a Provider, so models can be swapped and the track record decides.

`AnthropicProvider` calls Claude with a JSON-schema-constrained output. `FakeProvider` returns
whatever its responder function computes, for tests and for running without an API key.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import get_settings

# USD per million tokens (input, output, cache read). Cache writes cost 1.25 × input.
# Source: Anthropic pricing, cached 2026-10-06.
PRICES_PER_MTOK: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
}


class ProviderError(RuntimeError):
    """The model call failed or returned something unusable. The message is safe to show users."""


@dataclass
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    input_tokens: int = 0  # all input, cached or not
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def meta(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cost_usd": round(self.cost_usd, 4),
            "duration_s": round(self.duration_s, 2),
            "request_id": self.request_id,
            **self.extra,
        }


class Provider(Protocol):
    name: str
    model: str

    def complete_json(
        self, *, task: str, system: str, user: str, schema: dict[str, Any], effort: str = "medium",
        cache_system: bool = False, max_tokens: int | None = None,
    ) -> LLMResult: ...


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0) -> float:
    """`input_tokens` here is the uncached remainder; cache writes and reads are priced separately."""
    price_in, price_out, price_read = PRICES_PER_MTOK.get(model, (0.0, 0.0, 0.0))
    return (input_tokens * price_in + cache_write * price_in * 1.25 + cache_read * price_read
            + output_tokens * price_out) / 1_000_000


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, api_key: str | None = None, max_tokens: int = 64000) -> None:
        import anthropic

        self.model = model
        self.max_tokens = max_tokens
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def complete_json(
        self, *, task: str, system: str, user: str, schema: dict[str, Any], effort: str = "medium",
        cache_system: bool = False, max_tokens: int | None = None,
    ) -> LLMResult:
        anthropic = self._anthropic
        started = time.monotonic()
        limit = max_tokens or self.max_tokens
        # A cached system prompt (handbook + instructions) is billed at ~5% on repeat calls.
        system_param: Any = (
            [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if cache_system else system
        )
        try:
            # Streaming keeps long outputs clear of HTTP timeouts. On a policy decline the API
            # re-runs the request on a fallback model it picks by refusal category.
            with self._client.beta.messages.stream(
                model=self.model,
                max_tokens=limit,
                system=system_param,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise ProviderError("Anthropic API key was rejected") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("Anthropic rate limit hit; try again in a minute") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("could not reach the Anthropic API") from exc

        if message.stop_reason == "refusal":
            category = message.stop_details.category if message.stop_details else None
            raise ProviderError(f"the model declined this {task} (category: {category})")
        if message.stop_reason == "max_tokens":
            raise ProviderError(f"the {task} was cut off at {limit} output tokens")
        text = next((b.text for b in message.content if b.type == "text"), None)
        if text is None:
            raise ProviderError(f"the model returned no {task}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"the model returned invalid JSON for the {task}") from exc

        usage = message.usage
        cache_write = getattr(usage, "cache_creation_input_tokens", None) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
        return LLMResult(
            data=data,
            provider=self.name,
            model=message.model,  # the fallback model if one served the request
            input_tokens=usage.input_tokens + cache_write + cache_read,
            output_tokens=usage.output_tokens,
            cache_read_tokens=cache_read,
            cost_usd=cost_usd(message.model, usage.input_tokens, usage.output_tokens, cache_write, cache_read),
            duration_s=time.monotonic() - started,
            request_id=getattr(message, "_request_id", None),
            extra={"effort": effort},
        )


Responder = Callable[[str, str, str, dict[str, Any]], dict[str, Any]]


class FakeProvider:
    """Deterministic stand-in. `responders` maps a task name to a function of
    (task, system, user, schema) that returns the JSON the model would have produced."""

    name = "fake"
    model = "fake-provider"

    def __init__(self, responders: dict[str, Responder] | None = None) -> None:
        self.responders = responders or {}
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self, *, task: str, system: str, user: str, schema: dict[str, Any], effort: str = "medium",
        cache_system: bool = False, max_tokens: int | None = None,
    ) -> LLMResult:
        self.calls.append({"task": task, "system": system, "user": user, "effort": effort, "cache_system": cache_system})
        if task not in self.responders:
            raise ProviderError(f"no fake responder for {task!r}; set ANTHROPIC_API_KEY to use Claude")
        started = time.monotonic()
        data = self.responders[task](task, system, user, schema)
        return LLMResult(data=data, provider=self.name, model=self.model, duration_s=time.monotonic() - started)


_override: Provider | None = None


def set_provider(provider: Provider | None) -> None:
    """Tests and scripts can force a provider; None restores the default choice."""
    global _override
    _override = provider


def get_provider() -> Provider:
    if _override is not None:
        return _override
    settings = get_settings()
    if settings.anthropic_api_key:
        return AnthropicProvider(model=settings.llm_model, api_key=settings.anthropic_api_key)
    from app.orientation.offline import offline_responders

    return FakeProvider(offline_responders())
