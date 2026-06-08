"""Pydantic / dataclass contracts (build spec §7).

Only the contracts needed so far are defined. ``RouteDecision``, ``StructuredResult`` and
``MemoryCandidate`` arrive with the milestones that use them (router/loop = M3, memory = M5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


class RunContext(BaseModel):
    """Run identity + live budget + permitted scopes, threaded through the loop and broker.

    ``cost_so_far_usd`` is accumulated after each model call (spec §6.1); the broker reads it for
    the budget check. ``scopes`` are the data scopes this agent may touch (broker scope check).
    """

    run_id: str
    agent_id: str
    route: str | None = None
    # NB: defaults to 0.0, which makes the broker's budget check (cost_so_far_usd >= max) deny
    # EVERY tool call. The M3 loop MUST set a real per-run budget from the model_profile, or no
    # tool ever runs. Safe-by-default (deny), but set it explicitly.
    max_cost_per_run: float = 0.0
    cost_so_far_usd: float = 0.0
    scopes: list[str] = Field(default_factory=list)


# --- Broker verdicts (spec §6.2: Allowed | Denied | ApprovalRequired) --------------------
# Frozen dataclasses rather than Pydantic models so ``Allowed.result`` can carry an arbitrary
# tool result without model-config gymnastics.


@dataclass(frozen=True)
class Allowed:
    result: Any


@dataclass(frozen=True)
class Denied:
    reason: str


@dataclass(frozen=True)
class ApprovalRequired:
    action_id: str


BrokerVerdict = Allowed | Denied | ApprovalRequired


# --- router + result contracts (spec §7) --------------------------------------------------

Route = Literal["answer_inline", "sap_review", "research", "clarify", "refuse"]


class RouteDecision(BaseModel):
    """The classifier returns only this (spec §6.5). Dispatch policy is code, not the model."""

    route: Route
    confidence: float
    risk: Literal["low", "medium", "high"]
    requires_approval: bool = False
    reason: str = ""


class StructuredResult(BaseModel):
    """The answer to a request (spec §7). ``truncated`` is set when the run stopped on budget."""

    run_id: str
    route: str
    answer: str
    evidence: list[str] = Field(default_factory=list)  # source paths / urls
    cost_usd: float = 0.0
    needs_approval: bool = False
    truncated: bool = False

