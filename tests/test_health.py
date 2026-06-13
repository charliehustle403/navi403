"""Tests for /health and the DB probe — fully Postgres-independent (NAVI-21).

``/health`` runs its DB probe on the injected session, so overriding ``get_session`` with an
in-memory SQLite session lets the suite pass in seconds with no live database. In production the
real engine is used and ``db`` reports ``"error"`` (not a hang — the engine has a connect timeout)
when Postgres is unreachable.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import navi.models  # noqa: F401 — registers tables on SQLModel.metadata
from navi.api import app, get_session
from navi.db import check_db


def _client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health_returns_ok_with_sqlite() -> None:
    # No Postgres required: the probe runs SELECT 1 against the overridden in-memory session.
    for client in _client():
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"


def test_check_db_false_on_error() -> None:
    # The error branch (prod's "db": "error") stays covered: a failing SELECT 1 → False, no raise.
    broken = MagicMock()
    broken.execute.side_effect = RuntimeError("connection lost")
    assert check_db(cast(Session, broken)) is False
