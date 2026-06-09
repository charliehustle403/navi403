"""Trace persistence (build spec §5, §6.8).

Every run writes a ``runs`` row and ``trace_events`` for each model call, broker decision, route,
and error. Sensitive payloads (args/outputs/text) are stored only as sha256 hashes; non-sensitive
fields (tool name, route, verdict, token counts) are kept in clear so traces are debuggable and the
health-signal queries work. ``RunRecorder`` also accumulates the run's cost (incl. the routing
classifier call), so cost accounting is complete.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlmodel import Session, col, select

from navi.contracts import RouteDecision, RunTrace, TraceEventView
from navi.models import Run, TraceEvent

if TYPE_CHECKING:
    from navi.model_client import ModelResponse


def _hash(payload: Any) -> str:
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def open_run(session: Session, agent_id: str, route: str | None = None) -> Run:
    run = Run(agent_id=agent_id, route=route, status="open")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def close_run(session: Session, run: Run, *, status: str, cost_usd: float) -> None:
    run.status = status
    run.cost_usd = round(cost_usd, 6)
    run.ended_at = datetime.now(UTC)
    session.add(run)
    session.commit()


class RunRecorder:
    """Writes trace_events for a run and accumulates its cost."""

    def __init__(self, session: Session, run_id: str) -> None:
        self.session = session
        self.run_id = run_id
        self.cost = 0.0

    def _add(self, event_type: str, **fields: Any) -> None:
        self.session.add(TraceEvent(run_id=self.run_id, event_type=event_type, **fields))
        self.session.commit()

    def model_call(self, resp: ModelResponse) -> None:
        self.cost += resp.cost_usd
        self._add(
            "model_call",
            tokens_in=resp.input_tokens,
            tokens_out=resp.output_tokens,
            payload_hash=_hash(resp.text) if resp.text else None,
        )

    def broker_decision(self, record: dict[str, Any]) -> None:
        """Adapter for the broker's ``tracer`` callable (spec §6.2).

        When the broker redacted cred/PII spans from a tool's output (NAVI-14), the non-sensitive
        labels are folded into ``payload_hash`` — labels only, never the raw matched content.
        # TODO(scope): a first-class ``redacted`` column on trace_events (migration) is deferred.
        """
        reason = record.get("reason")
        redacted = record.get("redacted")
        if redacted:
            payload_hash: str | None = _hash({"redacted": redacted})
        elif reason:
            payload_hash = _hash(reason)
        else:
            payload_hash = None
        self._add(
            "broker_decision",
            tool_name=record.get("tool_name"),
            verdict=record.get("verdict"),
            payload_hash=payload_hash,
        )

    def route_event(self, dispatched: str, decision: RouteDecision) -> None:
        self._add("route", route=dispatched, payload_hash=_hash(decision.model_dump()))

    def error(self, message: str) -> None:
        self._add("error", payload_hash=_hash(message))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def get_run_trace(session: Session, run_id: str) -> RunTrace | None:
    run = session.get(Run, run_id)
    if run is None:
        return None
    events = session.exec(
        select(TraceEvent).where(TraceEvent.run_id == run_id).order_by(col(TraceEvent.created_at))
    ).all()
    return RunTrace(
        run_id=run.id,
        agent_id=run.agent_id,
        route=run.route,
        status=run.status,
        cost_usd=run.cost_usd,
        started_at=run.started_at.isoformat(),
        ended_at=_iso(run.ended_at),
        events=[
            TraceEventView(
                event_type=e.event_type,
                tool_name=e.tool_name,
                route=e.route,
                verdict=e.verdict,
                tokens_in=e.tokens_in,
                tokens_out=e.tokens_out,
                payload_hash=e.payload_hash,
                created_at=e.created_at.isoformat(),
            )
            for e in events
        ],
    )
