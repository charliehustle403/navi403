# NAVI-3: Revise navi_MVP_Build_Spec.md to close deep-review findings

## Scope
Revise ONLY `core_documents/navi_MVP_Build_Spec.md` to close the findings from the deep review
(this conversation). Leave `navi_Master_Design_Document_v2.md` unchanged (it is the *why*; the
spec is the *what* and is the thing that must be airtight before milestone 1). No code — doc edit.
Preserve the spec's voice, scope discipline, and section numbering; do not expand MVP scope.

## Findings to close (from review)

### High severity (all must be addressed)
1. **web_search exfiltration channel.** §3 + §6.2 + §6.3: state read-only still has one OUTBOUND
   channel; add a broker **egress check** on web_search args (length cap; deny obvious
   credential/PII/long-verbatim-context payloads). Update §3 non-negotiables and §10 security
   acceptance to include egress.
2. **SAP output: typed vs markdown.** Decide **markdown passthrough** (simpler/safer per §0).
   Reword §2 and §6.6 to drop "schema"; keep §8 markdown; confirm §6.8 CLI just prints it.
   (Do NOT invent a FindingsResult model — keep it simple.)
3. **`research` route dispatch.** §6.4: add research dispatch — runs on `daily_driver` with
   web_search emphasized (same manual loop), distinct from answer_inline only by tool emphasis.
4. **Token→USD pricing config missing.** §4 + §6.1: add a `pricing` table to the model_profiles
   config (per-model input/output $/token), framed as config-that-drifts. cost_usd derives from it.
5. **Budget behavior contradiction.** §6.1 says "abort with error"; §6.4/§10 say "stop and report
   partial". Reconcile to **stop-and-report partial result**; define the partial StructuredResult.
6. **Per-agent permission table missing.** §5: add `agent_tools(agent_id, tool_id, enabled)` join
   so the broker's "agent permitted this tool" check has a data source; seed = one agent ↔ both tools.
7. **RunContext undefined.** §7: define `RunContext` (run_id, agent_id, remaining_budget_usd, scopes)
   — it is load-bearing for the broker budget/scope checks.
8. **Memory gate has no MVP producer.** §6.7: state explicitly that memory is **gate-only** in the
   MVP (consider() is unit-tested directly; no live ingestion path) so no one wires a phantom producer.

### Medium severity (address as clean doc edits)
9. **Broker bypass via grep, not encapsulation.** §3/§6.2: require the tool registry be **private to
   the broker module** (callables not exported) so bypass is structurally impossible.
10. **trace_events too thin.** §5: add clear-text non-sensitive columns (`tool_name`, `verdict`,
    `route`, `tokens_in`, `tokens_out`) alongside `payload_hash`.
11. **knowledge_base_search "keyword/semantic" ambiguous.** §6.3: pin **keyword** for MVP; keep the
    pgvector TODO. Note `docs/` needs seed fixtures for the KB eval.
12. **expires_at not enforced.** §5/§6.7: note expiry/revalidation is column-only (deferred).
13. **No API auth.** §6.8: add "bind to localhost in MVP; shared-secret header if remotely reachable."
14. **Double clarify/refuse precedence.** §6.5: state dispatch-code thresholds override the model's
    returned route (deterministic).
15. **Broker "rate" check has no fields.** §6.2: drop "rate" (keep budget) for MVP, or note deferred.

### Low (fold in if trivial)
- Mark `agents.risk_default`, `tools.requires_approval` "(unused in MVP)".
- Note `last_validated` deferred. CLI `Navi` -> `navi`.

## Approach
- Edit in place, section by section, smallest changes that make each section internally consistent.
- Add a short `## 13. Revision log (v1.1)` at the end summarizing what changed and why, so the
  master-doc readers can see the spec diverged deliberately.
- Keep additive-design intact; nothing here expands runtime scope (egress check + pricing + a join
  table + clarified prose are all within the read-only MVP).

## Files
- `core_documents/navi_MVP_Build_Spec.md` (only).

## Acceptance criteria
- All 8 high-severity findings are closed and the relevant sections no longer contradict each other
  (budget behavior single-valued; SAP output single-valued; research route dispatched; RunContext
  defined; agent_tools present; pricing present; egress check present in broker + §10; memory
  gate-only stated).
- Medium findings 9-15 addressed or explicitly deferred-with-note.
- No MVP scope expansion (still read-only; no write tools; no Agent SDK; no server tools).
- Master design doc untouched. Spec voice/structure preserved. Revision log added.

## Complexity: medium
