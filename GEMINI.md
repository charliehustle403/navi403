# GEMINI.md — working agreement for Gemini in this repo

> Gemini, you are bound by the **same** working agreement as every other agent in this repo.
> The canonical cross-agent rules are in **`AGENTS.md`**; the full source of truth is
> **`CLAUDE.md`**. **Read both in full before doing anything.** The non-negotiable summary
> below applies to you.

## 1. Lattice is mandatory — no untracked work

Work is tracked in **Lattice** (`.lattice/`). If you're about to write code and no Lattice
task exists for it, **stop and create one first**:

```
lattice create "<title>" --actor agent:gemini
```

Always attribute with `--actor agent:gemini` so the event log shows your work.

## 2. The lifecycle: plan FIRST, then implement, then review

**Update status BEFORE doing the work, not after.**

```
backlog → in_planning → planned → in_progress → review → done
                                       ↕            ↕
                                    blocked      needs_human
```

```
lattice status <task> <status> --actor agent:gemini
```

- **`in_planning`** — before opening the first file. Write a real plan to
  `.lattice/plans/<full-task-id>.md` (scope, approach, key files, acceptance criteria).
- **`planned`** — only once the plan file has real content (CLI blocks `in_progress` on
  empty-scaffold plans).
- **`in_progress`** — before the first line of code. Implement, test, commit.
- **`review`** — when implementation is complete; review against the plan with fresh eyes,
  run tests/lint, then record findings:
  `lattice comment <task> --role review --actor agent:gemini "<what you reviewed/found>"`.
- **`done`** — only after a review has been performed and recorded.

Plan wrong → back to `in_planning`. Implementation wrong → back to `in_progress`.
Leave breadcrumbs with `lattice comment`. Full rework loop: see `CLAUDE.md`.

## 3. Git: dev→main transport workflow

- Develop on **`dev`**; never commit experimental work directly to `main`.
- **`main` is production and branch-protected** — promote `dev → main` via Pull Request only.
- Commit small/often with clear messages; push regularly.
- **Never** force-push, rewrite history, delete branches, or `git reset --hard` without
  explicit confirmation in the chat.

## 4. Shared-worktree discipline

Other agents may be working concurrently. If you see changes you didn't make, **investigate
before touching** (`git log`, `lattice list`). Never revert/reset/delete work you can't attribute.

## 5. Project specifics

<!-- TODO: replace with this project's architecture, key invariants, and module dependency
     rules a new agent must not violate. CLAUDE.md is the source of truth. -->
Read `CLAUDE.md` (Stack / Project structure / Conventions) before writing code.

---

*Canonical cross-agent rules: `AGENTS.md`. Full mandate and conventions: `CLAUDE.md`.*
