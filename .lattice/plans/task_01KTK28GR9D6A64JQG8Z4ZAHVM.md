# NAVI-11: start.bat / stop.bat (clean local startup + shutdown)

## Scope
Two Windows cmd batch files at the repo root that bring the full local stack up/down cleanly.
No app code change. Devs run them in their own terminal.

## start.bat (in order, fail-fast)
1. Verify Docker daemon (`docker info`); error + exit if not running.
2. `docker compose up -d` Postgres, then poll `docker inspect` until health == healthy (cap ~60s).
3. `uv sync --frozen` (fast, offline, from uv.lock).
4. `uv run alembic upgrade head` (idempotent).
5. `uv run python -m navi.seed` (idempotent).
6. Launch API in its own window: `start "navi-server" cmd /c "uv run uvicorn navi.api:app --host
   127.0.0.1 --port 8000"`.
7. Poll `curl /health` until reachable (cap ~30s), then print URLs + how to ask/stop.
- Sleeps via `ping -n` (portable; `timeout` breaks under redirected stdin). Steps guarded with
  errorlevel -> message + exit /b 1.

## stop.bat
1. Find PID LISTENING on 127.0.0.1:8000 via `netstat -ano | findstr` -> `taskkill /PID /T /F`.
   Message if none.
2. `docker compose stop` (data volume preserved; note `down -v` to drop).

## Notes
- App boots without ANTHROPIC_API_KEY (only /ask's model call needs it); /health is key-free.
- DATABASE_URL default already points at the compose Postgres, so no .env required.

## Verification
start.bat -> curl /health 200 {status:ok,db:ok} -> stop.bat -> port 8000 free; container stopped.

## Acceptance criteria
- start.bat brings up Postgres + migrations + seed + API and confirms /health; fails fast with a
  clear message if Docker is down or a step errors.
- stop.bat stops the API (by port) + Postgres cleanly; safe when nothing is running.
- No app/source change; files at repo root; committed on dev.

## Complexity: low-medium (Windows batch correctness)
