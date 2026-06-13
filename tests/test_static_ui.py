"""SPA static mount tests (NAVI-16): mount_spa guard + API route precedence over the mount.

The import-time ``mount_spa(app)`` call in ``navi.api`` mounts the real ``web/dist`` when it
exists (NAVI-17 builds it on dev machines) and no-ops otherwise. Each test forces a known
state by unmounting first, so the suite passes with or without a local UI build.

Tests that hit ``/health`` override ``get_session`` with in-memory SQLite so the DB probe is
instant and needs no live Postgres (NAVI-21).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import navi.models  # noqa: F401 — registers tables on SQLModel.metadata
from navi.api import app, get_session, mount_spa


def _spa_route_names() -> list[str]:
    return [
        name
        for r in app.router.routes
        if (name := getattr(r, "name", None)) == "spa"
    ]


def _unmount_spa() -> None:
    app.router.routes[:] = [
        r for r in app.router.routes if getattr(r, "name", None) != "spa"
    ]


def _use_sqlite() -> None:
    """Point the app's DB dependency at a fresh in-memory SQLite (no Postgres for /health)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override


def test_app_boots_and_serves_api_without_web_dist() -> None:
    # Simulate the "no UI build" state (fresh clone): '/' unmounted, the API still answers.
    _unmount_spa()
    _use_sqlite()
    try:
        assert _spa_route_names() == []
        client = TestClient(app)
        assert client.get("/").status_code == 404
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    finally:
        app.dependency_overrides.clear()


def test_mount_spa_missing_dir_is_noop(tmp_path: Path) -> None:
    _unmount_spa()
    assert mount_spa(app, str(tmp_path / "nope")) is False
    assert _spa_route_names() == []


def test_mount_spa_serves_index_and_api_takes_precedence(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>navi-ui</html>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('navi');", encoding="utf-8")

    _unmount_spa()
    _use_sqlite()
    try:
        assert mount_spa(app, str(tmp_path)) is True
        client = TestClient(app)

        root = client.get("/")
        assert root.status_code == 200
        assert root.headers["content-type"].startswith("text/html")
        assert "navi-ui" in root.text

        assert client.get("/assets/app.js").status_code == 200

        # API routes registered before the mount still win over the '/' catch-all.
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
    finally:
        # The app is module-global; remove the test mount + override so other tests see clean state.
        _unmount_spa()
        app.dependency_overrides.clear()
    assert _spa_route_names() == []
