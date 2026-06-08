"""Eval suite — tool-permission (build spec §10): broker allows read-only, denies everything else.

Graded on the broker VERDICT (the path), against the real broker + registry over a seeded DB.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from navi.broker import ToolSpec, broker
from navi.contracts import Allowed, Denied, RunContext
from navi.models import AgentTool, Tool
from navi.seed import seed_defaults
from navi.tools import KnowledgeBaseSearchArgs

# (label, tool, args, scopes, agent, expected) — agent "self" = seeded agent, "ghost" = stranger
_CASES = [
    ("allow_kb", "knowledge_base_search", {"query": "naming"}, ["kb", "web"], "self", Allowed),
    ("allow_web", "web_search", {"query": "sap fiori"}, ["kb", "web"], "self", Allowed),
    ("allow_kb_kbscope", "knowledge_base_search", {"query": "sod"}, ["kb"], "self", Allowed),
    ("deny_unknown_tool", "send_email", {"query": "x"}, ["kb", "web"], "self", Denied),
    ("deny_web_out_of_scope", "web_search", {"query": "x"}, ["kb"], "self", Denied),
    ("deny_kb_out_of_scope", "knowledge_base_search", {"query": "x"}, ["web"], "self", Denied),
    ("deny_web_invalid_args", "web_search", {"nope": 1}, ["kb", "web"], "self", Denied),
    ("deny_kb_invalid_args", "knowledge_base_search", {}, ["kb", "web"], "self", Denied),
    ("deny_egress_exfil", "web_search", {"query": "x " + "A" * 60}, ["kb", "web"], "self", Denied),
    ("deny_ghost_agent", "web_search", {"query": "x"}, ["kb", "web"], "ghost", Denied),
]


@pytest.mark.parametrize(
    "label,tool,args,scopes,agent,expected", _CASES, ids=[c[0] for c in _CASES]
)
def test_tool_permission(
    label: str, tool: str, args: dict, scopes: list[str], agent: str, expected: type,
    session: Session, offline_settings: object,
) -> None:
    seeded = seed_defaults(session)
    agent_id = seeded.id if agent == "self" else "ghost-agent"
    ctx = RunContext(
        run_id="r", agent_id=agent_id, route="answer_inline",
        max_cost_per_run=1.0, scopes=scopes,
    )
    verdict = broker(session, agent_id, tool, args, ctx)
    assert isinstance(verdict, expected), f"{label}: got {verdict}"


def test_deny_disabled_tool(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    kb = session.exec(select(Tool).where(Tool.name == "knowledge_base_search")).first()
    assert kb is not None
    kb.enabled = False
    session.add(kb)
    session.commit()
    ctx = RunContext(run_id="r", agent_id=agent.id, route="x", max_cost_per_run=1.0, scopes=["kb"])
    verdict = broker(session, agent.id, "knowledge_base_search", {"query": "x"}, ctx)
    assert isinstance(verdict, Denied)


def test_deny_write_tool_kind(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
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
    ctx = RunContext(run_id="r", agent_id=agent.id, route="x", max_cost_per_run=1.0, scopes=["sap"])
    verdict = broker(session, agent.id, "delete_role", {"query": "x"}, ctx, registry=registry)
    assert isinstance(verdict, Denied)
    assert "not read-only" in verdict.reason
