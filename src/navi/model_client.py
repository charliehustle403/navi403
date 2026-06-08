"""model_profiles wrapper over the Anthropic Client SDK (build spec §6.1, §3).

Logic references profile *names*; the name->model mapping, per-run budgets, and the token->USD
pricing table all live in the config file (``model_profiles.json``), not here. ``complete`` is
the only place the model is called; it normalizes the SDK response to plain dicts/dataclasses so
the loop has no SDK-type coupling and tests can pass a fake client (no network, no key).

This is the **Client SDK with a manual tool loop** — never the Agent SDK, never server-side
tools (they would bypass the broker).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from navi.config import get_settings

logger = logging.getLogger(__name__)

# Built-in fallback used only if the config file is missing/unreadable.
_DEFAULT_CONFIG: dict[str, Any] = {
    "profiles": {
        "cheap_triage": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001",
                         "max_cost_per_run": 0.05, "max_tokens": 512},
        "daily_driver": {"provider": "anthropic", "model": "claude-sonnet-4-6",
                         "max_cost_per_run": 0.50, "max_tokens": 2048},
        "deep_reasoning": {"provider": "anthropic", "model": "claude-opus-4-8",
                           "max_cost_per_run": 3.00, "max_tokens": 4096},
        "local_private": {"provider": "ollama", "model": "configurable",
                          "max_cost_per_run": 0.0, "max_tokens": 2048, "no_cloud": True},
    },
    "pricing": {
        "claude-haiku-4-5-20251001": {"input_per_mtok": 1.0, "output_per_mtok": 5.0},
        "claude-sonnet-4-6": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
        "claude-opus-4-8": {"input_per_mtok": 15.0, "output_per_mtok": 75.0},
    },
}


@lru_cache
def load_config() -> dict[str, Any]:
    path = Path(get_settings().model_profiles_path)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.exception("Failed to read %s; falling back to built-in defaults", path)
    return _DEFAULT_CONFIG


def get_profile(name: str) -> dict[str, Any]:
    profiles = load_config()["profiles"]
    if name not in profiles:
        raise KeyError(f"unknown model profile: {name!r}")
    return dict(profiles[name])


def price(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost from the config pricing table. Unknown model -> 0.0 (logged)."""
    rate = load_config().get("pricing", {}).get(model)
    if rate is None:
        logger.warning("no pricing for model %r; recording cost 0.0", model)
        return 0.0
    return (
        input_tokens / 1_000_000 * rate["input_per_mtok"]
        + output_tokens / 1_000_000 * rate["output_per_mtok"]
    )


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ModelResponse:
    text: str
    tool_uses: list[ToolUse]
    stop_reason: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    content: list[dict[str, Any]]  # raw assistant blocks (dicts) — re-appended to messages


class Completer(Protocol):
    """The interface the loop/router depend on — satisfied by ModelClient and by test fakes."""

    def complete(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> ModelResponse: ...


class ModelClient:
    """Calls Anthropic's Messages API for a named profile and normalizes the response."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else get_settings().anthropic_api_key
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set; cannot call the model.")
            import anthropic  # lazy: importing this module must not require the SDK/key

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> ModelResponse:
        prof = get_profile(profile)
        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": prof["model"],
            "max_tokens": prof.get("max_tokens", 2048),
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        resp = client.messages.create(**kwargs)

        content = [block.model_dump() for block in resp.content]
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        tool_uses = [
            ToolUse(id=b["id"], name=b["name"], input=b.get("input", {}))
            for b in content
            if b.get("type") == "tool_use"
        ]
        cost = price(prof["model"], resp.usage.input_tokens, resp.usage.output_tokens)
        return ModelResponse(
            text=text,
            tool_uses=tool_uses,
            stop_reason=resp.stop_reason or "end_turn",
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cost_usd=cost,
            content=content,
        )
