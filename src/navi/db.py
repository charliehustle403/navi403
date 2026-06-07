"""Database engine + session helpers (sync SQLModel over psycopg v3).

Milestone 1 keeps the data layer deliberately simple: a single sync engine, a session
dependency for FastAPI, and a ``check_db`` probe the health endpoint uses. No async.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import text
from sqlmodel import Session, create_engine

from navi.config import get_settings

logger = logging.getLogger(__name__)

# create_engine is lazy — it does not open a connection here, so importing this module
# (and thus the FastAPI app) never requires the DB to be up.
engine = create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session bound to the shared engine."""
    with Session(engine) as session:
        yield session


def check_db() -> bool:
    """Return True iff a trivial ``SELECT 1`` succeeds.

    Used by ``/health``. Any failure is logged and reported as a False result — the caller
    surfaces it as ``db: "error"`` rather than raising, so the endpoint stays up when the
    database is down.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database health check failed")
        return False
