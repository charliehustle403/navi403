# AGENTS.md — working agreement for ALL agents in this repo

> This file binds **every** AI agent that works in this repo — Codex, Cursor, Gemini,
> Claude, and any future tool — to the same discipline. `CLAUDE.md` is the **canonical,
> full source of truth**; read it in full before doing anything. The rules below are the
> non-negotiable summary and apply to you regardless of which tool you are.

## 1. Lattice is mandatory — no untracked work

This project uses **Lattice** (file-based, event-sourced task tracking in `.lattice/`).
If you are about to write code and no Lattice task exists for it, **stop and create one first**.
Untracked work is a coordination failure: other agents and humans cannot see, build on, or
trust it.

```
lattice create "<title>" --actor agent:<your-id>
```

Use a tool-specific actor id so the event log shows who did what: `agent:codex`,
`agent:gemini`, `agent:claude-opus-4`, etc.

## 2. The lifecycle: plan FIRST, then implement, then review

Every task that produces commits moves through this lifecycle. **Update status BEFORE you
do the work, not after** — if the board says `backlog` but you're coding, the board is lying.

```
backlog → in_planning → planned → in_progress → review → done
                                       ↕            ↕
                                    blocked      needs_human
```

```
lattice status <task> <status> --actor agent:<your-id>
```

- **`in_planning`** — before you open the first file. Then explore the code and **write a
  real plan** to `.lattice/plans/<full-task-id>.md` (scope, approach, key files, acceptance
  criteria). Even trivial tasks get a one-line plan.
- **`planned`** — only once the plan file has real content (the CLI blocks `in_progress`
  while the plan is still empty scaffold).
- **`in_progress`** — before you write the first line of code. Implement, test, commit.
- **`review`** — when implementation is complete. Then **actually review**: ideally with
  fresh context (an agent/pass that did NOT write the code), read the plan + the git diff,
  run tests/lint, check against acceptance criteria, and record findings:
  `lattice comment <task> --role review --actor agent:<your-id> "<what you reviewed/found>"`.
- **`done`** — only after a review has been performed and recorded.

If the plan was wrong → back to `in_planning`. If only the implementation was wrong →
back to `in_progress`. See `CLAUDE.md` for the full rework loop and the 3-cycle safety valve.

Leave breadcrumbs: `lattice comment` for decisions/what you tried; `.lattice/notes/<id>.md`
for working notes. The record you leave is the next agent's only context.

## 3. Git: dev→main transport workflow

- **Develop on `dev`.** Test there. Never commit experimental work directly to `main`.
- **`main` is production and branch-protected** — direct pushes are blocked (admins
  included); promote `dev → main` via a Pull Request only.
- Commit small and often with clear messages; push regularly (the remote is the source of
  truth across the user's devices).
- **Never** run destructive/irreversible git ops (force-push, history rewrite, branch
  deletion, `git reset --hard`) without explicit confirmation in the chat.

## 4. Shared-worktree discipline

Multiple agents may work this repo concurrently. If you encounter changes you didn't make,
**investigate before you touch** (`git log`, `lattice list`) — it's almost certainly another
agent's legitimate work. Never revert/reset/delete changes you can't attribute.

## 5. Project specifics

<!-- TODO: replace with this project's architecture, key invariants, and any module
     dependency rules a new agent must not violate. Keep CLAUDE.md as the source of truth
     and summarize the load-bearing constraints here. -->
- Read `CLAUDE.md` (Stack / Project structure / Conventions) before writing code.

---

*Full mandate, rework loop, sub-agent execution model, and project conventions: see `CLAUDE.md`.*
