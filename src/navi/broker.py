"""The tool broker — the security boundary (build spec §3, §6.2).

Every tool call goes through ``broker()``; it is the only code path that executes a tool. The
tool callables live in ``navi.tools`` (underscore-private, ``__all__ = []``) and are referenced
only from the private ``_REGISTRY`` this module owns — so no other module can call a tool
directly. The broker is deterministic: plain, ordered code, no model in the loop.

Milestone 2 scope: read-only enforcement, the agent-permission read, arg validation, scope and
egress checks, and the per-run budget gate. The ``approval_required`` verdict exists but is never
returned (no write tools ship). DB-backed trace persistence is wired in Milestone 5; here the
broker emits its decision through an injectable ``tracer`` that defaults to logging.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from navi.contracts import Allowed, ApprovalRequired, BrokerVerdict, Denied, RunContext
from navi.models import AgentTool, Tool
from navi.tools import (
    KnowledgeBaseSearchArgs,
    WebSearchArgs,
    _knowledge_base_search,
    _web_search,
)

__all__ = [
    "Allowed", "ApprovalRequired", "BrokerVerdict", "Denied", "RunContext",
    "anthropic_tool_defs", "broker",
]

logger = logging.getLogger(__name__)

Tracer = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ToolSpec:
    """A tool's intrinsic, code-owned properties (the source of truth for the broker checks)."""

    name: str
    args_model: type[BaseModel]
    fn: Callable[[Any], dict[str, Any]]
    kind: str  # read_only | write  (MVP registry holds read_only only)
    access_scope: str
    egress_checked: bool
    description: str = ""
    enabled: bool = True


# The registry the broker owns. Private — nothing outside this module references it.
_REGISTRY: dict[str, ToolSpec] = {
    "knowledge_base_search": ToolSpec(
        name="knowledge_base_search",
        args_model=KnowledgeBaseSearchArgs,
        fn=_knowledge_base_search,
        kind="read_only",
        access_scope="kb",
        egress_checked=False,  # local file read — no outbound channel
        description="Keyword-search the local SAP knowledge base; returns top matching snippets "
        "with their source file paths.",
    ),
    "web_search": ToolSpec(
        name="web_search",
        args_model=WebSearchArgs,
        fn=_web_search,
        kind="read_only",
        access_scope="web",
        egress_checked=True,  # outbound — the exfiltration backstop applies
        description="Search the public web for current information; returns title/url/snippet "
        "results.",
    ),
}


# --- egress / exfiltration backstop (spec §3, §6.2) ---------------------------------------

_MAX_QUERY_LEN = 512
_MAX_TOKEN_LEN = 40  # a single opaque blob this long in a search query smells like exfil
_CRED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "openai-style key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws access key id"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\."), "jwt"),
    (re.compile(r"[0-9a-fA-F]{32,}"), "long hex secret"),
]


def _egress_check(value: str) -> str | None:
    """Return a block reason if an outbound string looks like data exfiltration, else None.

    Deterministic guard — the broker does not trust the model to "surface, not obey".
    TODO(scope): add PII-shaped detection (emails/SSNs) once false-positive tuning is worth it.
    """
    if len(value) > _MAX_QUERY_LEN:
        return f"value too long ({len(value)} > {_MAX_QUERY_LEN} chars)"
    for token in value.split():
        if len(token) >= _MAX_TOKEN_LEN:
            return f"contains a long opaque token ({len(token)} chars)"
    for pattern, label in _CRED_PATTERNS:
        if pattern.search(value):
            return f"matches credential pattern ({label})"
    return None


def _string_values(model: BaseModel) -> list[str]:
    return [v for v in model.model_dump().values() if isinstance(v, str)]


def _agent_permitted(session: Session, agent_id: str, tool_name: str) -> bool:
    """True iff an enabled ``agent_tools`` link exists for this agent + enabled tool (spec §6.2)."""
    tool = session.exec(select(Tool).where(Tool.name == tool_name)).first()
    if tool is None or not tool.enabled:
        return False
    link = session.exec(
        select(AgentTool).where(AgentTool.agent_id == agent_id, AgentTool.tool_id == tool.id)
    ).first()
    return link is not None and link.enabled


def _log_tracer(record: dict[str, Any]) -> None:
    logger.debug("broker_decision %s", record)


def broker(
    session: Session,
    agent_id: str,
    tool_name: str,
    args: dict[str, Any],
    ctx: RunContext,
    *,
    registry: dict[str, ToolSpec] | None = None,
    tracer: Tracer | None = None,
) -> BrokerVerdict:
    """Single entry point for all tool execution. Returns Allowed | Denied | ApprovalRequired.

    Checks run in the spec §6.2 order; the first failure returns ``Denied`` (and is traced).
    ``session`` is used only for the agent-permission read; ``registry`` and ``tracer`` are
    injectable (default: the private registry and a logging tracer).
    """
    reg = registry if registry is not None else _REGISTRY
    emit: Tracer = tracer if tracer is not None else _log_tracer

    def deny(reason: str) -> Denied:
        emit({"event_type": "broker_decision", "tool_name": tool_name, "verdict": "denied",
              "reason": reason})
        return Denied(reason)

    spec = reg.get(tool_name)
    if spec is None or not spec.enabled:
        return deny(f"unknown or disabled tool: {tool_name!r}")
    if not _agent_permitted(session, agent_id, tool_name):
        return deny(f"agent {agent_id!r} not permitted tool {tool_name!r}")
    if spec.kind != "read_only":
        return deny(f"tool {tool_name!r} is not read-only (kind={spec.kind!r})")
    try:
        validated = spec.args_model.model_validate(args)
    except ValidationError as exc:
        return deny(f"invalid args: {exc.error_count()} validation error(s)")
    if spec.access_scope not in ctx.scopes:
        return deny(f"scope {spec.access_scope!r} not permitted for this run")
    if spec.egress_checked:
        for value in _string_values(validated):
            blocked = _egress_check(value)
            if blocked:
                return deny(f"egress blocked: {blocked}")
    if ctx.cost_so_far_usd >= ctx.max_cost_per_run:
        return deny("per-run budget exhausted")

    result = spec.fn(validated)
    # TODO(scope): optional output redaction before returning to the model (spec §6.2).
    emit({"event_type": "broker_decision", "tool_name": tool_name, "verdict": "allowed",
          "reason": None})
    return Allowed(result)


def anthropic_tool_defs(registry: dict[str, ToolSpec] | None = None) -> list[dict[str, Any]]:
    """Anthropic tool schemas for the enabled read-only tools, derived from the private registry.

    Lets the loop advertise the available tools to the model. Execution still goes only through
    ``broker()`` — these are declarations, not callables.
    """
    reg = registry if registry is not None else _REGISTRY
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.args_model.model_json_schema(),
        }
        for spec in reg.values()
        if spec.enabled and spec.kind == "read_only"
    ]
