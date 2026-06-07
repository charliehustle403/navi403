"""Shared test fixtures.

``session`` is an in-memory SQLite DB (StaticPool keeps one connection so the schema persists
across the session) — broker tests run with no Docker/Postgres. ``offline_settings`` points the
tools at a temp KB and guarantees no search API key, so tool tests never touch the network.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import navi.models  # noqa: F401 — import registers all tables on SQLModel.metadata
from navi.config import Settings


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def offline_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    doc = tmp_path / "kb_note.md"
    doc.write_text(
        "SAP role naming conventions; vendor payment SoD conflict guidance.",
        encoding="utf-8",
    )
    fake = Settings(search_api_key=None, kb_dir=str(tmp_path))
    monkeypatch.setattr("navi.tools.get_settings", lambda: fake)
    return fake
