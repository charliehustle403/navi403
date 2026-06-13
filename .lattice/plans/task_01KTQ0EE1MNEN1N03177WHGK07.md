# NAVI-14: Broker — optional output redaction before returning tool results to the model

**Complexity:** Low-Medium. One new pure helper + one `ToolSpec` field + a small `broker()` success-path change + a tracer-record field. No DB migration. No signature change to `broker()`. No change to `Allowed`.

---

## Scope

Resolve the deferred TODO at `src/navi/broker.py:206` (`# TODO(scope): optional output redaction before returning to the model (spec section 6.2)`).

Today the broker returns tool results to the model verbatim (`return Allowed(result)`). This task adds a **defensive output transform**: scrub credential/PII-shaped tokens out of a tool OUTPUT before that output re-enters the model context, so a prompt-injection planted in (untrusted) `web_search` results cannot as easily make the model echo a planted secret back outbound.

This is the *inbound* mirror of the NAVI-6 egress check (which guards outbound args). It MUST NOT change routing, tool selection, or tool semantics - it only rewrites string spans inside an already-`Allowed` result.

**In scope**
- A new pure helper `_redact(value: str) -> tuple[str, list[str]]` reusing the NAVI-6 `_CRED_PATTERNS` + `_PII_PATTERNS`.
- A result-traversal helper that applies `_redact` to the string fields of the tool result dict.
- A new `ToolSpec` field `redact_output: bool` (default `False`), set `True` only for `web_search`.
- Wiring in `broker()` after `spec.fn(...)`, gated on `spec.redact_output`.
- Tracing the redaction (labels only, never raw matched content) on the `broker_decision` event.
- Tests (positive + negative + purity + regression).

**Out of scope (leave as `# TODO(scope):`)** - see final section.

---

## Approach - the six required decisions, made explicitly

### Decision 1 - Redact-in-place, NOT deny
**REDACT.** Output redaction is fundamentally different from input egress. The egress check denies the *whole tool call* because the model composed an outbound query and a single secret-shaped token in that query is itself the exfil attempt. For OUTPUT, denying the whole `web_search` result because one secret-shaped token appeared on a fetched page would break legitimate research (a page can legitimately contain a hex hash, an email in a footer, etc.). So we replace only the matched spans and let the cleaned result through.

**Placeholder format:** `[REDACTED:<label>]`, where `<label>` is the exact NAVI-6 label string for the pattern that matched (e.g. `[REDACTED:openai-style key]`, `[REDACTED:email address]`, `[REDACTED:us ssn]`). Implemented with `pattern.sub()` per `(pattern, label)` pair, in the SAME order as `_CRED_PATTERNS` then `_PII_PATTERNS`, so the transform is deterministic and order-stable. The placeholder is a constant string containing no captured content.

### Decision 2 - Which detectors apply to output
Reuse **`_CRED_PATTERNS` + `_PII_PATTERNS` only**, as substitutions (`re.sub`). These are span-shaped detectors: each matches a concrete substring that can be replaced.

The **fragmented-exfil HEX-DENSITY heuristic is NOT applied to output.** It is a whole-string ratio gate (`hexlike/total >= 0.5`) that returns a *reason*, not spans - there is nothing well-defined to substitute, and a legitimate research result that is hex-dense (a page about hashes, a hexdump) is not an exfil attempt the way a hex-dense *query the model composed* is. The density gate and the over-length / long-opaque-token gates stay **input-only**. So: cred+PII patterns are substitutable and apply to output; the density/length gates do not.

Do **not** duplicate any regex - `_redact` iterates the existing `_CRED_PATTERNS` and `_PII_PATTERNS` lists.

### Decision 3 - Scope: only `web_search` gets output-redacted
Add a per-tool flag rather than redacting all output uniformly, mirroring the existing `egress_checked` design:

- `ToolSpec.redact_output: bool = False` (new field, defaulted so existing constructions and tests need no change).
- `web_search`: `redact_output=True` - its results are **untrusted, attacker-controllable** content (the indirect-injection vector per spec section 3 "Read-only is not leak-proof").
- `knowledge_base_search`: `redact_output=False` - local, trusted markdown. Redacting trusted KB content would silently corrupt legitimate answers (a KB doc that documents an example token would come back mangled) for no threat-model gain.

This mirrors `egress_checked` (web=True, kb=False) and keeps the dangerous transform narrowly scoped to the one untrusted channel - the simpler/safer choice per CLAUDE.md.

### Decision 4 - Where redaction happens + result-type traversal
`spec.fn` returns `dict[str, Any]` for both tools (`{"status": ..., "results": [...], "note"?: ...}`, where each `results` item is `{"source"/"title"/"url", "snippet"}`). Redaction targets the **string values** that came from untrusted upstream content.

Two new pure helpers in `broker.py`:

```python
def _redact(value: str) -> tuple[str, list[str]]:
    """Replace credential/PII-shaped spans with [REDACTED:label]. Returns (clean, labels_hit).
    Pure, deterministic, no I/O. Reuses _CRED_PATTERNS + _PII_PATTERNS (NAVI-6)."""

def _redact_result(result: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Walk a tool-result dict and redact its string values, returning a NEW dict + all labels hit.
    Recurses into nested dicts and into lists of dicts/strings (covers result['results'] items).
    Non-string scalars pass through untouched."""
```

`_redact_result` builds a new structure (does not mutate the tool returned dict) by walking values: `str -> _redact`, `dict -> recurse`, `list -> map over items`, everything else unchanged. This mirrors the spirit of `_string_values` for input but, because output is nested, it traverses recursively. Determinism: dict key order is preserved (insertion order), substitutions applied in fixed pattern order.

Wiring in `broker()` success path, replacing the TODO line:

```python
result = spec.fn(validated)
redacted_labels: list[str] = []
if spec.redact_output:
    result, redacted_labels = _redact_result(result)
emit({"event_type": "broker_decision", "tool_name": tool_name, "verdict": "allowed",
      "reason": None, "redacted": redacted_labels})
return Allowed(result)
```

For tools with `redact_output=False`, `result` is returned exactly as before and `redacted` is an empty list - byte-for-byte identical behavior to today (regression-safe).

### Decision 5 - Tracing (labels only, never raw content)
Emit a new `"redacted"` key on the `broker_decision` tracer record: a `list[str]` of the labels that were hit (e.g. `["openai-style key", "email address"]`). The labels are **non-sensitive category names**, not the matched secret, satisfying CLAUDE.md "hash payloads - never store raw sensitive content."

Persistence: `trace.py::RunRecorder.broker_decision` currently forwards only `tool_name`/`verdict`/`reason(->payload_hash)`. The `TraceEvent` SQLModel has **no redaction column**, and adding one is a migration (heavier than warranted). Recommended minimal approach: in `broker_decision`, when `record.get("redacted")` is non-empty, set the event `payload_hash = _hash({"redacted": labels})` (reproducible from the non-sensitive labels, no raw content). This is additive and guarded (`if record.get("redacted")`), so existing trace tests are unaffected.

- The in-memory tracer record always carries `redacted` (tests assert on it directly - no DB needed).
- A first-class column is a **deferred follow-up** (`# TODO(scope):` near the recorder) - not required for acceptance.

### Decision 6 - Signature stability / blast radius
- `broker()` signature: **unchanged.**
- `Allowed`: **unchanged** - no new field. `loop.py` consumes `verdict.result` (json-dumps it, runs `_collect_evidence`); since the redacted result is still the same-shaped dict, loop.py needs **no change**. Surfacing "was redacted" to callers via `Allowed` is unnecessary and would widen blast radius - rejected.
- `ToolSpec`: one new field `redact_output: bool = False` (defaulted -> all existing `ToolSpec(...)` calls in tests/registry keep compiling).
- `trace.py`: one small additive change in `broker_decision`.

Net: additive, low blast radius, no migration, no public-contract change.

---

## Key files
- `src/navi/broker.py` - add `redact_output` to `ToolSpec`; set it `True` for `web_search` in `_REGISTRY`; add `_redact` + `_redact_result`; wire into `broker()` success path (replace the TODO at line 206); add `redacted` to the allowed `emit(...)`.
- `src/navi/trace.py` - `RunRecorder.broker_decision`: additively persist redaction evidence (hash of labels) when present.
- `tests/test_broker.py` - new positive/negative/purity/regression tests (conventions: in-memory `session` + `offline_settings`, `seed_defaults`, injected `registry`/`tracer`).
- `src/navi/tools.py` - reference only (confirms result dict shape; no change expected).
- `src/navi/loop.py` - reference only (confirms `Allowed.result` consumer is shape-stable; no change).

---

## Test cases (named)

Positive
- `test_redact_output_credential_span` - register a fake tool with `redact_output=True` whose `fn` returns `{"status":"ok","results":[{"url":"http://x","snippet":"key is sk-ABCDEFGHIJKLMNOPQRSTUV here"}]}`; assert `Allowed`, and the snippet now contains `[REDACTED:openai-style key]` and no longer contains the raw `sk-...` token.
- `test_redact_output_pii_email` - fake tool output containing `jane.doe@example.com`; assert it becomes `[REDACTED:email address]` and the raw email is gone.
- `test_redact_output_multiple_spans` - output with both a credential and an SSN across nested `results` items; assert both placeholders present; assert the tracer record `redacted` list contains `"openai-style key"` and `"us ssn"` and does NOT contain the raw secret/SSN.
- `test_redact_traced_labels_not_raw` - capture via injected `tracer=records.append`; assert `records[-1]["redacted"]` is the label list and that no raw matched substring appears anywhere in the record.

Negative / regression
- `test_redact_clean_output_unchanged` - fake `redact_output=True` tool returning clean prose; assert `verdict.result` equals the original dict and `redacted == []`.
- `test_kb_output_not_redacted` - real `knowledge_base_search` (`redact_output=False`); even if a faked snippet contains a token-shaped string, output passes through unmodified (scope decision 3).
- `test_existing_allow_paths_unchanged` - existing `test_allow_web_search_degrades_to_unavailable` / `test_allow_knowledge_base_search` still pass (no happy-path behavior change; `unavailable`/`ok` results contain nothing matchable).
- `test_input_egress_unaffected` - assert the input-egress deny tests (`test_deny_egress_*`) are untouched: output redaction runs only AFTER all deny checks pass, so an egress-denied call never reaches `_redact_result`.

Purity / determinism
- `test_redact_is_pure_and_deterministic` - call `_redact(value)` twice on the same input; assert identical `(clean, labels)`; assert the input string is not mutated; assert `_redact_result` returns a NEW dict and leaves the input dict unchanged.
- `test_redact_no_false_positive_on_research_prose` - a word-dense research snippet (mirroring `test_allow_egress_long_research_query`) yields `clean == input`, `labels == []` (confirms the density gate is NOT applied to output).

---

## Acceptance criteria
1. `web_search` results containing credential/PII-shaped spans return `Allowed` with those spans replaced by `[REDACTED:<label>]`; raw matched content is absent from the returned result.
2. `knowledge_base_search` output is returned verbatim (no redaction).
3. Clean output passes through byte-identically; `redacted == []`.
4. The `broker_decision` trace/tracer record carries the redaction labels (non-sensitive) and never the raw matched content; DB persistence change is additive and guarded.
5. `broker()` signature, `Allowed`, and `loop.py` are unchanged; only an additive `ToolSpec` field + private helpers + a small trace adapter change.
6. `_redact`/`_redact_result` are pure, deterministic, I/O-free; reuse the NAVI-6 pattern lists with no regex duplication.
7. All existing broker/trace tests stay green; new tests cover positive, negative/regression, and purity.
8. `ruff` + `mypy` clean; everything typed; style matches the existing module.

---

## Out-of-scope / deferred (leave as `# TODO(scope):`)
- A first-class `redacted` column on `trace_events` (migration) - deferred; this task folds labels into the existing hashed payload path.
- Verbatim-span-from-context echo detection on output (long spans copied out of context) - same deferred follow-up already noted on `_egress_check`.
- Applying redaction to KB or any future tool - gated behind `redact_output`; flip per-tool when a new untrusted source is added.
- Semantic/entropy-based secret detection beyond the NAVI-6 regex set.
- Surfacing "was redacted" to API/CLI callers via `Allowed`/`StructuredResult` - not needed for the threat-model goal.
