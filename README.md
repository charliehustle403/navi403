# Navi

A read-only **Technical Workbench** AI backend — a FastAPI + Postgres service that routes a
request, runs a manual Anthropic tool loop, and either answers directly, performs grounded web
research, or runs a structured **SAP S/4HANA role-design review**. Every tool call passes through a
deterministic **tool broker** (the security boundary), and every run is **traced**.

Inspired by Jarvis from Iron Man.

## Status

MVP — early development. See `core_documents/` for the build spec and master design document.

## Scope (MVP)

- FastAPI backend + Postgres (SQLModel + Alembic)
- Deterministic **tool broker** in front of every tool call
- Two read-only tools: `knowledge_base_search`, `web_search`
- **Navi loop**: router + manual Anthropic Client-SDK tool loop
- **SAP role-design review** capability
- Trace persistence (`runs`, `trace_events`)
- Provenance-gated memory
- Provider-agnostic `model_profiles` config
- CLI client + REST API
- pytest eval suite

**Out of scope:** any write/mutating/side-effecting action, autonomous behavior, schedulers,
frontend, voice, MCP servers, and Anthropic server-side tools (they bypass the broker).

## Development

Requirements: [`uv`](https://docs.astral.sh/uv/), Docker Desktop. Milestone 1 ships the
skeleton + data layer only (config, the §5 SQLModel schema, the Alembic migration, and a
DB-checking `/health`).

```bash
uv sync                              # install deps into .venv
cp .env.example .env                 # (optional) ANTHROPIC_API_KEY not needed until M3
docker compose up -d                 # Postgres 16 on 127.0.0.1:5432
uv run alembic upgrade head          # create the schema
uv run uvicorn navi.api:app --host 127.0.0.1 --port 8000   # serve (localhost only)
# -> GET http://127.0.0.1:8000/health  =>  {"status":"ok","db":"ok"}
```

Checks: `uv run pytest` · `uv run ruff check .` · `uv run mypy`. Tear down Postgres with
`docker compose down` (add `-v` to drop the data volume).

## Documentation

- `core_documents/navi_MVP_Build_Spec.md` — what to build
- `core_documents/navi_Master_Design_Document_v2.md` — why
