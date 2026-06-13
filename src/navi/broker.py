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
    redact_output: bool = False  # scrub cred/PII-shaped spans from this tool's output (NAVI-14)


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
        redact_output=True,  # untrusted, attacker-controllable content — scrub before the model
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
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Email address. Conservative: requires a dotted TLD of 2+ alpha chars (skips bare @mentions).
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "email address"),
    # US SSN: NNN-NN-NNNN, separators (hyphen or space) REQUIRED so a bare 9-digit run is not
    # eaten (avoids colliding with order numbers, zip+4, 3-3-4 phone numbers).
    (re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"), "us ssn"),
]
# Fragmented-exfil heuristic: a secret split across many short tokens that each pass the
# per-token / cred checks. Floor of 32 hexlike chars mirrors the 128-bit secret-size intuition
# of the [0-9a-fA-F]{32,} cred pattern; the 0.5 ratio gate keeps word-dense research queries
# (alphabetic words dominate) well clear of the deny.
_MIN_HEXLIKE_CHARS = 32
_HEXLIKE_RATIO = 0.5
_HEXLIKE = re.compile(r"[0-9a-fA-F]")
_NON_SPACE = re.compile(r"\S")

# Verbatim-span echo (NAVI-13, spec §6.2): deny an outbound query that copies a long contiguous
# run of normalized tokens straight out of the run's own context (user text + prior KB outputs).
# Dual gate — a span must be both long in TOKENS and long in CHARS to deny, so legitimately quoted
# short titles/phrases stay Allowed and the NAVI-6 density gate keeps ownership of tiny-token runs.
_VERBATIM_MIN_TOKENS: int = 16  # contiguous shared normalized tokens to deny
_VERBATIM_MIN_CHARS: int = 80  # AND the shared run must span this many reconstructed chars


def _normalize_tokens(text: str) -> list[str]:
    """Casefold, collapse whitespace, split into tokens. Applied identically to query and corpus."""
    return text.casefold().split()


def _verbatim_span(value: str, corpus: str) -> int | None:
    """Return the token length of a long verbatim run shared by ``value`` and ``corpus``, else None.

    Pure/deterministic, no I/O. Builds the set of corpus token n-grams of length
    ``_VERBATIM_MIN_TOKENS`` (O(corpus tokens)); slides the same window over the query tokens
    (O(query tokens)). On the first shared n-gram it extends the contiguous match as far as it goes
    and returns its token length iff that run is ``>= _VERBATIM_MIN_TOKENS`` tokens AND its
    reconstructed (single-space-joined) char length is ``>= _VERBATIM_MIN_CHARS``. Returns only a
    count — never the raw span text. An empty corpus yields no n-grams ⇒ always None (pure no-op).
    """
    n = _VERBATIM_MIN_TOKENS
    q = _normalize_tokens(value)
    c = _normalize_tokens(corpus)
    if len(q) < n or len(c) < n:
        return None
    corpus_ngrams: set[tuple[str, ...]] = {tuple(c[i : i + n]) for i in range(len(c) - n + 1)}
    for i in range(len(q) - n + 1):
        if tuple(q[i : i + n]) not in corpus_ngrams:
            continue
        # Shared window at q[i:]; extend the contiguous match as far as the corpus contains it.
        for j in range(i + n, len(q) + 1):
            window = tuple(q[j - n : j])
            if window not in corpus_ngrams:
                break
        else:
            j = len(q) + 1
        end = j - 1  # last index (exclusive) whose trailing n-gram still matched the corpus
        run = q[i:end]
        if len(run) >= n and len(" ".join(run)) >= _VERBATIM_MIN_CHARS:
            return len(run)
    return None


def _egress_check(value: str, corpus: str = "") -> str | None:
    """Return a block reason if an outbound string looks like data exfiltration, else None.

    Deterministic guard — the broker does not trust the model to "surface, not obey". Covers
    over-length queries, long opaque tokens, credential-shaped tokens, PII-shaped tokens
    (email / US SSN), fragmented secret-shaped content (a secret spread across many short tokens
    via a hexlike-density gate), and — last — long verbatim spans copied out of the run's own
    context.

    Verbatim-span echo detection is DONE (NAVI-13): an exact normalized-token n-gram match
    (N=16 tokens / 80 chars) against ``corpus`` = the run's user text + prior knowledge_base_search
    outputs (assembled in ``run_loop`` onto ``RunContext.egress_context``). The branch runs last and
    no-ops when ``corpus`` is empty, so every corpus-free caller behaves exactly as before.
    # TODO(scope): fuzzy / semantic / edit-distance matching stays deferred (exact n-gram only);
    # prior web_search outputs are intentionally excluded from the corpus (external/public,
    # FP-prone); a first-class `verbatim` column on trace_events is deferred (reason = count only).
    """
    if len(value) > _MAX_QUERY_LEN:
        return f"value too long ({len(value)} > {_MAX_QUERY_LEN} chars)"
    for token in value.split():
        if len(token) >= _MAX_TOKEN_LEN:
            return f"contains a long opaque token ({len(token)} chars)"
    for pattern, label in _CRED_PATTERNS:
        if pattern.search(value):
            return f"matches credential pattern ({label})"
    for pattern, label in _PII_PATTERNS:
        if pattern.search(value):
            return f"matches PII pattern ({label})"
    hexlike = len(_HEXLIKE.findall(value))
    total = len(_NON_SPACE.findall(value))
    if hexlike >= _MIN_HEXLIKE_CHARS and total > 0 and hexlike / total >= _HEXLIKE_RATIO:
        return f"high-density secret-shaped content ({hexlike}/{total} chars)"
    if corpus:
        matched = _verbatim_span(value, corpus)
        if matched is not None:
            return f"verbatim span copied from context ({matched} tokens)"
    return None


# --- output redaction (inbound mirror of the egress check; spec §6.2) ---------------------
# Untrusted tool OUTPUT (web_search results) can carry an indirect prompt-injection: a planted
# secret/PII span the model might echo back outbound. Before such output re-enters the model
# context we scrub the cred/PII-shaped spans in place. Unlike the egress check (which denies the
# whole call), output is redacted not denied — a fetched page legitimately containing a hex hash
# or a footer email must not break legitimate research. Only the substitutable span detectors
# (_CRED_PATTERNS + _PII_PATTERNS) apply; the whole-string density/length gates stay input-only.


def _redact(value: str) -> tuple[str, list[str]]:
    """Replace credential/PII-shaped spans with ``[REDACTED:<label>]``; return (clean, labels_hit).

    Pure, deterministic, no I/O. Reuses the NAVI-6 ``_CRED_PATTERNS`` + ``_PII_PATTERNS`` (no regex
    duplication), substituting in fixed pattern order. The placeholder is a constant string holding
    no captured content. ``labels_hit`` carries only the non-sensitive category names that matched.
    """
    clean = value
    labels: list[str] = []
    for pattern, label in (*_CRED_PATTERNS, *_PII_PATTERNS):
        clean, count = pattern.subn(f"[REDACTED:{label}]", clean)
        if count:
            labels.append(label)
    return clean, labels


def _redact_result(result: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Walk a tool-result dict, redacting its string values; return a NEW dict + all labels hit.

    Builds a new structure (never mutates the input): ``str`` → ``_redact``, ``dict`` → recurse,
    ``list`` → map over items, other scalars unchanged. Covers nested ``results[]`` snippet/url
    spans. Labels accumulate in traversal order (stable). Pure, deterministic, no I/O.
    """
    labels: list[str] = []

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            clean, hit = _redact(node)
            labels.extend(hit)
            return clean
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    redacted: dict[str, Any] = walk(result)
    return redacted, labels


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
        # NAVI-13: the corpus is the run's own sensitive text (user message + prior KB outputs),
        # carried on RunContext so broker()'s public signature stays stable. Empty ⇒ verbatim no-op.
        corpus = "\n".join(ctx.egress_context)
        for value in _string_values(validated):
            blocked = _egress_check(value, corpus)
            if blocked:
                return deny(f"egress blocked: {blocked}")
    # NAVI-15: per-run, per-tool call cap (DoS/cost backstop). Read-only here — the loop increments
    # ctx.tool_calls on Allowed. None ⇒ feature off. Placed after the security checks so a malicious
    # call is denied for the security reason, not masked as a rate limit. ``>=`` counts executed
    # calls: cap=2 lets calls #1/#2 through (counts 0,1) and denies #3 (count 2).
    cap = ctx.max_calls_per_tool
    if cap is not None and ctx.tool_calls.get(tool_name, 0) >= cap:
        return deny(f"tool call rate limit exhausted ({tool_name!r}: {cap} per run)")
    if ctx.cost_so_far_usd >= ctx.max_cost_per_run:
        return deny("per-run budget exhausted")

    result = spec.fn(validated)
    # Output redaction (spec §6.2): scrub cred/PII-shaped spans from untrusted tool output before
    # it re-enters the model context — done (NAVI-14). For redact_output=False tools this is a
    # no-op, so behavior is byte-for-byte identical to before.
    # TODO(scope): first-class `redacted` column on trace_events (migration) and verbatim-span echo
    # detection on output remain deferred follow-ups.
    redacted_labels: list[str] = []
    if spec.redact_output:
        result, redacted_labels = _redact_result(result)
    emit({"event_type": "broker_decision", "tool_name": tool_name, "verdict": "allowed",
          "reason": None, "redacted": redacted_labels})
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
