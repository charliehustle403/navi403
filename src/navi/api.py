"""FastAPI application (Milestone 1).

Only ``/health`` exists yet. It reports DB connectivity without failing when the database is
down. ``POST /ask`` and ``GET /runs/{id}`` arrive in later milestones. The app is served on
127.0.0.1 only (spec §6.8) — see the run command in README / CLAUDE.md.
"""

from __future__ import annotations

from fastapi import FastAPI

from navi import __version__
from navi.db import check_db

app = FastAPI(title="Navi", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness + DB connectivity. Always 200; ``db`` reflects the probe result."""
    return {"status": "ok", "db": "ok" if check_db() else "error"}
