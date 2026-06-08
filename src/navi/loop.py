"""The Navi loop (build spec §6.4): route -> dispatch -> manual Anthropic tool loop.

Every tool call goes through ``broker()``. Budget is **stop-and-report** (spec §6.1): the loop
checks the per-run budget before each model call and returns a partial result rather than raising.
Run/trace persistence is deferred to Milestone 5; the SAP review prompt to Milestone 4.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from navi.broker import anthropic_tool_defs, broker
from navi.contracts import Allowed, Denied, RunContext, StructuredResult
from navi.model_client import Completer, get_profile
from navi.models import Agent, AgentTool, Tool
from navi.prompts import GENERAL, RESEARCH, SAP_REVIEW
from navi.router import dispatch_route, route

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 8  # safety backstop on the tool loop
_DEFAULT_AGENT_NAME = "navi"

# dispatched route -> (system prompt, model profile)
_DISPATCH: dict[str, tuple[str, str]] = {
    "answer_inline": (GENERAL, "daily_driver"),
    "research": (RESEARCH, "daily_driver"),
    "sap_review": (SAP_REVIEW, "deep_reasoning"),  # §8 review prompt (NAVI-8)
}


def _agent_and_scopes(session: Session, name: str = _DEFAULT_AGENT_NAME) -> tuple[str, list[str]]:
    """Return the agent id + the access scopes of its enabled, permitted tools."""
    agent = session.exec(select(Agent).where(Agent.name == name)).first()
    if agent is None:
        raise RuntimeError(f"default agent {name!r} not found; run `python -m navi.seed`")
    scopes: set[str] = set()
    for link in session.exec(select(AgentTool).where(AgentTool.agent_id == agent.id)).all():
        if not link.enabled:
            continue
        tool = session.get(Tool, link.tool_id)
        if tool is not None and tool.enabled:
            scopes.add(tool.access_scope)
    return agent.id, sorted(scopes)


def _collect_evidence(result: object, evidence: list[str]) -> None:
    if not isinstance(result, dict):
        return
    for item in result.get("results", []):
        if isinstance(item, dict):
            source = item.get("source") or item.get("url")
            if source:
                evidence.append(str(source))


def _result(
    ctx: RunContext, answer: str, evidence: list[str], *, truncated: bool
) -> StructuredResult:
    return StructuredResult(
        run_id=ctx.run_id,
        route=ctx.route or "",
        answer=answer,
        evidence=sorted(set(evidence)),
        cost_usd=round(ctx.cost_so_far_usd, 6),
        truncated=truncated,
    )


def run_loop(
    model: Completer,
    session: Session,
    ctx: RunContext,
    system: str,
    profile: str,
    user_text: str,
) -> StructuredResult:
    """Manual Anthropic tool loop. Each tool_use is brokered; budget hit -> stop-and-report."""
    tools = anthropic_tool_defs()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
    evidence: list[str] = []
    last_text = ""

    for _ in range(_MAX_ITERATIONS):
        if ctx.cost_so_far_usd >= ctx.max_cost_per_run:
            return _result(
                ctx, last_text or "[stopped: per-run budget reached]", evidence, truncated=True
            )

        resp = model.complete(profile, messages, tools, system)
        ctx.cost_so_far_usd += resp.cost_usd
        if resp.text:
            last_text = resp.text

        if resp.stop_reason != "tool_use":
            return _result(ctx, resp.text, evidence, truncated=False)

        messages.append({"role": "assistant", "content": resp.content})
        tool_results: list[dict[str, Any]] = []
        for tu in resp.tool_uses:
            verdict = broker(session, ctx.agent_id, tu.name, tu.input, ctx)
            if isinstance(verdict, Allowed):
                _collect_evidence(verdict.result, evidence)
                payload = json.dumps(verdict.result)
            elif isinstance(verdict, Denied):
                payload = f"DENIED by tool broker: {verdict.reason}"  # surfaced to the model
            else:  # ApprovalRequired — unreachable in the read-only MVP; handled defensively
                payload = f"APPROVAL REQUIRED: {verdict.action_id}"
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.id, "content": payload}
            )
        messages.append({"role": "user", "content": tool_results})

    return _result(
        ctx, last_text or "[stopped: tool-loop iteration cap reached]", evidence, truncated=True
    )


def _clarify_or_refuse(dispatched: str, decision_reason: str) -> str:
    if dispatched == "clarify":
        return f"I need a bit more to act on that. {decision_reason}".strip()
    return (
        "I can't help with that — it's outside this read-only assistant's scope. "
        f"{decision_reason}"
    ).strip()


def handle_request(text: str, *, model: Completer, session: Session) -> StructuredResult:
    """Route -> dispatch -> run. Builds the RunContext with a real budget from the chosen profile.

    NB: the routing classifier's (cheap_triage) cost is not folded into ``cost_usd`` here; full
    cost accounting lands with trace persistence in Milestone 5.
    """
    agent_id, scopes = _agent_and_scopes(session)
    decision = route(model, text)
    dispatched = dispatch_route(decision)
    run_id = uuid4().hex

    if dispatched in ("clarify", "refuse"):
        return StructuredResult(
            run_id=run_id, route=dispatched, answer=_clarify_or_refuse(dispatched, decision.reason)
        )

    system, profile = _DISPATCH[dispatched]
    prof = get_profile(profile)
    ctx = RunContext(
        run_id=run_id,
        agent_id=agent_id,
        route=dispatched,
        max_cost_per_run=float(prof["max_cost_per_run"]),  # real budget — not the 0.0 default
        scopes=scopes,
    )
    return run_loop(model, session, ctx, system, profile, text)
