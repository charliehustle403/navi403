"""The Navi loop (build spec §6.4): route -> dispatch -> manual Anthropic tool loop.

Every tool call goes through ``broker()``. Budget is **stop-and-report** (spec §6.1): the loop
checks the per-run budget before each model call and returns a partial result rather than raising.
Each run opens a ``runs`` row and records ``trace_events`` (route / model_call / broker_decision /
error) via a RunRecorder (Milestone 5).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlmodel import Session, select

from navi.broker import anthropic_tool_defs, broker
from navi.contracts import Allowed, Denied, RunContext, StructuredResult
from navi.model_client import Completer, get_profile
from navi.models import Agent, AgentTool, Tool
from navi.prompts import GENERAL, RESEARCH, SAP_REVIEW
from navi.router import dispatch_route, route
from navi.trace import RunRecorder, close_run, open_run

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 8  # safety backstop on the tool loop
_DEFAULT_AGENT_NAME = "navi"
# NAVI-15: per-run, per-tool call cap (DoS/cost backstop). Used when a model profile omits
# ``max_calls_per_tool``; profiles may override in model_profiles.json (config, not code).
_DEFAULT_MAX_CALLS_PER_TOOL = 5

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


def _corpus_strings(result: object) -> list[str]:
    """Walk a tool-result dict, returning all its string values (NAVI-13 egress-context corpus).

    Pure helper: ``str`` collected, ``dict``/``list`` recursed, other scalars skipped. Folds a
    knowledge_base_search result's text into the run's egress corpus so a later outbound web_search
    query that echoes a long verbatim KB span is caught by the broker.
    """
    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(result)
    return out


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
    recorder: RunRecorder | None = None,
) -> StructuredResult:
    """Manual Anthropic tool loop. Each tool_use is brokered; budget hit -> stop-and-report."""
    tools = anthropic_tool_defs()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
    evidence: list[str] = []
    last_text = ""
    broker_tracer = recorder.broker_decision if recorder is not None else None
    # NAVI-13 egress corpus: the run's own sensitive text. Seeded with the user message; grows with
    # each Allowed knowledge_base_search output. Prior web_search outputs are deliberately excluded
    # (external/public). Threaded onto ctx so the broker can deny verbatim-span echoes outbound.
    corpus: list[str] = [user_text]

    for _ in range(_MAX_ITERATIONS):
        if ctx.cost_so_far_usd >= ctx.max_cost_per_run:
            return _result(
                ctx, last_text or "[stopped: per-run budget reached]", evidence, truncated=True
            )

        resp = model.complete(profile, messages, tools, system)
        if recorder is not None:
            recorder.model_call(resp)
        ctx.cost_so_far_usd += resp.cost_usd
        if resp.text:
            last_text = resp.text

        if resp.stop_reason != "tool_use":
            return _result(ctx, resp.text, evidence, truncated=False)

        messages.append({"role": "assistant", "content": resp.content})
        tool_results: list[dict[str, Any]] = []
        for tu in resp.tool_uses:
            # Refresh the egress corpus (user text + KB outputs so far) before brokering, so the
            # next outbound query is checked against everything sensitive pulled this run.
            ctx.egress_context = tuple(corpus)
            verdict = broker(session, ctx.agent_id, tu.name, tu.input, ctx, tracer=broker_tracer)
            if isinstance(verdict, Allowed):
                _collect_evidence(verdict.result, evidence)
                if tu.name == "knowledge_base_search":
                    corpus.extend(_corpus_strings(verdict.result))
                # NAVI-15: count executed calls per tool so the broker can rate-limit the next one.
                ctx.tool_calls[tu.name] = ctx.tool_calls.get(tu.name, 0) + 1
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
    """Route -> dispatch -> run, persisting a run + trace events. Budget from the chosen profile.

    The routing classifier's cost is folded into the run total via the recorder (it accumulates
    cost across the classifier call and every loop call).
    """
    agent_id, scopes = _agent_and_scopes(session)
    run = open_run(session, agent_id)
    recorder = RunRecorder(session, run.id)

    try:
        decision = route(model, text, recorder)
        dispatched = dispatch_route(decision)
        recorder.route_event(dispatched, decision)
        run.route = dispatched

        if dispatched in ("clarify", "refuse"):
            answer = _clarify_or_refuse(dispatched, decision.reason)
            result = StructuredResult(
                run_id=run.id, route=dispatched, answer=answer, cost_usd=round(recorder.cost, 6)
            )
            close_run(session, run, status="refused" if dispatched == "refuse" else "ok",
                      cost_usd=recorder.cost)
            return result

        system, profile = _DISPATCH[dispatched]
        prof = get_profile(profile)
        ctx = RunContext(
            run_id=run.id,
            agent_id=agent_id,
            route=dispatched,
            max_cost_per_run=float(prof["max_cost_per_run"]),  # real budget — not the 0.0 default
            cost_so_far_usd=recorder.cost,  # carry the classifier cost into the budget + total
            scopes=scopes,
            # NAVI-15: per-tool call cap from the profile (config), with a safe default fallback.
            max_calls_per_tool=int(prof.get("max_calls_per_tool", _DEFAULT_MAX_CALLS_PER_TOOL)),
        )
        result = run_loop(model, session, ctx, system, profile, text, recorder)
        close_run(session, run, status="truncated" if result.truncated else "ok",
                  cost_usd=ctx.cost_so_far_usd)
        return result
    except Exception as exc:
        recorder.error(str(exc))
        close_run(session, run, status="error", cost_usd=recorder.cost)
        raise
