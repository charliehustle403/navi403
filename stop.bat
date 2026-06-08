@echo off
REM Navi - clean shutdown: stop the API server (by port) and the Postgres container.
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo === Navi: stopping ===

REM --- 1. API server: kill whatever is LISTENING on 127.0.0.1:8000 ------------
echo [1/2] Stopping API server ^(port 8000^)...
set "PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "127.0.0.1:8000" ^| findstr "LISTENING"') do set "PID=%%p"
if defined PID (
  taskkill /PID !PID! /T /F >nul 2>&1
  echo       Stopped API server ^(PID !PID!^).
) else (
  echo       No API server listening on 127.0.0.1:8000.
)

REM --- 2. Postgres -----------------------------------------------------------
echo [2/2] Stopping Postgres ^(docker compose stop^)...
docker compose stop

echo.
echo === Navi stopped ===
echo   Data volume preserved. To also drop the database: docker compose down -v
endlocal
