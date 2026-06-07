"""Runtime configuration, loaded from the environment / ``.env`` (build spec §4).

Settings are read once and cached. ``database_url`` carries a local-dev default (the Docker
Compose Postgres) so the app and tests import without requiring a ``.env`` to exist;
``anthropic_api_key`` is optional in Milestone 1 (no model calls yet).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Optional until Milestone 3 (the model client). Absence must not break boot or /health.
    anthropic_api_key: str | None = None

    # Default points at the Docker Compose Postgres (docker-compose.yml). Override via .env.
    # 127.0.0.1 (not "localhost") avoids the Windows IPv6 ::1 fallback, which the IPv4-only
    # compose port mapping doesn't serve.
    database_url: str = "postgresql+psycopg://navi:navi@127.0.0.1:5432/navi"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings."""
    return Settings()
