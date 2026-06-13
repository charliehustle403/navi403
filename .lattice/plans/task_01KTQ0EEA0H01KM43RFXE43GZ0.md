# NAVI-15: Broker — per-tool rate-limiting (beyond per-run cost budget)

**Complexity: Low-Medium** — mirrors the existing per-run budget gate; NO schema, NO migration,
NO Postgres dependency (RunContext-carried, in-memory for the run's lifetime).

## Scope

Add a deterministic per-run, **per-tool call-count cap** as a DoS + cost backstop layered on top of
the per-run cost budget. Enforced in `broker()` (a new `Denied("tool call rate limit ...")`),
counted in `run_loop`, carried on `RunContext` — exactly the pattern the cost budget already uses
(`max_cost_per_run` / `cost_so_far_usd`). The spec deferred this assuming persistent DB rate fields;
a *per-run* cap needs no persistence, so the spec's "no rate fields in the MVP schema" constraint is
respected (we add none).

## Approach

### RunContext (`src/navi/contracts.py`) — two new fields, opt-in default

```python
# NAVI-15: per-run, per-tool call cap (DoS/cost backstop atop the cost budget). None = no limit
# (default off → every existing caller/test is unaffected). tool_calls accumulates executed calls.
max_calls_per_tool: int | None = None
tool_calls: dict[str, int] = Field(default_factory=dict)
```

- **`max_calls_per_tool: int | None = None`** — `None` means **unlimited / feature off**. This is a
  deliberate departure from the budget's fail-closed `0.0`-denies-all default: rate-limiting is a
  *secondary* backstop (the cost budget remains the primary fail-closed gate), and defaulting it off
  keeps every existing `RunContext(...)`/`_ctx(...)` construction and test behaving exactly as today.
- **`tool_calls: dict[str, int]`** — per-tool count of **executed** (Allowed) calls this run.

### broker() (`src/navi/broker.py`) — new gate, placed after egress, before the budget check

Insert between the egress block (line ~308) and the budget check (line ~309):

```python
if ctx.max_calls_per_tool is not None and ctx.tool_calls.get(tool_name, 0) >= ctx.max_calls_per_tool:
    return deny(f"tool call rate limit exhausted ({tool_name!r}: {ctx.max_calls_per_tool} per run)")
```

- **Order rationale:** security checks (permission → scope → egress) fire first so a malicious call
  is denied for the *security* reason, not masked as a rate-limit; the two per-run *resource* gates
  (rate, then budget) come last. Purely additive — only adds a new DENY, never weakens an existing
  one. The check reads the count of already-executed calls: with `max_calls_per_tool=2`, calls #1
  (count 0) and #2 (count 1) pass, call #3 (count 2) is denied — exactly 2 allowed.
- `broker()`'s public signature is unchanged (rides on `ctx`). Denied calls are NOT counted (they
  didn't execute) — the loop increments only on Allowed (below).

### run_loop (`src/navi/loop.py`) — increment on Allowed, set the cap from the profile

- In the `isinstance(verdict, Allowed)` branch (where evidence/corpus are already collected),
  increment: `ctx.tool_calls[tu.name] = ctx.tool_calls.get(tu.name, 0) + 1`.
- In `handle_request`, where `ctx` is built with `max_cost_per_run=float(prof["max_cost_per_run"])`,
  also set `max_calls_per_tool=prof.get("max_calls_per_tool", _DEFAULT_MAX_CALLS_PER_TOOL)`. Define a
  module constant `_DEFAULT_MAX_CALLS_PER_TOOL = 5` (sane backstop if a profile omits the key).

### model_profiles.json — add the knob to config (config, not code)

Add `"max_calls_per_tool": 5` (tune per profile) alongside `max_cost_per_run` in each profile, so the
cap lives in config per project convention. `handle_request` reads it with the constant as fallback,
so a profile missing the key still works.

## Key files
- `src/navi/contracts.py` — two new `RunContext` fields (opt-in `None` default).
- `src/navi/broker.py` — the rate-limit deny, after egress / before budget.
- `src/navi/loop.py` — increment `ctx.tool_calls` on Allowed; `_DEFAULT_MAX_CALLS_PER_TOOL`; set
  `ctx.max_calls_per_tool` from the profile in `handle_request`.
- `model_profiles.json` — `max_calls_per_tool` per profile.
- `tests/test_broker.py` — unit tests (need a `_ctx(..., max_calls_per_tool=, tool_calls=)` passthrough).
- `tests/test_eval_budget.py` (or test_broker) — an eval-style rate-limit case if the eval file groups
  per-run resource limits; otherwise keep it in test_broker. (§10 has no rate-limit floor; additive.)

## Test cases (named; all SQLite-fixture, fast — no Postgres)
- `test_deny_rate_limit_exhausted` — `_ctx(agent.id, scopes=["web"], max_calls_per_tool=1, tool_calls={"web_search": 1})` → `web_search` denied, `"rate limit"` in reason.
- `test_allow_under_rate_limit` — `max_calls_per_tool=3, tool_calls={"web_search": 1}` → Allowed.
- `test_rate_limit_per_tool_isolated` — `max_calls_per_tool=1, tool_calls={"web_search": 1}` → `knowledge_base_search` (different tool, scope "kb") still Allowed (counts are per-tool).
- `test_rate_limit_default_unlimited` — default `_ctx` (`max_calls_per_tool=None`) with a high prior count → Allowed (feature off; confirms existing callers unaffected).
- `test_rate_limit_denied_not_counted` — a denied (over-limit) call does not increment `tool_calls` (broker doesn't mutate the dict; the loop does). Assert the dict is unchanged after a denied verdict.
- `test_loop_increments_tool_calls` — drive `run_loop` with a FakeModel issuing 2 `web_search` tool_uses under `max_calls_per_tool=1`: first executes, second is denied + surfaced to the model ("DENIED ... rate limit"); assert via the tracer that one allowed + one denied broker decision were recorded.

## Acceptance criteria
1. `broker()` public signature unchanged (cap + counter on `RunContext`).
2. `max_calls_per_tool=None` (default) ⇒ no rate limiting; ALL existing broker/loop/eval tests pass UNMODIFIED.
3. Over-limit `web_search` → `Denied` with `"rate limit"` in reason; surfaced to the model in the loop like other denials (the model can stop/adjust — stop-and-report friendly).
4. Counts are per-tool and per-run; only Allowed calls increment; denied calls don't.
5. The cap is config-driven (`model_profiles.json` `max_calls_per_tool`, default constant fallback) — not hard-coded in broker logic.
6. ruff + mypy clean; `uv run pytest tests/test_broker.py tests/test_eval_egress.py tests/test_loop.py -q` green (fast subset); full suite green when Postgres is up.
7. `RunContext.tool_calls` default uses `Field(default_factory=dict)` (no shared-mutable-default bug); broker treats it read-only, loop mutates it.

## Out of scope / deferred (`# TODO(scope):`)
- Time-window rate limiting (calls per minute/hour) — a per-run count cap fits the single-user
  localhost MVP; sliding-window needs a clock + state and is deferred.
- Persistent / cross-run / per-agent limits in the schema (`Tool`/`AgentTool` rate columns + migration)
  — the original spec framing; deferred as unnecessary for the per-run backstop.
- Global total-tool-call cap (the `_MAX_ITERATIONS=8` loop cap already bounds total turns).
