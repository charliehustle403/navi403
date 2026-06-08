# NAVI-5: Milestone 2 — Tool broker + read-only tools

## Scope (build spec §11 milestone 2; §6.2, §6.3, §3, §10)
The deterministic security boundary + the two read-only tools behind it, with unit tests.
NO model calls / no router / no /ask (those are M3). Read-only only; no write tools exist.

## Design

### contracts.py (spec §7, only what M2 needs)
- `RunContext` (Pydantic): run_id, agent_id, route, max_cost_per_run, cost_so_far_usd=0.0, scopes=[].
- `BrokerVerdict = Allowed | Denied | ApprovalRequired` (frozen dataclasses):
  `Allowed(result)`, `Denied(reason)`, `ApprovalRequired(action_id)`.

### tools.py (callables PRIVATE — `__all__ = []`; imported only by broker.py) — spec §3, §6.3
- Arg schemas (Pydantic): `KnowledgeBaseSearchArgs(query)`, `WebSearchArgs(query)`.
- `_knowledge_base_search(args)` — **keyword** search over `settings.kb_dir` (default `docs/`)
  markdown; return top-k {snippet, source_path}. `# TODO(scope):` pgvector.
- `_web_search(args)` — httpx call using `settings.search_api_key`; **if no key, return a clear
  "search unavailable" result, never crash** (so tests need no network/mock).

### broker.py (owns the registry) — spec §6.2, §3
- `ToolSpec`: name, args_model, fn, kind ("read_only"), access_scope, egress_checked(bool).
- `_REGISTRY` — private; kb_search(scope "kb", egress False), web_search(scope "web", egress True).
  Source of truth for tool kind/scope/callable/schema.
- `_egress_check(query) -> str|None` — exfiltration backstop. Deny when: len > 512; any
  whitespace-token len >= 40 (opaque blob); credential patterns (sk-…, AKIA…, long hex, JWT eyJ…).
  PII refinement left as `# TODO`.
- `broker(session, agent_id, tool_name, args, ctx, *, registry=None, tracer=None) -> BrokerVerdict`
  Checks IN ORDER (§6.2): tool exists & enabled (registry) → agent permitted (DB: agent_tools
  JOIN tools by name) → kind == read_only → args validate → scope in ctx.scopes → egress (if
  egress_checked) → budget (cost_so_far_usd < max_cost_per_run) → execute → (redact `# TODO`) →
  emit broker_decision via tracer (default log; DB persistence = M5) → Allowed. Else Denied(reason).
  `session` used only for the agent_tools read; `registry`/`tracer` injectable for tests.

### seed.py
- `seed_defaults(session)` idempotent: Agent "navi", two Tool rows (names match registry), AgentTool
  links. `python -m navi.seed` seeds the configured DB.

### docs/ (seed KB) — spec §6.3
- 2-3 small SAP role-design markdown notes.

### config.py additions
- `search_api_key: str | None = None`, `kb_dir: str = "docs"`. (.env.example updated.)

## Tests (fast, hermetic — SQLite in-memory; NO Docker)
- `tests/test_broker.py` fixture: in-memory SQLite (StaticPool) + `seed_defaults`. Cases: allow kb;
  allow web ("unavailable"); deny unknown tool; deny disabled tool; deny agent-not-permitted; deny
  invalid args; deny scope-not-in-ctx; deny budget exceeded; **deny egress/exfil**; deny a seeded
  WRITE tool (kind != read_only).
- `tests/test_tools.py`: kb_search finds a seeded-doc term; web_search returns "unavailable" w/o key.

## Acceptance criteria
- Broker is the single execution path; tool callables private (not exported).
- Check order matches §6.2; every branch returns the right verdict; egress blocks exfil.
- Read-only enforced (write tool denied); approval path exists but untriggered.
- web_search degrades to "unavailable" without a key (no crash/network in tests).
- ruff + mypy clean; pytest green and FAST (no Docker for broker tests).
- No scope creep (no model client / router / /ask).

## Complexity: high (security core)
