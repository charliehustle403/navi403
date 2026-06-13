# NAVI-21: Make pytest independent of a running Postgres

**Complexity: Low**

## Root cause (verified)

`uv run pytest` is ~2.5s with Postgres up but ~392s with it down. Investigation shows **`test_health`
is the SOLE offender**: every other API test already routes the DB through in-memory SQLite — either
by overriding the `get_session` dependency (`test_ask`, `test_cli`, `test_runs_list`, `test_trace`)
or by using the `session` fixture directly (`test_sap_review`). `test_health` calls `/health`, which
calls the module-global `check_db()` against the **real-Postgres engine** with no override; when the
container is down (esp. the Docker-port-forwards-but-hangs case) the connect blocks for minutes.

A second, latent prod bug: `/health` can hang for minutes when the DB is down/hung, because the
engine has no connect timeout.

## Approach (two small, surgical changes)

### 1. Make `check_db` injectable; `/health` uses the overridable session dependency
- `src/navi/db.py`: change `check_db() -> bool` to `check_db(session: Session) -> bool`, running
  `session.execute(text("SELECT 1"))` (keep the try/except → False contract). No more reaching for
  the module-global engine directly.
- `src/navi/api.py`: `/health` becomes `def health(session: Session = Depends(get_session))` and
  returns `"db": "ok" if check_db(session) else "error"`. In production this still uses the real
  engine session (still detects DB failure, endpoint still returns 200); in tests the override makes
  it use SQLite.

### 2. Add a connect timeout to the engine (fast-fail, prod robustness + belt-and-suspenders)
- `src/navi/db.py`: `create_engine(..., pool_pre_ping=True, connect_args={"connect_timeout": _DB_CONNECT_TIMEOUT_S})`
  with a module constant `_DB_CONNECT_TIMEOUT_S = 5` (libpq/psycopg connect timeout, seconds). A
  down/hung Postgres now fails within ~5s instead of hanging minutes — fixing `/health` in prod AND
  bounding the blast radius if any future test forgets to override the DB. Normal up-Postgres
  connects are unaffected (well under 5s).

### 3. `test_health` overrides `get_session` with SQLite
- `tests/test_health.py`: use the same in-memory-SQLite + `app.dependency_overrides[get_session]`
  pattern as `test_ask`/`test_runs_list` so `/health` runs `SELECT 1` against SQLite — instant,
  deterministic, no Postgres. Assert `db == "ok"` (SQLite SELECT 1 always succeeds), and keep a note
  that prod reports `"error"` when the real DB is down. Add a focused unit test for the False path:
  `check_db` returns False on a closed/broken session (so the error branch stays covered).

## Key files
- `src/navi/db.py` — `check_db(session)` signature; `connect_args` connect timeout + constant.
- `src/navi/api.py` — `/health` depends on `get_session`, passes the session to `check_db`.
- `tests/test_health.py` — override `get_session` with SQLite; cover both ok and error branches.

## Test cases
- `test_health_returns_ok_with_sqlite` — `/health` over an overridden in-memory session → 200,
  `status=="ok"`, `db=="ok"`; runs with NO Postgres.
- `test_check_db_false_on_broken_session` — `check_db` on a session whose connection is closed/invalid
  returns `False` (covers the except branch; keeps `/health`'s error path tested).
- The whole suite must now run fast (~2-3s) with Postgres DOWN. Manual verification step: stop the
  container (or `docker compose stop`) and confirm `uv run pytest` completes in seconds, not minutes.

## Acceptance criteria
1. With Postgres DOWN, `uv run pytest` completes in seconds (no multi-minute hang); all tests pass.
2. With Postgres UP, the suite still passes (143-ish passed / 1 skipped).
3. `/health` still reports `db: "error"` (not a hang, not a 500) when the real DB is unreachable, now
   bounded by the ~5s connect timeout.
4. `check_db` is injectable; no production code path other than the FastAPI dependency constructs the
   engine session for the health probe.
5. ruff + mypy clean.

## Out of scope / deferred
- Switching the whole suite to a shared SQLite-by-default app fixture (the per-test overrides already
  work; only `test_health` was missing one).
- Async DB / connection pooling tuning beyond the connect timeout.
- Making `database_url` connect-timeout configurable via Settings (hard-coded constant is fine for MVP;
  `# TODO(scope):` if it ever needs per-env tuning).
