"""FastAPI application (build spec §6.8).

Endpoints so far: ``GET /health`` (M1), ``POST /ask`` (M3), ``GET /runs/{id}`` (M5) and
``GET /runs`` (NAVI-16, web UI history). When a web UI build exists at ``web/dist`` (NAVI-17),
it is mounted at ``/`` after all API routes. Served on 127.0.0.1 only (spec §6.8). The model
client and DB session are injected as dependencies so tests can override them with a fake
model + in-memory DB.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session

from navi import __version__
from navi.config import get_settings
from navi.contracts import RunSummary, RunTrace, StructuredResult
from navi.db import check_db, get_session
from navi.loop import handle_request
from navi.model_client import Completer, ModelClient
from navi.trace import get_run_trace, list_runs

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


@app.get("/runs")
def list_runs_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[RunSummary]:
    """List recent runs, newest first (web UI history view). Token sums from trace events."""
    return list_runs(session, limit=limit)


@app.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunTrace:
    """Return the run summary + ordered trace events (build spec §6.8). 404 if unknown."""
    trace = get_run_trace(session, run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="run not found")
    return trace


def mount_spa(application: FastAPI, dist_dir: str | None = None) -> bool:
    """Mount the web UI build (NAVI-17) at ``/``. No-op (returns False) when the build is absent.

    Must be called AFTER all API routes are defined: Starlette matches routes in registration
    order, so the ``/`` mount only catches paths no API route claimed. Moving this call above
    the route definitions would silently shadow every API route.
    """
    dist = Path(dist_dir or get_settings().web_dist_dir)
    if not dist.is_dir():
        # TODO(scope): NAVI-17 supplies web/dist; until then the API runs UI-less.
        return False
    # TODO(scope): SPA deep-link fallback (rewrite unknown GETs to index.html) when the UI grows
    # client-side routes. The v1 UI is a single page; html=True already serves index at "/".
    application.mount("/", StaticFiles(directory=dist, html=True), name="spa")
    return True


mount_spa(app)
