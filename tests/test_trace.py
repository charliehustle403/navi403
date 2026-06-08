"""Trace persistence + /runs/{id} tests (build spec §5, §6.8)."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import navi.models  # noqa: F401 — register tables
from _fakes import FakeModel, text_response, tool_use_response
from navi.api import app, get_model_client, get_session
from navi.loop import handle_request
from navi.models import Run, TraceEvent
from navi.seed import seed_defaults

_ANSWER_INLINE = json.dumps(
    {"route": "answer_inline", "confidence": 0.95, "risk": "low",
     "requires_approval": False, "reason": "general"}
)


def test_handle_request_persists_run_and_events(session: Session, offline_settings: object) -> None:
    seed_defaults(session)
    model = FakeModel([text_response(_ANSWER_INLINE, cost=0.002), text_response("Hi.", cost=0.01)])
    result = handle_request("hello", model=model, session=session)

    run = session.get(Run, result.run_id)
    assert run is not None
    assert run.status == "ok"
    assert run.ended_at is not None
    # cost includes BOTH the classifier (0.002) and the answer (0.01) — classifier accounting
    assert result.cost_usd >= 0.012 - 1e-9
    assert run.cost_usd == result.cost_usd

    events = session.exec(select(TraceEvent).where(TraceEvent.run_id == result.run_id)).all()
    types = [e.event_type for e in events]
    assert "route" in types
    assert types.count("model_call") == 2  # classifier + answer


def test_trace_records_broker_decision(session: Session, offline_settings: object) -> None:
    seed_defaults(session)
    model = FakeModel([
        text_response(_ANSWER_INLINE, cost=0.001),
        tool_use_response("knowledge_base_search", {"query": "naming"}, cost=0.001),
        text_response("done", cost=0.001),
    ])
    result = handle_request("look up role naming", model=model, session=session)
    events = session.exec(select(TraceEvent).where(TraceEvent.run_id == result.run_id)).all()
    verdicts = [e.verdict for e in events if e.event_type == "broker_decision"]
    assert "allowed" in verdicts


def test_runs_endpoint_and_404(offline_settings: object) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed_defaults(s)

    def override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    model = FakeModel([text_response(_ANSWER_INLINE), text_response("hello there")])
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_model_client] = lambda: model
    try:
        client = TestClient(app)
        run_id = client.post("/ask", json={"text": "hi"}).json()["run_id"]

        resp = client.get(f"/runs/{run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert body["status"] == "ok"
        assert any(e["event_type"] == "route" for e in body["events"])

        assert client.get("/runs/does-not-exist").status_code == 404
    finally:
        app.dependency_overrides.clear()
