"""SQLModel tables — the full build-spec §5 data model.

Several columns are intentionally present but unused in the read-only MVP (additive design,
spec §12): ``tools.requires_approval``, ``agents.risk_default``, the whole ``approvals`` table,
and ``memories.expires_at`` (column-only; no revalidation actor yet). Allowed values for the
string status/kind/enum-ish columns are documented inline; they are stored as plain strings to
keep Alembic migrations simple (no Postgres ENUM types) per the spec's "simpler/safer" rule.

IDs are uuid4 hex strings so ``runs.id`` matches ``StructuredResult.run_id: str`` (spec §7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Agent(SQLModel, table=True):
    __tablename__ = "agents"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    role: str
    model_profile: str
    risk_default: str = "low"  # unused in MVP (additive)
    enabled: bool = True


class Tool(SQLModel, table=True):
    __tablename__ = "tools"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(unique=True, index=True)
    kind: str  # read_only | write  (MVP: read_only only)
    access_scope: str
    requires_approval: bool = False  # unused in MVP (additive)
    enabled: bool = True


class AgentTool(SQLModel, table=True):
    """Permission join: which agent may use which tool (spec §5 / §6.2).

    The broker's "agent permitted this tool" check reads from here. MVP seed: the one agent
    linked to both read-only tools.
    """

    __tablename__ = "agent_tools"

    agent_id: str = Field(foreign_key="agents.id", primary_key=True)
    tool_id: str = Field(foreign_key="tools.id", primary_key=True)
    enabled: bool = True


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(default_factory=_uuid, primary_key=True)
    parent_run_id: str | None = Field(default=None, foreign_key="runs.id")
    agent_id: str | None = Field(default=None, foreign_key="agents.id")
    route: str | None = None
    status: str = "open"  # open | ok | truncated | refused | error
    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
    cost_usd: float = 0.0


class TraceEvent(SQLModel, table=True):
    """One event in a run's trace (spec §5, fattened in v1.1).

    Non-sensitive columns (tool_name/route/verdict/tokens) are stored in clear so traces are
    debuggable and the health-signal queries work; only ``payload_hash`` hashes args/outputs.
    """

    __tablename__ = "trace_events"

    id: str = Field(default_factory=_uuid, primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    event_type: str  # model_call | tool_call | broker_decision | route | error
    tool_name: str | None = None
    route: str | None = None
    verdict: str | None = None  # allowed | denied | approval_required
    tokens_in: int | None = None
    tokens_out: int | None = None
    payload_hash: str | None = None  # hash of args/outputs, never raw sensitive content
    created_at: datetime = Field(default_factory=_now)


class Approval(SQLModel, table=True):
    """Interface-only in the MVP — no write tools trigger it (spec §5)."""

    __tablename__ = "approvals"

    id: str = Field(default_factory=_uuid, primary_key=True)
    run_id: str = Field(foreign_key="runs.id")
    action_type: str
    status: str = "pending"  # pending | approved | denied | expired
    requested_at: datetime = Field(default_factory=_now)
    decided_at: datetime | None = None


class MemoryCandidate(SQLModel, table=True):
    __tablename__ = "memory_candidates"

    id: str = Field(default_factory=_uuid, primary_key=True)
    source: str
    source_trust: str  # trusted | untrusted
    value_hash: str
    classification: str  # preference | world_fact | decision | sensitive
    status: str = "pending"  # pending | accepted | rejected
    created_at: datetime = Field(default_factory=_now)


class Memory(SQLModel, table=True):
    __tablename__ = "memories"

    id: str = Field(default_factory=_uuid, primary_key=True)
    value: str
    source: str
    source_trust: str
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=_now)
    expires_at: datetime | None = None  # column-only in MVP (no revalidation actor yet)
    may_influence_actions: bool = False
