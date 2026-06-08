# NAVI-7: Milestone 3 — model client + manual tool loop + router + /ask

## Scope (build spec §11 m3; §6.1, §6.4, §6.5, §6.8, §7)
The brain: model_profiles wrapper (pricing + stop-and-report budget), the manual Anthropic
Client-SDK tool loop driving the M2 broker, the router + deterministic dispatch (incl. `research`),
and `POST /ask` answering general + research. SAP reviewer prompt is M4; trace/run persistence is
M5 — both deferred here (clear TODOs). No write tools.

## Design

### model_profiles.json (config file) + model_client.py
- `model_profiles.json` at repo root: profiles {cheap_triage, daily_driver, deep_reasoning,
  local_private} each {provider, model, max_cost_per_run, max_tokens}; a `pricing` map
  model -> {input_per_mtok, output_per_mtok}. Real current model IDs; prices marked VERIFY /
  config-drifts (not asserted as fact).
- `model_client.py`: dataclasses ToolUse, ModelResponse(text, tool_uses, stop_reason, input_tokens,
  output_tokens, cost_usd, content: list[dict]). `load_profiles()` cached (json file w/ fallback).
  `price(model,in,out)`. `ModelClient.complete(profile, messages, tools, system) -> ModelResponse`
  using `Anthropic(api_key=...).messages.create(...)`; normalizes blocks to dicts; computes cost.
  Clear error if no api key. Injectable so tests use a fake (no network/key).

### contracts.py (add §7)
- `RouteDecision(route, confidence, risk, requires_approval=False, reason)`.
- `StructuredResult(run_id, route, answer, evidence=[], cost_usd, needs_approval=False, truncated=False)`.

### prompts.py
- GENERAL, RESEARCH (emphasize web_search + cite urls), CLASSIFIER (RouteDecision JSON only).
  SAP_REVIEW placeholder w/ `# TODO(M4)`.

### router.py
- `route(model, text) -> RouteDecision`: deterministic pre-check (explicit `/sap-review` or SAP
  keywords -> sap_review) else cheap_triage classifier (parse JSON; failure -> clarify).
- `dispatch_route(decision) -> str`: code overrides model — confidence<0.6 -> clarify; risk high
  -> refuse; else decision.route.

### broker.py (addition)
- `anthropic_tool_defs() -> list[dict]`: public; derive Anthropic tool schemas (name, description,
  input_schema via args_model.model_json_schema()) from the private registry — execution still
  routes through broker().

### loop.py
- `run_loop(model, session, ctx, system, profile, user_text) -> StructuredResult`: budget check
  before each model call (>= max -> stop-and-report partial, truncated=True); complete; add cost;
  stop_reason != tool_use -> return answer; else append assistant content, route each tool_use
  through broker(), append tool_result (Allowed -> json + collect evidence; Denied -> "DENIED:
  reason" so model sees refusal), re-loop; hard iteration cap.
- `handle_request(text, *, model, session) -> StructuredResult`: fetch default agent ("navi") ->
  agent_id + scopes (from permitted tools); route(); dispatch_route(); RunContext w/
  max_cost_per_run from the chosen profile (fixes M2 0.0 footgun); dispatch answer_inline/research/
  sap_review(TODO M4)/clarify/refuse; run_id = uuid (run/trace persistence = M5).

### api.py
- `POST /ask {text} -> StructuredResult`. Deps get_session + get_model_client (overridable in tests).

### config.py
- add `model_profiles_path: str = "model_profiles.json"`.

## Tests (mocked model — no network/key; SQLite session + seed)
- test_router.py: SAP pre-check (explicit + keyword); classifier JSON via fake; parse-failure ->
  clarify; dispatch policy thresholds + override.
- test_loop.py: fake model [tool_use -> end_turn]; assert broker invoked + tool_result + answer +
  evidence; budget stop-and-report (scripted costs exceed max -> truncated); Denied verdict surfaced.
- test_ask.py: dependency_overrides (fake model + seeded sqlite); POST /ask -> 200 StructuredResult.

## Acceptance criteria
- /ask answers general + research (mocked); router deterministic dispatch incl. research; loop
  drives broker for every tool call; budget = stop-and-report partial.
- model IDs + prices in config file, not logic. ctx.max_cost_per_run set from profile.
- No write tools / no Agent SDK / no server tools. SAP + trace persistence deferred (TODOs).
- ruff + mypy clean; pytest green and fast (no network). Live /ask works if ANTHROPIC_API_KEY set.

## Complexity: high (largest milestone)
