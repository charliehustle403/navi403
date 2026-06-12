@echo off
REM Navi - clean local startup: Docker -> Postgres -> deps -> migrate -> seed -> web UI -> API.
REM Run from a terminal or double-click:  start.bat        Shut down with: stop.bat
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo === Navi: starting ===

REM --- 0. Docker daemon (auto-start Docker Desktop if needed) -------------------
docker info >nul 2>&1
if not errorlevel 1 goto dockerup
echo [0/6] Docker is not running - starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a tries=0
:waitdocker
docker info >nul 2>&1
if not errorlevel 1 goto dockerup
set /a tries+=1
if !tries! geq 45 (
  echo [ERROR] Docker did not become ready in ~90s. Start Docker Desktop manually, then re-run start.bat.
  goto fail
)
ping -n 3 127.0.0.1 >nul
goto waitdocker
:dockerup

REM --- 1. Postgres --------------------------------------------------------------
echo [1/6] Starting Postgres ^(docker compose^)...
docker compose up -d
if errorlevel 1 ( echo [ERROR] "docker compose up" failed. & goto fail )

echo [2/6] Waiting for Postgres to be healthy...
set /a tries=0
:waitdb
set "HEALTH="
for /f "delims=" %%i in ('docker inspect -f "{{.State.Health.Status}}" navi-postgres 2^>nul') do set "HEALTH=%%i"
if /i "!HEALTH!"=="healthy" goto dbready
set /a tries+=1
if !tries! geq 30 ( echo [ERROR] Postgres did not become healthy in ~60s. & goto fail )
ping -n 3 127.0.0.1 >nul
goto waitdb
:dbready
echo       Postgres is healthy.

REM --- 2. Deps + migrations + seed ----------------------------------------------
echo [3/6] Syncing dependencies ^(uv sync --frozen^)...
call uv sync --frozen
if errorlevel 1 ( echo [ERROR] "uv sync" failed. & goto fail )

echo [4/6] Applying migrations + seeding defaults...
call uv run alembic upgrade head
if errorlevel 1 ( echo [ERROR] "alembic upgrade head" failed. & goto fail )
call uv run python -m navi.seed
if errorlevel 1 ( echo [ERROR] seed failed. & goto fail )

REM --- 3. Web UI build (first run only; skipped when web\dist already exists) ----
echo [5/6] Checking web UI build...
if not exist "web\package.json" goto uidone
if exist "web\dist\index.html" (
  echo       web\dist present - skipping build.
  goto uidone
)
where npm >nul 2>&1
if errorlevel 1 (
  echo       [WARN] npm not found - skipping UI build. API will run UI-less.
  goto uidone
)
echo       First run: npm install + npm run build ^(takes a minute^)...
pushd web
call npm install
if errorlevel 1 ( popd & echo [ERROR] "npm install" failed. & goto fail )
call npm run build
if errorlevel 1 ( popd & echo [ERROR] "npm run build" failed. & goto fail )
popd
:uidone

REM --- 4. Launch the API in its own window ----------------------------------------
echo [6/6] Starting API on http://127.0.0.1:8000 ...
start "navi-server" cmd /c "uv run uvicorn navi.api:app --host 127.0.0.1 --port 8000"

REM --- 5. Wait for /health, then open the UI --------------------------------------
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
echo   UI:     http://127.0.0.1:8000  ^(opening in your browser^)
echo   Health: http://127.0.0.1:8000/health
echo   Ask:    uv run navi ask "what is SAP SoD?"   ^(needs ANTHROPIC_API_KEY in .env^)
echo   Stop:   stop.bat
start "" http://127.0.0.1:8000/
goto done

:fail
echo.
echo === Navi startup FAILED - see the error above ===
pause
endlocal
exit /b 1

:done
endlocal
