"""Test doubles for the model client — no network, no API key.

A ``FakeModel`` returns scripted ``ModelResponse`` objects on successive ``complete`` calls and
records what it was called with, so tests can drive the router and the tool loop deterministically.
"""

from __future__ import annotations

from typing import Any

from navi.model_client import ModelResponse, ToolUse


class FakeModel:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, list[dict[str, Any]], Any, Any]] = []

    def complete(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> ModelResponse:
        self.calls.append((profile, messages, tools, system))
        if not self._responses:
            raise AssertionError("FakeModel ran out of scripted responses")
        return self._responses.pop(0)


def text_response(text: str, *, cost: float = 0.001) -> ModelResponse:
    return ModelResponse(
        text=text, tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=10,
        cost_usd=cost, content=[{"type": "text", "text": text}],
    )


def tool_use_response(
    name: str, tool_input: dict[str, Any], *, cost: float = 0.001, tu_id: str = "tu1"
) -> ModelResponse:
    block = {"type": "tool_use", "id": tu_id, "name": name, "input": tool_input}
    return ModelResponse(
        text="", tool_uses=[ToolUse(id=tu_id, name=name, input=tool_input)],
        stop_reason="tool_use", input_tokens=10, output_tokens=10, cost_usd=cost, content=[block],
    )
