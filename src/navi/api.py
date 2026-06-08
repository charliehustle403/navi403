"""FastAPI application (build spec §6.8).

Endpoints so far: ``GET /health`` (M1) and ``POST /ask`` (M3). ``GET /runs/{id}`` lands with trace
persistence in M5. Served on 127.0.0.1 only (spec §6.8). The model client and DB session are
injected as dependencies so tests can override them with a fake model + in-memory DB.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlmodel import Session

from navi import __version__
from navi.contracts import StructuredResult
from navi.db import check_db, get_session
from navi.loop import handle_request
from navi.model_client import Completer, ModelClient

app = FastAPI(title="Navi", version=__version__)


class AskRequest(BaseModel):
    text: str


def get_model_client() -> Completer:
    """Dependency: the real Anthropic-backed model client (overridden in tests)."""
    return ModelClient()


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness + DB connectivity. Always 200; ``db`` reflects the probe result."""
    return {"status": "ok", "db": "ok" if check_db() else "error"}


@app.post("/ask")
def ask(
    req: AskRequest,
    session: Session = Depends(get_session),
    model: Completer = Depends(get_model_client),
) -> StructuredResult:
    """Route the request and run the Navi loop; return the structured result."""
    return handle_request(req.text, model=model, session=session)
