"""CLI tests (build spec §6.8): driven against the in-process app via TestClient — no network."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import navi.models  # noqa: F401 — register tables
from _fakes import FakeModel, text_response, tool_use_response
from navi import cli
from navi.api import app, get_model_client, get_session
from navi.seed import seed_defaults

_ANSWER_INLINE = json.dumps(
    {"route": "answer_inline", "confidence": 0.95, "risk": "low",
     "requires_approval": False, "reason": "general"}
)


def _client_for(model: FakeModel) -> TestClient:
    """A TestClient (an httpx.Client subclass) wired to the app with a seeded in-memory DB."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed_defaults(s)

    def override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_model_client] = lambda: model
    return TestClient(app)


def test_cli_ask_prints_answer_and_status(offline_settings: object) -> None:
    client = _client_for(FakeModel([text_response(_ANSWER_INLINE), text_response("Navi here.")]))
    try:
        buf = io.StringIO()
        rc = cli.cmd_ask("hello", client=client, out=buf)
        assert rc == 0
        text = buf.getvalue()
        assert "Navi here." in text
        assert "route=answer_inline" in text
        assert "run=" in text
    finally:
        app.dependency_overrides.clear()


def test_cli_ask_shows_evidence(offline_settings: object) -> None:
    client = _client_for(FakeModel([
        text_response(_ANSWER_INLINE),
        tool_use_response("knowledge_base_search", {"query": "naming"}),
        text_response("Names must encode type/master/scope."),
    ]))
    try:
        buf = io.StringIO()
        cli.cmd_ask("how do I name roles?", client=client, out=buf)
        assert "Sources:" in buf.getvalue()
    finally:
        app.dependency_overrides.clear()


def test_cli_run_shows_trace_and_404(offline_settings: object) -> None:
    client = _client_for(FakeModel([text_response(_ANSWER_INLINE), text_response("hi")]))
    try:
        run_id = client.post("/ask", json={"text": "hi"}).json()["run_id"]
        buf = io.StringIO()
        rc = cli.cmd_run(run_id, client=client, out=buf)
        assert rc == 0
        out = buf.getvalue()
        assert run_id in out
        assert "status=ok" in out
        assert "route" in out
        assert cli.cmd_run("does-not-exist", client=client, out=io.StringIO()) == 1
    finally:
        app.dependency_overrides.clear()
