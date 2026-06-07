"""Smoke test for /health. DB-agnostic so it passes with or without a live database."""

from __future__ import annotations

from fastapi.testclient import TestClient

from navi.api import app

client = TestClient(app)


def test_health_returns_ok_and_db_status() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # db is "ok" when Postgres is up, "error" when it is down — both are valid responses.
    assert body["db"] in {"ok", "error"}
