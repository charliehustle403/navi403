# NAVI-1: Fix bootstrap.ps1 false-positive on branch protection failure

## Problem
In `bootstrap.ps1` (section 4, ~lines 177-186) the `gh api -X PUT .../protection` call is
wrapped in try/catch. `gh` is a native command: a non-zero exit (e.g. HTTP 403 on private
repos without GitHub Pro) does NOT raise a PowerShell terminating error, so the `catch` never
fires and execution falls through to `Ok "main protected..."`. The script reports success even
when protection was not applied. Observed live during navi403 bootstrap.

## Fix
Check `$LASTEXITCODE` after the `gh api` call. On 0 → `Ok`. On non-zero → `Warn` with the
captured gh output (which contains the real reason, e.g. the Pro/public hint). Keep the
existing `catch` for genuine PowerShell errors and the `finally` temp-file cleanup.

## Files
- `bootstrap.ps1` (only)

## Acceptance criteria
- A failing `gh api` (non-zero exit) prints a Warn, not `OK`, and surfaces gh's message.
- A succeeding call still prints the `OK` line.
- `catch`/`finally` behavior unchanged. No other script behavior altered.

## Complexity: low
