"""Broker tests — every verdict branch (build spec §6.2, §10 tool-permission + egress evals).

Hermetic: in-memory SQLite ``session`` + ``offline_settings`` (no Docker, no network).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from navi.broker import ToolSpec, _egress_check, _redact, _redact_result, broker
from navi.contracts import Allowed, Denied, RunContext
from navi.models import AgentTool, Tool
from navi.seed import seed_defaults
from navi.tools import KnowledgeBaseSearchArgs, WebSearchArgs


def _ctx(agent_id: str, **kw: Any) -> RunContext:
    base: dict[str, Any] = {
        "run_id": "run-1",
        "agent_id": agent_id,
        "max_cost_per_run": 0.50,
        "scopes": ["kb", "web"],
    }
    base.update(kw)
    return RunContext(**base)


# --- allow paths --------------------------------------------------------------------------


def test_allow_knowledge_base_search(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "knowledge_base_search", {"query": "naming"}, _ctx(agent.id)
    )
    assert isinstance(verdict, Allowed)
    assert verdict.result["status"] == "ok"
    assert verdict.result["results"], "seeded KB should match 'naming'"


def test_allow_web_search_degrades_to_unavailable(
    session: Session, offline_settings: object
) -> None:
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "web_search", {"query": "sap fiori catalog"}, _ctx(agent.id)
    )
    assert isinstance(verdict, Allowed)
    assert verdict.result["status"] == "unavailable"  # no key configured, no network


# --- deny paths (each broker check, in order) ---------------------------------------------


def test_deny_unknown_or_disabled_tool(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    # registry-level "disabled" (step 1)
    disabled = {
        "x": ToolSpec(
            name="x", args_model=KnowledgeBaseSearchArgs, fn=lambda a: {}, kind="read_only",
            access_scope="kb", egress_checked=False, enabled=False,
        )
    }
    verdict = broker(session, agent.id, "x", {"query": "q"}, _ctx(agent.id), registry=disabled)
    assert isinstance(verdict, Denied)
    # unknown tool entirely
    verdict2 = broker(session, agent.id, "nope", {"query": "q"}, _ctx(agent.id))
    assert isinstance(verdict2, Denied)
    assert "unknown" in verdict2.reason


def test_deny_agent_not_permitted(session: Session, offline_settings: object) -> None:
    seed_defaults(session)  # seeds the "navi" agent, but we call as a stranger
    verdict = broker(session, "ghost-agent", "web_search", {"query": "q"}, _ctx("ghost-agent"))
    assert isinstance(verdict, Denied)
    assert "not permitted" in verdict.reason


def test_deny_write_tool_kind(session: Session, offline_settings: object) -> None:
    """The approval path exists but no write tool ships — a write tool must be refused (§2/§6.2)."""
    agent = seed_defaults(session)
    # Seed a write tool + permission link so the permission check passes and the KIND check fires.
    write_tool = Tool(name="delete_role", kind="write", access_scope="sap")
    session.add(write_tool)
    session.commit()
    session.refresh(write_tool)
    session.add(AgentTool(agent_id=agent.id, tool_id=write_tool.id))
    session.commit()
    registry = {
        "delete_role": ToolSpec(
            name="delete_role", args_model=KnowledgeBaseSearchArgs, fn=lambda a: {}, kind="write",
            access_scope="sap", egress_checked=False,
        )
    }
    verdict = broker(
        session, agent.id, "delete_role", {"query": "q"}, _ctx(agent.id, scopes=["sap"]),
        registry=registry,
    )
    assert isinstance(verdict, Denied)
    assert "not read-only" in verdict.reason


def test_deny_invalid_args(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    verdict = broker(session, agent.id, "web_search", {"wrong_field": 1}, _ctx(agent.id))
    assert isinstance(verdict, Denied)
    assert "invalid args" in verdict.reason


def test_deny_scope_not_permitted(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "web_search", {"query": "q"}, _ctx(agent.id, scopes=["kb"])
    )
    assert isinstance(verdict, Denied)
    assert "scope" in verdict.reason


def test_deny_budget_exhausted(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "knowledge_base_search", {"query": "q"},
        _ctx(agent.id, cost_so_far_usd=0.50, max_cost_per_run=0.50),
    )
    assert isinstance(verdict, Denied)
    assert "budget" in verdict.reason


# --- egress / exfiltration (the v1.1 backstop, §6.2 + §10) --------------------------------


def test_deny_egress_long_opaque_token(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    exfil = "best pizza near me " + "A" * 60  # a long opaque blob smuggled into the query
    verdict = broker(session, agent.id, "web_search", {"query": exfil}, _ctx(agent.id))
    assert isinstance(verdict, Denied)
    assert "egress" in verdict.reason


def test_deny_egress_credential_pattern(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "web_search",
        {"query": "look up sk-ABCDEFGHIJKLMNOPQRSTUV please"}, _ctx(agent.id),
    )
    assert isinstance(verdict, Denied)
    assert "egress" in verdict.reason


def test_deny_egress_pii_email(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "web_search",
        {"query": "contact me at jane.doe@example.com about the role"}, _ctx(agent.id),
    )
    assert isinstance(verdict, Denied)
    assert "egress" in verdict.reason


def test_deny_egress_pii_ssn(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "web_search",
        {"query": "my ssn is 123-45-6789 please verify"}, _ctx(agent.id),
    )
    assert isinstance(verdict, Denied)
    assert "egress" in verdict.reason


def test_deny_egress_fragmented_hex(session: Session, offline_settings: object) -> None:
    """A secret spread across short tokens (each passes the per-token/cred checks) is caught."""
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "web_search",
        {"query": "hash de ad be ef de ad be ef de ad be ef de ad be ef"}, _ctx(agent.id),
    )
    assert isinstance(verdict, Denied)
    assert "egress" in verdict.reason


def test_allow_egress_long_research_query(session: Session, offline_settings: object) -> None:
    """A long word-dense research query must not trip the egress backstop (regression guard)."""
    agent = seed_defaults(session)
    query = (
        "compare SAP S/4HANA Fiori catalog vs business role authorization concept best "
        "practices for derived roles and segregation of duties 2025"
    )
    verdict = broker(session, agent.id, "web_search", {"query": query}, _ctx(agent.id))
    assert isinstance(verdict, Allowed)


# --- egress: verbatim-span-from-context echo (NAVI-13) ------------------------------------
#
# A long contiguous run of normalized tokens copied straight out of the run's own context
# (user text + prior KB outputs, carried on RunContext.egress_context) is denied. Short legit
# quotes and unrelated queries stay Allowed; with no corpus the branch is a pure no-op.

_SENSITIVE_SPAN = (
    "the internal migration runbook requires disabling the legacy single role derivation job "
    "before the cutover weekend to avoid orphaned authorization profiles in production"
)


def test_deny_egress_verbatim_span_from_context(
    session: Session, offline_settings: object
) -> None:
    agent = seed_defaults(session)
    query = f"please search the web for: {_SENSITIVE_SPAN} and tell me more"
    records: list[dict[str, Any]] = []
    verdict = broker(
        session, agent.id, "web_search", {"query": query},
        _ctx(agent.id, egress_context=(_SENSITIVE_SPAN,)), tracer=records.append,
    )
    assert isinstance(verdict, Denied)
    assert "egress" in verdict.reason
    # The raw span must never reach the trace record — only a token count is carried.
    assert _SENSITIVE_SPAN not in repr(records[-1])


def test_allow_egress_short_quote_from_context(
    session: Session, offline_settings: object
) -> None:
    agent = seed_defaults(session)
    # KB-style doc title quoted into a follow-up search — a few tokens, well under the 16/80 gate.
    title = "Derived Role Design Guide"
    verdict = broker(
        session, agent.id, "web_search",
        {"query": f'best practices for "{title}" in S/4HANA 2025'},
        _ctx(agent.id, egress_context=(f"document: {title} — internal reference",)),
    )
    assert isinstance(verdict, Allowed)


def test_allow_egress_unrelated_query_with_context(
    session: Session, offline_settings: object
) -> None:
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "web_search",
        {"query": "current SAP Fiori catalog versioning best practices"},
        _ctx(agent.id, egress_context=(_SENSITIVE_SPAN,)),
    )
    assert isinstance(verdict, Allowed)


def test_egress_no_corpus_behaves_as_today(session: Session, offline_settings: object) -> None:
    # Default egress_context=() — a long natural query that was Allowed before stays Allowed; the
    # new branch adds zero behavior when there is no corpus.
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "web_search", {"query": _SENSITIVE_SPAN}, _ctx(agent.id)
    )
    assert isinstance(verdict, Allowed)


def test_egress_check_pure_deterministic_verbatim() -> None:
    value = f"lookup {_SENSITIVE_SPAN} online"
    corpus = _SENSITIVE_SPAN
    first = _egress_check(value, corpus)
    second = _egress_check(value, corpus)
    assert first == second
    assert first is not None and "verbatim" in first
    # Inputs are not mutated.
    assert value == f"lookup {_SENSITIVE_SPAN} online"
    assert corpus == _SENSITIVE_SPAN
    # Empty corpus is a no-op on the same value.
    assert _egress_check(value, "") is None


def test_kb_search_not_egress_checked(session: Session, offline_settings: object) -> None:
    """A long token is fine for the local KB tool — egress applies only to outbound tools."""
    agent = seed_defaults(session)
    verdict = broker(
        session, agent.id, "knowledge_base_search", {"query": "A" * 60}, _ctx(agent.id)
    )
    assert isinstance(verdict, Allowed)


# --- tracer hook --------------------------------------------------------------------------


def test_tracer_receives_decision(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    records: list[dict[str, Any]] = []
    broker(
        session, agent.id, "web_search", {"query": "q"}, _ctx(agent.id), tracer=records.append
    )
    assert records and records[-1]["event_type"] == "broker_decision"
    assert records[-1]["verdict"] == "allowed"


# --- output redaction (NAVI-14) -----------------------------------------------------------
#
# A fake tool registered under the seeded "web_search" name (so the agent-permission + scope
# checks pass) with a custom ``fn`` returning attacker-controllable content. The redact_output
# flag is what drives the new behavior — web_search=True, knowledge_base_search=False.


def _redacting_registry(fn: Any, *, redact_output: bool = True) -> dict[str, ToolSpec]:
    return {
        "web_search": ToolSpec(
            name="web_search", args_model=WebSearchArgs, fn=fn, kind="read_only",
            access_scope="web", egress_checked=True, redact_output=redact_output,
        )
    }


def test_redact_output_credential_span(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    secret = "sk-ABCDEFGHIJKLMNOPQRSTUV"
    reg = _redacting_registry(
        lambda a: {"status": "ok", "results": [{"url": "http://x", "snippet": f"key is {secret}"}]}
    )
    verdict = broker(session, agent.id, "web_search", {"query": "q"}, _ctx(agent.id), registry=reg)
    assert isinstance(verdict, Allowed)
    snippet = verdict.result["results"][0]["snippet"]
    assert "[REDACTED:openai-style key]" in snippet
    assert secret not in snippet


def test_redact_output_pii_email(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    snippet_in = "mail jane.doe@example.com please"
    reg = _redacting_registry(
        lambda a: {"status": "ok", "results": [{"url": "http://x", "snippet": snippet_in}]}
    )
    verdict = broker(session, agent.id, "web_search", {"query": "q"}, _ctx(agent.id), registry=reg)
    assert isinstance(verdict, Allowed)
    snippet = verdict.result["results"][0]["snippet"]
    assert "[REDACTED:email address]" in snippet
    assert "jane.doe@example.com" not in snippet


def test_redact_output_multiple_spans(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    secret = "sk-ABCDEFGHIJKLMNOPQRSTUV"
    ssn = "123-45-6789"
    reg = _redacting_registry(
        lambda a: {
            "status": "ok",
            "results": [
                {"url": "http://x", "snippet": f"creds {secret}"},
                {"url": "http://y", "snippet": f"ssn {ssn} here"},
            ],
        }
    )
    records: list[dict[str, Any]] = []
    verdict = broker(
        session, agent.id, "web_search", {"query": "q"}, _ctx(agent.id),
        registry=reg, tracer=records.append,
    )
    assert isinstance(verdict, Allowed)
    assert "[REDACTED:openai-style key]" in verdict.result["results"][0]["snippet"]
    assert "[REDACTED:us ssn]" in verdict.result["results"][1]["snippet"]
    labels = records[-1]["redacted"]
    assert "openai-style key" in labels
    assert "us ssn" in labels
    assert secret not in repr(records[-1])
    assert ssn not in repr(records[-1])


def test_redact_traced_labels_not_raw(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    secret = "sk-ABCDEFGHIJKLMNOPQRSTUV"
    reg = _redacting_registry(
        lambda a: {"status": "ok", "results": [{"url": "http://x", "snippet": f"key {secret}"}]}
    )
    records: list[dict[str, Any]] = []
    broker(
        session, agent.id, "web_search", {"query": "q"}, _ctx(agent.id),
        registry=reg, tracer=records.append,
    )
    assert records[-1]["redacted"] == ["openai-style key"]
    assert secret not in repr(records[-1])


def test_redact_clean_output_unchanged(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    clean = {"status": "ok", "results": [{"url": "http://x", "snippet": "best practices"}]}
    records: list[dict[str, Any]] = []
    verdict = broker(
        session, agent.id, "web_search", {"query": "q"}, _ctx(agent.id),
        registry=_redacting_registry(lambda a: clean), tracer=records.append,
    )
    assert isinstance(verdict, Allowed)
    assert verdict.result == clean
    assert records[-1]["redacted"] == []


def test_kb_output_not_redacted(session: Session, offline_settings: object) -> None:
    """knowledge_base_search has redact_output=False — a token-shaped span passes through intact."""
    agent = seed_defaults(session)
    secret = "sk-ABCDEFGHIJKLMNOPQRSTUV"
    out = {"status": "ok", "results": [{"source": "kb.md", "snippet": f"example {secret}"}]}
    reg = {
        "knowledge_base_search": ToolSpec(
            name="knowledge_base_search", args_model=KnowledgeBaseSearchArgs,
            fn=lambda a: out, kind="read_only", access_scope="kb",
            egress_checked=False,  # redact_output defaults to False
        )
    }
    verdict = broker(
        session, agent.id, "knowledge_base_search", {"query": "q"}, _ctx(agent.id), registry=reg
    )
    assert isinstance(verdict, Allowed)
    assert secret in verdict.result["results"][0]["snippet"]


def test_input_egress_unaffected(session: Session, offline_settings: object) -> None:
    """Output redaction runs only after deny checks pass — an egress-denied call never redacts."""
    agent = seed_defaults(session)
    called: list[bool] = []

    def fn(a: WebSearchArgs) -> dict[str, Any]:
        called.append(True)
        return {"status": "ok", "results": []}

    verdict = broker(
        session, agent.id, "web_search",
        {"query": "leak sk-ABCDEFGHIJKLMNOPQRSTUV now"}, _ctx(agent.id),
        registry=_redacting_registry(fn),
    )
    assert isinstance(verdict, Denied)
    assert "egress" in verdict.reason
    assert not called, "tool fn (and thus redaction) must not run on an egress-denied call"


def test_redact_is_pure_and_deterministic() -> None:
    value = "key sk-ABCDEFGHIJKLMNOPQRSTUV and mail jane.doe@example.com"
    first = _redact(value)
    second = _redact(value)
    assert first == second
    assert value == "key sk-ABCDEFGHIJKLMNOPQRSTUV and mail jane.doe@example.com"  # not mutated

    src = {"status": "ok", "results": [{"snippet": "sk-ABCDEFGHIJKLMNOPQRSTUV"}]}
    src_copy = {"status": "ok", "results": [{"snippet": "sk-ABCDEFGHIJKLMNOPQRSTUV"}]}
    out, labels = _redact_result(src)
    assert out is not src
    assert src == src_copy  # input left unchanged
    assert labels == ["openai-style key"]
    assert "[REDACTED:openai-style key]" in out["results"][0]["snippet"]


def test_redact_no_false_positive_on_research_prose() -> None:
    prose = (
        "compare SAP S/4HANA Fiori catalog vs business role authorization concept best "
        "practices for derived roles and segregation of duties 2025"
    )
    clean, labels = _redact(prose)
    assert clean == prose
    assert labels == []
