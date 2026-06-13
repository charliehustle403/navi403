# NAVI-13: Egress — verbatim-span-from-context echo detection in broker

**Complexity: Medium**

## Scope

Add a deterministic, DENY-only egress check that catches **long verbatim spans copied out of the
run's own context** smuggled into an outbound `web_search` query. This is the deferred clause of
spec §6.2 ("deny … long verbatim spans copied from the model's context") and the `# TODO(scope):`
in `src/navi/broker.py` `_egress_check`. The detector compares the outbound query against a
**context corpus** (the run's own sensitive text) and denies when a sufficiently long contiguous
normalized-token run is shared. It only ADDS denies; every existing block (length / opaque-token /
cred / PII / density) and every Allowed path is unchanged. `knowledge_base_search`
(egress_checked=False) is untouched; only `web_search` (egress_checked=True) gets the check.

## Approach (the six decisions)

### Decision 1 — Threading mechanism: RunContext field, NOT a new `broker()` parameter

`ctx: RunContext` is **already** passed to `broker()` (call site `src/navi/loop.py`). Ride the
corpus on `ctx` so the **public `broker()` signature stays byte-for-byte stable**.

- **New field on `RunContext`** (`src/navi/contracts.py`, after `scopes`):
  ```python
  egress_context: tuple[str, ...] = Field(default_factory=tuple)
  ```
  `tuple[str, ...]` (immutable, hashable, matches the frozen/deterministic spirit). Default empty →
  **every existing `RunContext(...)` construction and every test still compiles and behaves exactly
  as today** (empty corpus ⇒ no verbatim match possible ⇒ the new check is a no-op).
- **`_egress_check` internal signature change (allowed — module-private):**
  `_egress_check(value: str, corpus: str = "") -> str | None`. The new corpus-aware branch only runs
  when `corpus` is non-empty; default `""` preserves the existing pure single-arg call shape used in
  unit tests.
- **Broker egress loop:** build the corpus string once before the loop from `ctx.egress_context`
  (join with a separator), pass it into each `_egress_check(value, corpus)` call. The
  `for value in _string_values(validated)` loop and the `deny(f"egress blocked: {blocked}")`
  convention are unchanged.

**Call sites that change (exhaustive):**
- `src/navi/contracts.py` — add the field.
- `src/navi/broker.py` — `_egress_check` signature + new branch; build corpus in `broker()` and
  thread it into the loop; update the `# TODO(scope):` docstring.
- `src/navi/loop.py` — `run_loop` assembles the corpus and sets `ctx.egress_context`. The
  `broker(...)` call itself does **not** change shape.
- No change to `trace.py` (existing `broker_decision` adapter already hashes the reason — a verbatim
  DENY rides the same `reason`→`_hash(reason)` path; reason text carries only a token count, never a
  raw span).

### Decision 2 — Corpus contents: user text + prior KB tool outputs only

Threat model: exfil = the model copying **sensitive context** into an outbound query. Sources:
1. **The original user message** (`user_text`) — always included; the highest-value exfil target.
2. **Prior `knowledge_base_search` outputs** (local/KB content) — included; echoing a KB paragraph
   back out through `web_search` is the exact attack.

**Excluded: prior `web_search` results.** Already external/public; copying them back out is low-risk
and including them would inflate false positives (legitimate follow-up searches reuse prior result
phrasing). Simpler/safer scope.

**Assembly point:** `run_loop` (`src/navi/loop.py`). Seed `corpus = [user_text]`. After each Allowed
broker verdict for `knowledge_base_search`, append the result's string values (a small local
`_corpus_strings(result)` helper, or reuse the evidence string-walk). Before brokering the next
tool_use, set `ctx.egress_context = tuple(corpus)`. So a `web_search` arg is checked against the user
message plus any KB content already pulled this run — exactly the exfil window.

### Decision 3 — Detection algorithm: normalized token n-gram longest-common-run, N=16 tokens / 80 chars

Pure/deterministic, no I/O. New module-level typed constants (NAVI-6/14 style):

```python
_VERBATIM_MIN_TOKENS: int = 16   # contiguous shared normalized tokens to deny
_VERBATIM_MIN_CHARS: int = 80    # AND the shared run must span this many chars
```

**Normalization:** `casefold()`, collapse whitespace runs to single spaces, then `.split()` into
tokens. Applied identically to query and corpus.

**Match:** DENY when the **longest contiguous run of normalized tokens** appearing in BOTH the query
and the corpus is `>= _VERBATIM_MIN_TOKENS` AND that run's reconstructed char length is
`>= _VERBATIM_MIN_CHARS`. Implementation: build the set of corpus token-n-grams of length
`_VERBATIM_MIN_TOKENS` (`set[tuple[str,...]]`, O(corpus_tokens)); slide the same window over the
query tokens and test membership (O(query_tokens)). Corpus is one run's text (small) → bounded
O(n+m). Return `f"verbatim span copied from context ({n} tokens)"` — count/label only, no raw span.

**Why N=16 / 80 chars won't false-positive (load-bearing):**
- A legitimately quoted **KB doc title** or short phrase is ~3–10 tokens — well under 16. A model
  echoing a doc title into a follow-up `web_search` (normal research) passes.
- 16 contiguous *verbatim, in-order* tokens (~80+ chars) shared with the user's message or a KB
  snippet is not idiomatic for a freshly composed query — it indicates a copied sentence/paragraph.
  The existing negative-guard research queries share scattered vocabulary but no 16-token contiguous
  run, so they stay Allowed.
- The dual char gate prevents a run of 16 tiny tokens (fragmented digits) from tripping this — that
  case is already owned by the NAVI-6 density gate; this check targets genuine prose spans.

Exact normalized n-gram only. **Fuzzy/semantic/edit-distance matching is explicitly OUT**
(`# TODO(scope):`).

### Decision 4 — Ordering & interaction

The verbatim check runs **last inside `_egress_check`**, after length → opaque-token → cred → PII →
density. Those five are corpus-independent and cheaper; the verbatim check is the only one needing
the corpus, and running it last means an empty corpus short-circuits to existing behavior with zero
added work. Purely additive — only returns a new DENY reason; never converts an existing DENY to
ALLOW. `knowledge_base_search` stays `egress_checked=False` so it never reaches `_egress_check`. With
`egress_context` empty (any caller that doesn't set it, incl. all current tests), the branch no-ops.

### Decision 5 — Test plan

**`tests/test_broker.py`** (unit):
- `test_deny_egress_verbatim_span_from_context` — `_ctx(agent.id, egress_context=(<long sensitive
  sentence ≥16 tokens>,))`; `web_search` query embeds that exact sentence ⇒ `Denied`, `"egress"` in
  reason; assert the raw span text is NOT present in the traced record.
- `test_allow_egress_short_quote_from_context` — corpus has a KB-style title; query quotes only the
  short title (few tokens) ⇒ `Allowed`.
- `test_allow_egress_unrelated_query_with_context` — corpus set, query is a normal unrelated research
  question ⇒ `Allowed`.
- `test_egress_no_corpus_behaves_as_today` — default `egress_context=()`; an exfil-shaped-but-not-
  verbatim query that was Allowed before stays Allowed (field default is a pure no-op).
- `test_egress_check_pure_deterministic_verbatim` — call `_egress_check(value, corpus)` twice, assert
  equal results and no input mutation.

**`tests/test_eval_egress.py`** (§10 floor — ADD, never remove):
- Add a verbatim-exfil case (corpus + verbatim-echo query ⇒ `Denied` with `"egress"`).
- Add one negative eval: short legitimate quote from corpus ⇒ `Allowed`.
- Existing exfil/research/redaction cases and all `test_deny_egress_*` / `test_allow_egress_*` pass
  **unmodified** (they construct `RunContext`/`_ctx` without `egress_context`).

### Decision 6 — Acceptance criteria

1. Public `broker()` signature **unchanged**; corpus rides on `RunContext.egress_context`.
2. `_egress_check` stays **pure/deterministic, no I/O/network**; covered by the purity test.
3. `ruff` + `mypy` clean; thresholds are typed module-level constants.
4. Full `uv run pytest` green, all pre-existing egress/redaction/broker tests **unmodified**.
5. No false positives on the negative cases (short quote, unrelated query, no-corpus).
6. Spec §6.2 verbatim clause satisfied: rewrite the `# TODO(scope):` to state verbatim-span echo
   detection is **done** (normalized n-gram, N=16/80ch, corpus = user_text + prior KB outputs), and
   note residual deferrals (fuzzy/semantic OUT; prior web_search outputs intentionally excluded).
7. A verbatim DENY is traced **by hash only** — existing `tracer` → `broker_decision` → `_hash(reason)`
   path; reason carries only a token count. Test asserts the raw span is absent from the record.

## Key files

- `src/navi/contracts.py` — add `egress_context: tuple[str, ...] = Field(default_factory=tuple)` to
  `RunContext`.
- `src/navi/broker.py` — `_VERBATIM_MIN_TOKENS` / `_VERBATIM_MIN_CHARS` + verbatim helper;
  `_egress_check(value, corpus="")` signature + last-position branch; build corpus from
  `ctx.egress_context` and thread into the egress loop; update the `# TODO(scope):` docstring.
- `src/navi/loop.py` — `run_loop` assembles `corpus = [user_text]`, appends KB tool-output strings
  after Allowed `knowledge_base_search` verdicts, sets `ctx.egress_context = tuple(corpus)` before
  brokering each tool_use.
- `tests/test_broker.py` — 5 new unit tests.
- `tests/test_eval_egress.py` — verbatim-exfil DENY + short-quote ALLOW (additive).

(`src/navi/trace.py` — no change; hashed-reason path reused.)

## Out-of-scope / deferred (`# TODO(scope):`)

- Fuzzy / semantic / edit-distance matching (exact normalized n-gram only).
- Including prior `web_search` outputs in the corpus (low-risk, FP-prone).
- A first-class `verbatim` column on `trace_events` (deferred since NAVI-14).
- Per-tool configurable thresholds; cross-run/historical corpus.
