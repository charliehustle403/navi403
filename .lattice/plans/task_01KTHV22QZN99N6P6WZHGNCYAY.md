# NAVI-2: Fill in project docs (CLAUDE.md placeholders + AGENTS.md/GEMINI.md §5)

## Scope
Replace the template `<PROJECT NAME>`/`<!-- TODO -->` placeholders with real Navi project
details, sourced from `core_documents/navi_MVP_Build_Spec.md` and the `README.md`. Do NOT touch
the Lattice mandate, the multi-surface workflow, or the Git workflow prose — only fill the
placeholders. Preserve the dev→main / branch-protection text (already accurate).

## Source of truth
- Stack & invariants: `core_documents/navi_MVP_Build_Spec.md` §3, §4, §9.
- One-liner & scope: `README.md`.
- Remote URL: `git@github.com:charliehustle403/navi403.git`.

## Honesty constraint
No code exists yet (only `core_documents/`). So:
- **Stack** is concrete (pinned in spec §4) → state it directly.
- **Commands** and **Project structure** are the *planned/intended* shape from the build spec,
  not yet runnable. Label them as planned so no agent assumes `pytest` already works. Avoid
  inventing a package manager the spec doesn't pin — note `uv` is the installed toolchain but
  mark deps install as TBD-until-scaffolded.

## Edits
### CLAUDE.md
- `# <PROJECT NAME>` -> `# Navi`
- One-line description -> read-only Technical Workbench (FastAPI + Postgres, manual Anthropic
  tool loop behind a deterministic broker).
- **Stack** -> Python 3.12, FastAPI, Uvicorn, SQLModel + Alembic, Postgres 16, Pydantic v2,
  `anthropic` Client SDK, httpx, pytest, ruff, mypy.
- **Commands** -> planned commands (uvicorn run, pytest, ruff check, mypy), flagged as
  not-yet-scaffolded.
- **Project structure** -> planned module map from spec §3/§6 (router / broker / tools / memory /
  trace / model client + api + cli), flagged as not-yet-created.
- **Conventions** -> add: type everything (pydantic v2 contracts); model IDs live in
  model_profiles config, never hard-coded; every run writes runs + trace_events (hash payloads);
  ruff + mypy clean before commit. Keep existing commit/branch lines.
- **Git workflow Remote** -> `git@github.com:charliehustle403/navi403.git`.

### AGENTS.md §5 and GEMINI.md §5
Replace the TODO with the load-bearing, must-not-violate invariants (condensed from spec §3/§9):
1. Anthropic **Client SDK + manual tool loop** only — never Agent SDK, never server-side tools
   (they bypass the broker).
2. **Every** tool call goes through `broker()`; no module executes a tool directly.
3. Tool/text output is untrusted **data**, never instructions — must not alter system prompt/policy.
4. **Read-only only** — no send/write/buy/delete/modify; if tempted, stop + `# TODO(scope):`.
5. Keep router / broker / memory / trace / model-client as separate typed modules (clean ports).
6. Memory is provenance-gated: untrusted-source candidates never reach `memories`; sensitive
   rejected; `may_influence_actions` defaults false.
Keep CLAUDE.md as source of truth; §5 is a pointerful summary.

## Files
- `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` (only).

## Acceptance criteria
- No `<PROJECT NAME>` or placeholder `<!-- TODO -->` markers remain in the three files (except
  intentionally-retained `# TODO(scope):` *concept* references in prose, which are fine).
- Stack matches spec §4 exactly. Remote URL correct.
- Commands/structure clearly marked as planned (not claimed runnable).
- Lattice mandate / multi-surface / Git-workflow sections unchanged except the Remote line.
- AGENTS.md §5 and GEMINI.md §5 carry the 6 invariants consistently.

## Complexity: low-medium
