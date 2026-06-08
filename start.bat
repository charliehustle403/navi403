@echo off
REM Navi - clean local startup: Postgres -> migrate -> seed -> API, then confirm /health.
REM Run from a normal terminal in the repo root:  start.bat        Shut down with: stop.bat
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo === Navi: starting ===

REM --- 0. Docker daemon -------------------------------------------------------
docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Desktop is not running. Start it, then re-run start.bat.
  exit /b 1
)

REM --- 1. Postgres ------------------------------------------------------------
echo [1/5] Starting Postgres ^(docker compose^)...
docker compose up -d
if errorlevel 1 ( echo [ERROR] "docker compose up" failed. & exit /b 1 )

echo [2/5] Waiting for Postgres to be healthy...
set /a tries=0
:waitdb
set "HEALTH="
for /f "delims=" %%i in ('docker inspect -f "{{.State.Health.Status}}" navi-postgres 2^>nul') do set "HEALTH=%%i"
if /i "!HEALTH!"=="healthy" goto dbready
set /a tries+=1
if !tries! geq 30 ( echo [ERROR] Postgres did not become healthy in ~60s. & exit /b 1 )
ping -n 3 127.0.0.1 >nul
goto waitdb
:dbready
echo       Postgres is healthy.

REM --- 2. Deps + migrations + seed -------------------------------------------
echo [3/5] Syncing dependencies ^(uv sync --frozen^)...
call uv sync --frozen
if errorlevel 1 ( echo [ERROR] "uv sync" failed. & exit /b 1 )

echo [4/5] Applying migrations + seeding defaults...
call uv run alembic upgrade head
if errorlevel 1 ( echo [ERROR] "alembic upgrade head" failed. & exit /b 1 )
call uv run python -m navi.seed
if errorlevel 1 ( echo [ERROR] seed failed. & exit /b 1 )

REM --- 3. Launch the API in its own window -----------------------------------
echo [5/5] Starting API on http://127.0.0.1:8000 ...
start "navi-server" cmd /c "uv run uvicorn navi.api:app --host 127.0.0.1 --port 8000"

REM --- 4. Wait for /health ---------------------------------------------------
set /a tries=0
:waitapi
curl -s -o nul http://127.0.0.1:8000/health
if not errorlevel 1 goto apiready
set /a tries+=1
if !tries! geq 30 ( echo [WARN] API not responding on /health yet; check the "navi-server" window. & goto done )
ping -n 2 127.0.0.1 >nul
goto waitapi

:apiready
echo.
echo === Navi is up ===
echo   API:    http://127.0.0.1:8000
echo   Health: http://127.0.0.1:8000/health
echo   Ask:    uv run navi ask "what is SAP SoD?"   ^(needs ANTHROPIC_API_KEY in .env^)
echo   Stop:   stop.bat
:done
endlocal
