# agent-starter-kit

A **GitHub template repository** that bootstraps a new project with multi-agent governance
already wired in:

- **Multi-surface workflow** (`CLAUDE.md`) — concise/mobile-friendly defaults, plan-before-
  big-changes, confirm-before-destructive, tuned for driving sessions from terminal + phone.
- **Cross-agent governance** (`AGENTS.md`, `GEMINI.md`) — binds Claude, Codex, Gemini, and
  any future tool to the same **plan → implement → review** lifecycle.
- **Lattice** task tracking — the full mandate ships in `CLAUDE.md`; `bootstrap.ps1` creates
  the per-project board.
- **dev/main transport workflow** — develop on `dev`, promote to `main` via PR; `main` is
  branch-protected.
- **Optional:** [peon-ping](https://github.com/charliehustle403/peon-ping) agent voice
  notifications — recommended; install steps in [GETTING_STARTED.md §5](GETTING_STARTED.md).

## What's inside

| File | Purpose | Per-project action |
|------|---------|--------------------|
| `CLAUDE.md` | Working agreement + full Lattice mandate | Fill in `<PROJECT NAME>`, Stack, Commands, Structure, Conventions, Remote |
| `AGENTS.md` | Cross-agent rules (Codex/Cursor/etc.) | Fill in §5 "Project specifics" |
| `GEMINI.md` | Gemini-specific mirror | Fill in §5 "Project specifics" |
| `.gitignore` | Sensible Python/Node defaults + `.lattice/locks/` + secrets | usually none |
| `.gitattributes` | Git LFS tracking for large/binary files (media, model weights, datasets) | add patterns with `git lfs track` |
| `bootstrap.ps1` | One-command project init (Lattice + Git LFS + dev branch + branch protection) | run once |
| `README.md` | This file | replace with your project's README |

> **Not included on purpose:** no `.lattice/` board and no inherited git history. Each new
> project gets a fresh Lattice board (right project code) and its own clean history — that's
> the whole point of using a *template* rather than copying a repo.

## How to start a new project

> **New machine?** First install the toolchain (Git, Python, Node/npm, uv, `gh`) and an agent
> CLI (Claude Code or Codex). Step-by-step, Windows-first: **[GETTING_STARTED.md](GETTING_STARTED.md)**.

1. On GitHub, click **“Use this template” → Create a new repository** (gives you a fresh
   repo with no shared history). Then clone it locally.
2. From the repo root, run the bootstrap.

   **Windows (Command Prompt):**

   ```bat
   powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 -ProjectName "My New Thing" -ProjectCode "MNT"
   ```

   **Linux** (PowerShell 7): `pwsh ./bootstrap.ps1 -ProjectName "My New Thing" -ProjectCode "MNT"`

   This will:
   - **install the Lattice CLI** (`lattice-tracker` from PyPI) if it isn't already present,
   - `lattice init` with the `classic` workflow and your project code (docs already carry
     the mandate, so it skips re-injecting it),
   - create + push a `dev` branch,
   - apply `main` branch protection via `gh` (best-effort; needs `gh` auth + admin).
3. Fill in the `CLAUDE.md` placeholders (`<PROJECT NAME>`, Stack, Commands, Structure,
   Remote) and §5 of `AGENTS.md`/`GEMINI.md`. Track that edit as your first Lattice task.
4. Develop on `dev`. Promote to `main` via PR when ready.

## Requirements

Full setup walkthrough: **[GETTING_STARTED.md](GETTING_STARTED.md)**. In short:

- Git, Python 3.11+, Node.js 18+ / npm, and [`uv`](https://docs.astral.sh/uv/)
- The **Lattice** CLI (`lattice-tracker`) — `bootstrap.ps1` installs it automatically if missing
- [`gh`](https://cli.github.com/) authenticated (`gh auth status`) — for the branch-protection step
- An agent CLI: **Claude Code** and/or **Codex** (install steps in GETTING_STARTED.md)
- PowerShell 7+ to run `bootstrap.ps1` (Windows-first; steps are trivial to run by hand elsewhere)
