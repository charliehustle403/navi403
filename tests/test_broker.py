"""Broker tests — every verdict branch (build spec §6.2, §10 tool-permission + egress evals).

Hermetic: in-memory SQLite ``session`` + ``offline_settings`` (no Docker, no network).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from navi.broker import ToolSpec, broker
from navi.contracts import Allowed, Denied, RunContext
from navi.models import AgentTool, Tool
from navi.seed import seed_defaults
from navi.tools import KnowledgeBaseSearchArgs


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
