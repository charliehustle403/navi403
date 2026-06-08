# NAVI-9: Milestone 5 — Memory provenance gate + trace persistence

## Scope (build spec §11 m5; §6.7, §5, §6.8)
Provenance-gated memory service, trace persistence (runs + trace_events on every
model/tool/broker/route event), and `GET /runs/{id}`. Folds in classifier-cost accounting (M3 nit).
Memory is gate-only (no live producer — spec §6.7); consider() unit-tested directly.

## Design

### contracts.py
- Add `MemoryCandidate` (§7): source, source_trust (trusted|untrusted), value, classification.
- Add /runs/{id} response views: `TraceEventView`, `RunTrace`.

### memory.py (provenance gate — §6.7)
- `consider(session, candidate) -> accepted|quarantined|rejected`:
  - untrusted -> memory_candidates (value_hash, pending), NOT memories -> quarantined.
  - trusted & sensitive (classification=="sensitive" OR PII/credential in value) -> rejected
    candidate (hash only), NOT memories -> rejected.
  - trusted & not sensitive -> memories with provenance, may_influence_actions=False -> accepted.
- `_looks_sensitive(value)`: emails, long digit runs, credential patterns. TODO: SAP-client.

### trace.py (persistence — §5)
- `open_run`, `close_run`, `RunRecorder` (cost accumulator; model_call/broker_decision/route_event/
  error; sha256 payload hashing, non-sensitive cols clear), `get_run_trace`.

### wire into router.py + loop.py (additive optional recorder; M3/M4 tests pass None)
- route/_classify(recorder=None): classifier records model_call.
- run_loop(recorder=None): model_call per complete; broker(tracer=recorder.broker_decision).
- handle_request: open_run -> recorder -> route -> route_event -> ctx.cost_so_far_usd=recorder.cost
  -> run_loop -> close_run(status, cost=recorder.cost); try/except -> error event + close error.

### api.py
- `GET /runs/{id}` -> RunTrace; 404 if unknown.

## Tests (sqlite + fakes; no network)
- test_memory.py: accepted/quarantined/rejected paths; may_influence_actions False; untrusted never
  in memories; sensitive rejected.
- test_trace.py: handle_request persists run + events; cost includes classifier; /runs/{id} 200 +404.
- existing tests still pass (now also persist).

## Acceptance criteria
- Provenance gate exact; every run persists Run + trace_events (route/model_call/broker_decision/
  error); payloads hashed; /runs/{id} works (+404); classifier cost folded in.
- No write tools / Agent SDK / server tools. ruff + mypy clean; pytest green + fast (no network).

## Complexity: high
