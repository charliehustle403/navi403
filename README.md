# Navi

A read-only **Technical Workbench** AI — a FastAPI + Postgres backend with a Jarvis-style web
cockpit. Navi routes a request, runs a manual Anthropic tool loop, and either answers directly,
performs grounded web research, or runs a structured **SAP S/4HANA role-design review**. Every
tool call passes through a deterministic **tool broker** (the security boundary), and every run
is **traced** end to end.

Inspired by Jarvis from Iron Man.

## Status

**Backend MVP complete** (milestones M1–M6: schema, broker + egress hardening + output
redaction, model loop + router, SAP reviewer, memory gate + tracing, eval suite + CLI).
**Web UI v1 in progress** — the cockpit shell and chat + run inspector are live; the run-graph
view is next. See `core_documents/` for the build spec and master design document.

## Quick start (Windows)

Requirements: [`uv`](https://docs.astral.sh/uv/), Docker Desktop, Node.js (for the web UI).

```bat
start.bat   :: Docker -> Postgres -> deps -> migrations -> seed -> UI build -> API -> browser
stop.bat    :: stops the API server and the Postgres container (data volume preserved)
```

`start.bat` auto-starts Docker Desktop if needed, builds the web UI on first run (skipped when
`web\dist` exists; skipped with a warning if npm is absent), and opens
**http://127.0.0.1:8000/** when the API is healthy. Failures pause the window so the error is
readable.

To get real answers, create a `.env` in the repo root with your API key (without it the UI and
CLI still run, but asks fail gracefully):

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Web UI

A dark "Jarvis cockpit" (light theme toggle included): chat with route badges, evidence and
cost per answer, plus a **Run Inspector** showing each run's trace — route decision, model
calls with token counts, and broker verdicts (allowed / denied / output-redacted) as the
security boundary's live instrument panel.

- Production: built to `web/dist` (not committed) and served same-origin by FastAPI at `/`.
- Manual build: `cd web && npm install && npm run build`
- Development: `cd web && npm run dev` — Vite on :5173 with HMR, proxying `/ask`, `/runs`,
  and `/health` to the API on :8000.

## API + CLI

| Surface | What |
|---|---|
| `POST /ask` | Route + answer a request; returns a `StructuredResult` |
| `GET /runs` | Recent runs, newest first (`?limit=`, default 50) |
| `GET /runs/{id}` | One run's summary + ordered trace events |
| `GET /health` | API + DB health |
| `GET /` | The web UI (when `web/dist` exists) |
| `uv run navi ask "..."` | CLI ask |
| `uv run navi run <run_id>` | CLI trace view |

The API binds to **127.0.0.1 only** — `/ask` spends your API key, so never expose it beyond
localhost without adding auth.

## Manual development setup

```bash
uv sync                              # install deps into .venv
cp .env.example .env                 # add ANTHROPIC_API_KEY for live answers
docker compose up -d                 # Postgres 16 on 127.0.0.1:5432
uv run alembic upgrade head          # create the schema
uv run python -m navi.seed           # seed the default agent + tools
uv run uvicorn navi.api:app --host 127.0.0.1 --port 8000
# -> GET http://127.0.0.1:8000/health  =>  {"status":"ok","db":"ok"}
```

Checks: `uv run pytest` · `uv run ruff check .` · `uv run mypy .` (and `npm run lint` /
`npm run build` in `web/`). Tear down Postgres with `docker compose down` (add `-v` to drop
the data volume).

## Design guarantees

- **Read-only by design** — no write/mutating tools, no autonomous actions.
- **The broker is the only code path that executes a tool** — permission, scope, egress
  (credential/PII/fragmented-exfil detection on outbound queries), budget, and output
  redaction checks run on every call.
- **Every run is traced** — payloads are hashed, never stored raw.
- **Model choices live in `model_profiles.json`** (config, not code) — Anthropic profiles
  today; a local/offline profile is defined for future wiring.

**Out of scope (deliberately):** write/side-effecting actions, autonomous behavior,
schedulers, MCP servers, and Anthropic server-side tools (they would bypass the broker).
Voice input/output is tracked as future work.

## Documentation

- `core_documents/navi_MVP_Build_Spec.md` — what to build
- `core_documents/navi_Master_Design_Document_v2.md` — why
