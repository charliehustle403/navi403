# NAVI-10: Milestone 6 — eval suite (§10) + navi CLI

## Scope (build spec §11 m6; §10, §6.8)
Completes the MVP: the full pytest eval suite graded on the PATH (route/verdict/action-not-taken,
not just text), and the thin `navi` CLI client. No new runtime behavior — exercises what M1–M5
built. Read-only throughout.

## Design

### cli.py + pyproject entry
- `navi ask "<text>"` -> POST /ask, print answer + sources + `[route … cost …]` line (SAP markdown
  printed as-is). `navi run <id>` -> GET /runs/{id}, print summary + events. argparse; httpx client
  injectable (tests use an ASGITransport client over the app — no network/server). Errors -> stderr,
  exit 1.
- `[project.scripts] navi = "navi.cli:main"`; `uv sync` to register.

### SAP goldens -> 10 total
- Add 6 fixtures to tests/goldens/sap/ (SoD user-admin+role-admin, S_DEVELOP in prod, composite
  naming, Fiori catalog vs backend mismatch, leftover disabled tcodes, S_RFC blanket).

### Eval suite (tests/test_eval_*.py; flat so `_fakes` imports work; graded on path)
- test_eval_tool_permission.py: >=10 (real broker, sqlite) — allow kb/web; deny unknown/disabled/
  unpermitted-agent/write-kind/bad-scope/invalid-args. Assert verdict TYPE.
- test_eval_egress.py: >=5 exfil web_search payloads -> Denied(egress).
- test_eval_budget.py: >=5 scripted-cost scenarios -> run_loop truncated stop-and-report.
- test_eval_routing.py: >=10 (text -> expected route): SAP pre-check, non-SAP, dispatch policy.
- test_eval_injection.py: >=10 — FakeModel emits a forbidden tool_use (exfil/unknown/out-of-scope);
  via handle_request assert persisted trace verdict "denied" + action NOT taken.
- test_eval_sap_goldens.py: over the 10 goldens — each routes sap_review + valid §8 structure.
- Live evals stay gated (NAVI_LIVE_TESTS); not required for CI.

## Acceptance criteria
- Counts meet §10: >=10 routing, >=10 SAP goldens, >=10 injection, >=10 tool-permission, >=5 budget,
  >=5 egress; graded on the path.
- `navi ask` works end-to-end against /ask; `navi run` shows a trace; CLI tested via ASGI (no net).
- No write tools / Agent SDK / server tools. ruff + mypy clean; pytest green + fast (no network).

## Complexity: high (breadth)
