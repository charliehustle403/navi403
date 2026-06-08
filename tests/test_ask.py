"""API test (build spec §6.8): POST /ask end-to-end with a fake model + in-memory DB."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import navi.models  # noqa: F401 — register tables
from _fakes import FakeModel, text_response
from navi.api import app, get_model_client, get_session
from navi.seed import seed_defaults


def test_ask_answers_inline(offline_settings: object) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed_defaults(s)

    def override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    classifier = text_response(json.dumps(
        {"route": "answer_inline", "confidence": 0.95, "risk": "low",
         "requires_approval": False, "reason": "general question"}
    ))
    answer = text_response("Hello — I'm Navi, a read-only technical workbench.")
    model = FakeModel([classifier, answer])

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_model_client] = lambda: model
    try:
        client = TestClient(app)
        resp = client.post("/ask", json={"text": "hi, who are you?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["route"] == "answer_inline"
        assert "Navi" in body["answer"]
        assert body["truncated"] is False
    finally:
        app.dependency_overrides.clear()
