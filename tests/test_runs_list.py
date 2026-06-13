"""GET /runs list endpoint tests (NAVI-16): ordering, token aggregation, limit validation."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import navi.models  # noqa: F401 — register tables
from navi.api import app, get_session
from navi.models import Run, TraceEvent

_SUMMARY_FIELDS = {
    "run_id", "agent_id", "route", "status", "cost_usd",
    "started_at", "ended_at", "tokens_in", "tokens_out",
}


@pytest.fixture
def api() -> Iterator[tuple[TestClient, Session]]:
    """TestClient over the app with an in-memory DB + a session for seeding that same DB."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    try:
        with Session(engine) as seed_session:
            yield TestClient(app), seed_session
    finally:
        app.dependency_overrides.clear()


def _add_run(
    session: Session,
    *,
    started_at: datetime,
    status: str = "ok",
    route: str | None = "answer_inline",
    cost_usd: float = 0.001,
    ended_at: datetime | None = None,
) -> Run:
    # Naive datetimes on purpose: SQLite's DATETIME drops tzinfo, so naive values round-trip
    # identically and make the isoformat assertions exact.
    run = Run(route=route, status=status, started_at=started_at, cost_usd=cost_usd,
              ended_at=ended_at)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def test_list_runs_empty_db_returns_empty_list(api: tuple[TestClient, Session]) -> None:
    client, _ = api
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_runs_newest_first_with_fields(api: tuple[TestClient, Session]) -> None:
    client, session = api
    oldest = _add_run(session, started_at=datetime(2026, 1, 1, 12, 0, 0))
    middle = _add_run(session, started_at=datetime(2026, 1, 1, 12, 1, 0))
    newest = _add_run(
        session,
        started_at=datetime(2026, 1, 1, 12, 2, 0),
        ended_at=datetime(2026, 1, 1, 12, 2, 5),
        status="ok",
        route="research",
        cost_usd=0.025,
    )

    resp = client.get("/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert [item["run_id"] for item in body] == [newest.id, middle.id, oldest.id]
    for item in body:
        assert set(item.keys()) == _SUMMARY_FIELDS

    head = body[0]
    assert head["agent_id"] is None
    assert head["route"] == "research"
    assert head["status"] == "ok"
    assert head["cost_usd"] == 0.025
    assert head["started_at"] == datetime(2026, 1, 1, 12, 2, 0).isoformat()
    assert head["ended_at"] == datetime(2026, 1, 1, 12, 2, 5).isoformat()
    assert head["tokens_in"] is None
    assert head["tokens_out"] is None


def test_list_runs_aggregates_tokens(api: tuple[TestClient, Session]) -> None:
    client, session = api
    with_tokens = _add_run(session, started_at=datetime(2026, 1, 1, 12, 0, 0))
    without_tokens = _add_run(session, started_at=datetime(2026, 1, 1, 12, 1, 0))
    session.add(TraceEvent(run_id=with_tokens.id, event_type="model_call",
                           tokens_in=10, tokens_out=5))
    session.add(TraceEvent(run_id=with_tokens.id, event_type="model_call",
                           tokens_in=20, tokens_out=7))
    session.commit()

    by_id = {item["run_id"]: item for item in client.get("/runs").json()}
    assert by_id[with_tokens.id]["tokens_in"] == 30
    assert by_id[with_tokens.id]["tokens_out"] == 12
    assert by_id[without_tokens.id]["tokens_in"] is None
    assert by_id[without_tokens.id]["tokens_out"] is None


def test_list_runs_limit_respected(api: tuple[TestClient, Session]) -> None:
    client, session = api
    _add_run(session, started_at=datetime(2026, 1, 1, 12, 0, 0))
    middle = _add_run(session, started_at=datetime(2026, 1, 1, 12, 1, 0))
    newest = _add_run(session, started_at=datetime(2026, 1, 1, 12, 2, 0))

    resp = client.get("/runs", params={"limit": 2})
    assert resp.status_code == 200
    assert [item["run_id"] for item in resp.json()] == [newest.id, middle.id]


def test_list_runs_limit_validation(api: tuple[TestClient, Session]) -> None:
    client, session = api
    _add_run(session, started_at=datetime(2026, 1, 1, 12, 0, 0))

    assert client.get("/runs", params={"limit": 0}).status_code == 422
    assert client.get("/runs", params={"limit": 201}).status_code == 422
    resp = client.get("/runs")  # no param -> default 50
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_run_detail_endpoint_unchanged(api: tuple[TestClient, Session]) -> None:
    """GET /runs and GET /runs/{id} coexist — the list contains the id the detail serves."""
    client, session = api
    run = _add_run(session, started_at=datetime(2026, 1, 1, 12, 0, 0))

    listed = client.get("/runs").json()
    assert [item["run_id"] for item in listed] == [run.id]

    detail = client.get(f"/runs/{run.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["run_id"] == run.id
    assert body["events"] == []
