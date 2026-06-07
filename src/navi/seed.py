"""Seed the default agent, tools, and permission links (build spec §5 seed data).

Idempotent. Run against the configured DB with::

    uv run python -m navi.seed

Tests call ``seed_defaults`` against an in-memory SQLite session.
"""

from __future__ import annotations

from sqlmodel import Session, select

from navi.db import engine
from navi.models import Agent, AgentTool, Tool

DEFAULT_AGENT_NAME = "navi"
DEFAULT_TOOLS: list[dict[str, str]] = [
    {"name": "knowledge_base_search", "kind": "read_only", "access_scope": "kb"},
    {"name": "web_search", "kind": "read_only", "access_scope": "web"},
]


def seed_defaults(session: Session) -> Agent:
    """Ensure the MVP agent, the two read-only tools, and their links exist; return the agent."""
    agent = session.exec(select(Agent).where(Agent.name == DEFAULT_AGENT_NAME)).first()
    if agent is None:
        agent = Agent(name=DEFAULT_AGENT_NAME, role="workbench", model_profile="daily_driver")
        session.add(agent)
        session.commit()
        session.refresh(agent)

    for spec in DEFAULT_TOOLS:
        tool = session.exec(select(Tool).where(Tool.name == spec["name"])).first()
        if tool is None:
            tool = Tool(name=spec["name"], kind=spec["kind"], access_scope=spec["access_scope"])
            session.add(tool)
            session.commit()
            session.refresh(tool)
        link = session.exec(
            select(AgentTool).where(
                AgentTool.agent_id == agent.id, AgentTool.tool_id == tool.id
            )
        ).first()
        if link is None:
            session.add(AgentTool(agent_id=agent.id, tool_id=tool.id))
            session.commit()

    return agent


def main() -> None:
    with Session(engine) as session:
        agent = seed_defaults(session)
        print(f"Seeded agent {agent.name!r} ({agent.id}) + {len(DEFAULT_TOOLS)} read-only tools.")


if __name__ == "__main__":
    main()
