# NAVI-16: Web UI backend support: GET /runs list endpoint + serve SPA static build from FastAPI

**Complexity:** Low-Medium. Two additive API surfaces: one new read-only endpoint (`GET /runs`) backed by one new query helper + one new Pydantic contract, and a conditional `StaticFiles` mount. No DB migration. No new dependencies. No change to any existing endpoint, contract, or the 127.0.0.1 binding posture.

---

## Scope

Enabler for the NAVI-17 web UI (Vite+React SPA built to `web/dist`):

1. **`GET /runs`** — list recent runs, newest first, so the UI can populate history and the run inspector. Today only `GET /runs/{run_id}` exists (`src/navi/api.py:49`). Returns a typed `list[RunSummary]` with a `limit` query param (default 50, `ge=1`, `le=200`).
2. **Serve the SPA build from FastAPI** — mount `web/dist` at `/` so the UI is same-origin (no CORS needed; binding stays `127.0.0.1` — the server is started with `uvicorn navi.api:app --host 127.0.0.1` by `start.bat`; nothing in this task touches binding/auth). API routes (`/ask`, `/runs`, `/runs/{id}`, `/health`, plus FastAPI's built-in `/docs`/`/openapi.json`) MUST keep working and take precedence. Must degrade gracefully when `web/dist` does not exist (the frontend lands in NAVI-17 — the API must still boot and the full test suite must pass without it).

**In scope:** `RunSummary` contract; `list_runs()` query helper; `GET /runs` route; `web_dist_dir` Settings field; `mount_spa()` helper + conditional mount; tests.
**Out of scope:** the SPA itself (NAVI-17), deep-link/client-side-routing fallback, pagination cursors, filtering — see final section.

---

## Approach — decisions made explicitly

### Decision 0 (grounding) — the ACTUAL `Run` model columns (verified, `src/navi/models.py:64-74`)

```
id: str (uuid4 hex, PK) | parent_run_id: str | None | agent_id: str | None
route: str | None | status: str ("open"|"ok"|"truncated"|"refused"|"error")
started_at: datetime (default now) | ended_at: datetime | None | cost_usd: float
```

Two deviations from the task sketch, forced by the real schema:
- **There is no `created_at` on `Run`.** `started_at` IS the creation timestamp (`default_factory=_now`, set at insert in `open_run`). `RunSummary` exposes `started_at` (and `ended_at`), matching the existing `RunTrace` contract field names — do NOT invent a `created_at` alias.
- **There are no token columns on `Run`.** `tokens_in`/`tokens_out` live per-event on `TraceEvent` (`models.py:92-93`, populated by `RunRecorder.model_call`). "Tokens if available" therefore means **aggregating** `SUM(trace_events.tokens_in/out)` per run, exposed as `int | None` (NULL -> `None` when a run has no model_call events, e.g. an error-before-model run).

### Decision 1 — `GET /runs` response shape: bare `list[RunSummary]`

New Pydantic v2 model in `src/navi/contracts.py`, placed next to `RunTrace` under the existing `# --- /runs/{id} trace views` section (extend the comment to cover the list view). Same style as `RunTrace`: ISO-8601 strings for datetimes, plain `str` for status/route:

```python
class RunSummary(BaseModel):
    """One row in GET /runs — the run header without its events (web UI history list)."""

    run_id: str
    agent_id: str | None
    route: str | None
    status: str
    cost_usd: float
    started_at: str            # ISO-8601; the run's creation time (no created_at column exists)
    ended_at: str | None
    tokens_in: int | None      # SUM over the run's model_call trace events; None if none
    tokens_out: int | None
```

Endpoint signature (in `src/navi/api.py`, defined **above** `get_run` so the static `/runs` path reads before the parameterized one — no actual conflict, exact paths win, but it reads better):

```python
@app.get("/runs")
def list_runs_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[RunSummary]:
```

`fastapi.Query` is already sanctioned: `pyproject.toml` ruff config lists `fastapi.Query` in `extend-immutable-calls`. Out-of-range `limit` -> FastAPI's automatic 422 (no hand-rolled validation). Response is a bare JSON array — consistent with returning the contract directly as `ask`/`get_run` do; no envelope object.

**Query helper** goes in `src/navi/trace.py` next to `get_run_trace` (that module owns Run/TraceEvent reads), reusing its `_iso` helper:

```python
def list_runs(session: Session, limit: int = 50) -> list[RunSummary]:
    rows = session.exec(
        select(Run, func.sum(TraceEvent.tokens_in), func.sum(TraceEvent.tokens_out))
        .join(TraceEvent, col(TraceEvent.run_id) == col(Run.id), isouter=True)
        .group_by(col(Run.id))
        .order_by(col(Run.started_at).desc(), col(Run.id))
        .limit(limit)
    ).all()
    return [RunSummary(run_id=run.id, ..., tokens_in=tin, tokens_out=tout) for run, tin, tout in rows]
```

- **Newest-first:** `order_by(col(Run.started_at).desc())` — `col()` per the established mypy pattern already used at `trace.py:106`. Secondary `col(Run.id)` tie-break makes ordering deterministic when timestamps collide (Windows clock granularity in tests).
- **Tokens in ONE query:** LEFT OUTER JOIN + `GROUP BY runs.id` + `func.sum` (import `func` from `sqlalchemy`). Works identically on Postgres (prod) and SQLite StaticPool (tests). `SUM` of no rows / all-NULL -> `NULL` -> `None`. No N+1, no coalesce-to-0 (0 would lie — "no token data" is not "zero tokens").
- mypy note: the 3-entity `select(...)` returns tuples `(Run, Any, Any)`; unpack and pass to the typed `RunSummary` constructor — no `# type: ignore` expected (sqlmodel's multi-entity `select` overloads cover 3 args).

### Decision 2 — Static serving: conditional `StaticFiles` mount at `/`, added AFTER all route definitions

Mechanism: `app.mount("/", StaticFiles(directory=dist, html=True), name="spa")` at the **bottom of `api.py`**, guarded by `is_dir()`.

- **Why precedence works (verified semantics):** Starlette matches `app.router.routes` **in list order** — there is no special "mounts after routes" phase; precedence comes purely from registration order. All API routes (and FastAPI's built-ins `/docs`, `/openapi.json`, `/redoc`, registered at `FastAPI(...)` construction) are appended before the mount, so they win; the `Mount("/")` is the final catch-all. This MUST be stated in a comment at the mount site, because moving the mount above the route definitions would silently shadow every API route.
- **`StaticFiles` ships with Starlette** (a FastAPI hard dependency; import as `from fastapi.staticfiles import StaticFiles`). **`aiofiles` is NOT needed** — modern Starlette (fastapi>=0.115 pins starlette>=0.37) serves files via `FileResponse`/anyio thread offloading; the aiofiles requirement was dropped in old Starlette versions. No new dependencies.
- **`html=True`** serves `index.html` for `GET /` (and directory paths) and lets hashed assets (`/assets/*.js|css`) resolve naturally.
- **Missing-directory handling + testability:** wrap in a small module-level helper so tests can exercise the mount without `importlib.reload` gymnastics:

```python
def mount_spa(application: FastAPI, dist_dir: str | None = None) -> bool:
    """Mount the web UI build (NAVI-17) at '/'. No-op (False) when the build is absent.

    Must be called AFTER all API routes are defined: Starlette matches routes in
    registration order, so the '/' mount only catches paths no API route claimed.
    """
    dist = Path(dist_dir or get_settings().web_dist_dir)
    if not dist.is_dir():
        # TODO(scope): NAVI-17 supplies web/dist; until then the API runs UI-less.
        return False
    application.mount("/", StaticFiles(directory=dist, html=True), name="spa")
    return True

mount_spa(app)   # last statement touching `app` in the module
```

  `StaticFiles(directory=...)` raises for a missing directory (`check_dir=True` is the default) — hence the explicit `is_dir()` guard rather than relying on StaticFiles' own error. With no `web/dist`, the app is byte-for-byte today's app (the mount is never added), so the whole existing suite passes unchanged.
- **Deep-link fallback** (serving index.html for unknown non-API paths, e.g. a refresh on `/runs-view/abc`): **DEFERRED.** The v1 UI is a single page; `html=True` already covers `/`. A 404-rewriting catch-all adds a custom exception handler or wildcard route for zero v1 benefit. Leave `# TODO(scope): SPA deep-link fallback (rewrite unknown GETs to index.html) when the UI grows client-side routes.` at the mount site.

### Decision 3 — `web_dist_dir` is a Settings field (matches `kb_dir` precedent)

Add to `Settings` in `src/navi/config.py`, alongside `kb_dir`:

```python
# web UI static build (NAVI-17). Relative to the process cwd (repo root per start.bat).
web_dist_dir: str = "web/dist"
```

Rationale: `kb_dir: str = "docs"` and `model_profiles_path` establish the convention — filesystem locations are Settings fields, plain `str`, repo-root-relative defaults, env-overridable via `.env`. This also gives tests a clean injection point (`mount_spa(app, str(tmp_path))` takes the explicit-arg path, so tests do not even need to touch Settings). `start.bat` runs uvicorn from the repo root (`cd /d "%~dp0"`), so the relative default resolves correctly in prod; pytest also runs from the repo root.

### Decision 4 — Wiring summary (all additive)

- `contracts.py`: + `RunSummary`.
- `trace.py`: + `list_runs(session, limit)` (imports `func` from sqlalchemy; reuses existing `_iso`, `col`, `select`, `Run`, `TraceEvent`).
- `api.py`: + imports (`Query`, `pathlib.Path`, `StaticFiles`, `get_settings`, `RunSummary`, `list_runs`); + `GET /runs` route above `GET /runs/{run_id}`; + `mount_spa()` helper + call at module bottom; update the module docstring endpoint list.
- `config.py`: + `web_dist_dir` field.
- No changes to `models.py`, `db.py`, `loop.py`, migrations, or any existing route handler.

---

## Key files
- `src/navi/api.py` — new `GET /runs` route; `mount_spa()` + module-bottom call; docstring update.
- `src/navi/trace.py` — new `list_runs()` query helper (one outer-join/group-by query, `col(...).desc()` ordering).
- `src/navi/contracts.py` — new `RunSummary` Pydantic model next to `RunTrace`.
- `src/navi/config.py` — new `web_dist_dir: str = "web/dist"` Settings field.
- `tests/test_runs_list.py` (new) + `tests/test_static_ui.py` (new) — reuse the engine-override TestClient pattern from `tests/test_trace.py::test_runs_endpoint_and_404` and the `session` fixture from `tests/conftest.py`.

---

## Test cases (named)

`tests/test_runs_list.py` (seed pattern: StaticPool sqlite engine + `app.dependency_overrides[get_session]`, exactly as `test_trace.py:57-85`; seed runs directly with `open_run`/`close_run` or raw `Run(...)` rows with explicit `started_at` values so ordering assertions are deterministic):
- `test_list_runs_empty_db_returns_empty_list` — `GET /runs` on a fresh DB -> 200, `[]`.
- `test_list_runs_newest_first_with_fields` — insert 3 runs with distinct explicit `started_at`; assert order is newest-first and each item has exactly the `RunSummary` keys (`run_id`, `agent_id`, `route`, `status`, `cost_usd`, `started_at`, `ended_at`, `tokens_in`, `tokens_out`) with correct values.
- `test_list_runs_aggregates_tokens` — one run with two `model_call` TraceEvents (10/5 and 20/7 tokens) -> `tokens_in == 30`, `tokens_out == 12`; a run with no events -> both `None`.
- `test_list_runs_limit_respected` — insert 3 runs, `GET /runs?limit=2` -> exactly the 2 newest.
- `test_list_runs_limit_validation` — `limit=0` -> 422; `limit=201` -> 422; no param -> 200 (default 50).
- `test_run_detail_endpoint_unchanged` — existing `test_trace.py::test_runs_endpoint_and_404` already covers `GET /runs/{id}` + 404; additionally assert `GET /runs` and `GET /runs/{id}` coexist (the list contains the id the detail endpoint serves).

`tests/test_static_ui.py`:
- `test_app_boots_and_serves_api_without_web_dist` — with no `web/dist` in the repo (current state), `TestClient(app)` works: `GET /` -> 404 while `GET /health` -> 200 JSON. (Also implicitly proven by the entire existing suite passing.)
- `test_mount_spa_missing_dir_is_noop` — `mount_spa(app, str(tmp_path / "nope"))` returns `False` and adds no route named `"spa"`.
- `test_mount_spa_serves_index_and_api_takes_precedence` — write `tmp_path/index.html` (`<html>navi-ui</html>`) and `tmp_path/assets/app.js`; `mount_spa(app, str(tmp_path))` -> True; `GET /` -> 200, `text/html`, body contains `navi-ui`; `GET /assets/app.js` -> 200; `GET /health` STILL returns the JSON dict (route precedence over the `/` mount). Teardown removes the mount in a `finally` (the `app` is module-global and other tests reuse it): `app.router.routes[:] = [r for r in app.router.routes if getattr(r, "name", None) != "spa"]`.

Quality gates: `uv run ruff check .`, `uv run mypy`, full `uv run pytest` green.

---

## Acceptance criteria
1. `GET /runs` returns 200 with a JSON array of `RunSummary` objects, newest-first by `started_at`, default limit 50, `?limit=` validated `ge=1 le=200` (422 outside the range).
2. `RunSummary` exposes exactly: `run_id`, `agent_id`, `route`, `status`, `cost_usd`, `started_at` (ISO), `ended_at` (ISO|null), `tokens_in`/`tokens_out` (summed from trace events, `null` when absent). One DB query, no N+1.
3. With a populated `web/dist` (or injected dir), `GET /` serves `index.html` and asset paths resolve; `GET /health`, `POST /ask`, `GET /runs`, `GET /runs/{id}`, and `/docs` all still answer from the API (route precedence verified by test).
4. With NO `web/dist`, the app imports, boots, and the entire test suite passes — the mount is simply absent (`mount_spa` returns `False`).
5. Zero changes to existing endpoint behavior/contracts, no new pip dependencies, no DB migration, binding/auth posture untouched (the 127.0.0.1 host flag lives in `start.bat`, unmodified).
6. Everything typed; `ruff` + `mypy` clean; `# TODO(scope):` markers left for the deferred items below.

---

## Out-of-scope / deferred (leave as `# TODO(scope):`)
- **SPA deep-link fallback** (rewrite unknown non-API GETs to `index.html`) — defer until the UI has client-side routes (NAVI-17+). The v1 UI is a single page; `html=True` suffices.
- **The frontend itself** (`web/` source, Vite build, `web/dist` artifact) — NAVI-17.
- **Pagination beyond `limit`** (cursor/offset, total counts) — add when the UI needs infinite scroll.
- **Filtering** (`?status=`, `?route=`, date ranges) — additive query params later.
- **Token columns on `runs`** (denormalized `tokens_in/out`, migration) — the aggregate query is sufficient at MVP scale; revisit if `/runs` becomes hot.
- **Cache headers / immutable-asset caching** for `/assets/*` — premature for a localhost tool.
