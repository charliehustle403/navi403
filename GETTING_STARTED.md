# Getting Started — set up your machine

This guide gets a **fresh machine** ready to develop on a project created from this template,
driving the work with an AI coding agent (**Claude Code** or **Codex**). Every step is written
**Windows first, then Linux** (macOS noted where it differs).

> TL;DR (Windows): open **Command Prompt**, install Git + Python + Node.js + uv + GitHub CLI +
> Git LFS, install an agent (Claude Code or Codex), then run the bootstrap. The bootstrap installs
> the **Lattice** CLI for you.

---

## Before you begin — open your terminal

You'll type the install commands into a terminal window. Open it first:

- **Windows — open Command Prompt:** press the **Windows key**, type `cmd`, and press **Enter**.
  A black window appears — **that's where every Windows command in this guide goes.**
  (If a command later says it needs admin rights, close it, right-click *Command Prompt*, and
  choose *Run as administrator*.)
- **Linux — open Terminal:** on Ubuntu press `Ctrl` + `Alt` + `T`.

---

## 1. Core toolchain

| Tool | Why you need it | Verify |
|------|-----------------|--------|
| **Git** | version control; the agent drives commits/branches | `git --version` |
| **Python 3.11+** | runtime for Python projects **and** for the Lattice CLI | `python --version` |
| **Node.js 18+ LTS + npm** | runtime for JS/TS projects and for installing agent CLIs | `node --version` / `npm --version` |
| **uv** | fast Python package/tool manager; installs Lattice cleanly | `uv --version` |
| **GitHub CLI (`gh`)** | repo creation + branch protection (used by `bootstrap.ps1`) | `gh --version` |
| **Git LFS** | versions large/binary files (media, models, datasets) — the kit ships a `.gitattributes` and `bootstrap.ps1` runs `git lfs install` | `git lfs version` |

### Windows (in Command Prompt)

`winget` ships with Windows 10/11. In your Command Prompt window, run these one at a time:

```bat
winget install --id Git.Git -e
winget install --id Python.Python.3.13 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id astral-sh.uv -e
winget install --id GitHub.cli -e
winget install --id GitHub.GitLFS -e
```

Then **close Command Prompt and open a new one** (Win key → `cmd` → Enter) so the freshly installed
tools are picked up. (The Git for Windows installer can also bundle Git LFS — if `git lfs version`
already works, skip that last line.)

### Linux (Debian/Ubuntu)

```bash
sudo apt update && sudo apt install -y git git-lfs python3 python3-pip nodejs npm
curl -LsSf https://astral.sh/uv/install.sh | sh        # uv
# GitHub CLI: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
```

> **macOS:** use Homebrew — `brew install git git-lfs python node uv gh`.

> **Git LFS:** after installing the binary, run `git lfs install` once (per user) to register the
> LFS filters. `bootstrap.ps1` also runs `git lfs install --local` for the project. The kit's
> `.gitattributes` already routes common large/binary types (audio, video, archives, model
> weights, columnar data) through LFS — add more with `git lfs track "*.ext"`.

---

## 2. The Lattice CLI (task tracking)

This template **requires** Lattice — it's how every agent tracks work (see `CLAUDE.md`).
`bootstrap.ps1` installs it automatically, but to install it yourself the command is the **same on
Windows (Command Prompt) and Linux**:

```bat
uv tool install lattice-tracker      :: provides `lattice` and `lattice-mcp`
:: fallbacks if you don't use uv:
::   pipx install lattice-tracker
::   pip install --user lattice-tracker
```

Verify: `lattice --version` (expect `lattice, version 0.2.0` or newer).

### Fallback: install from source (Git)

If PyPI is blocked or `bootstrap.ps1` can't install Lattice for some reason, install it straight
from the Git source instead (same command on Windows and Linux):

```bat
uv tool install git+https://github.com/charliehustle403/lattice.git
:: equivalents:
::   pipx install git+https://github.com/charliehustle403/lattice.git
::   pip install --user git+https://github.com/charliehustle403/lattice.git
:: SSH form (if you have a key set up):
::   uv tool install git+ssh://git@github.com/charliehustle403/lattice.git
```

> **Note:** [`charliehustle403/lattice`](https://github.com/charliehustle403/lattice.git) is a
> **public** repo (MIT), so this fallback works for anyone — no GitHub sign-in required. It
> mirrors the public upstream [`Stage-11-Agentics/lattice`](https://github.com/Stage-11-Agentics/lattice);
> either source works (`uv tool install git+https://github.com/Stage-11-Agentics/lattice.git`).

> **PATH note:** uv/pipx/pip install console scripts to `~/.local/bin` (Windows:
> `%USERPROFILE%\.local\bin`). If `lattice` isn't found after install, add that folder to PATH
> and open a new terminal.

---

## 3. An AI coding agent

Install at least one. Both need **Node.js 18+** (installed above). After installing, run the tool
once to sign in.

### Claude Code (Anthropic)

**Windows (Command Prompt):**

```bat
npm install -g @anthropic-ai/claude-code
:: alternative (native installer):
::   powershell -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
```

**Linux:**

```bash
curl -fsSL https://claude.ai/install.sh | bash
#   or: npm install -g @anthropic-ai/claude-code
```

Verify: `claude --version`. Start it in a project with `claude`. First run opens a browser to
sign in to your Anthropic account.

### Codex (OpenAI)

**Windows (Command Prompt):**

```bat
npm install -g @openai/codex
```

**Linux:**

```bash
npm install -g @openai/codex
#   or native: curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

Verify: `codex --version`. Authenticate with `codex` (sign in with a ChatGPT plan or an OpenAI
API key).

> Codex reads `AGENTS.md`; Claude Code reads `CLAUDE.md`; Gemini reads `GEMINI.md`. This
> template ships all three so whichever agent you use follows the same lifecycle.

---

## 4. Verify everything

Run these in your terminal (Command Prompt on Windows, Terminal on Linux) — one per line:

```bat
git --version
python --version
node --version
npm --version
uv --version
gh --version
git lfs version
lattice --version
claude --version
codex --version
gh auth status
```

All printing versions? You're ready. If `gh auth status` says you're not logged in, run
`gh auth login` and follow the prompts.

---

## 5. Optional: peon-ping — agent voice notifications

Stop babysitting the terminal. **[peon-ping](https://github.com/charliehustle403/peon-ping)**
plays Warcraft / StarCraft / Portal / Zelda voice lines and on-screen banners when your AI agent
finishes or needs permission — for **Claude Code, Codex, Cursor, Gemini**, and more. Optional, but
genuinely useful when an agent runs long. MIT-licensed.

It installs **globally by default**, so the hooks fire in *every* project (not just ones from this
template) — install it once per machine.

**Windows (Command Prompt):**

```bat
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/charliehustle403/peon-ping/main/install.ps1 | iex"
```

**Linux / WSL2** (macOS: same command):

```bash
curl -fsSL https://raw.githubusercontent.com/charliehustle403/peon-ping/main/install.sh | bash
```

Prefer to inspect first? Clone it, then run the installer for your OS:

```bat
git clone https://github.com/charliehustle403/peon-ping.git
cd peon-ping
```

- **Windows (Command Prompt):** `powershell -ExecutionPolicy Bypass -File .\install.ps1`
- **Linux / macOS:** `./install.sh`

- **Per-project instead of global:** on Windows add `-Local` (e.g. `.\install.ps1 -Local`) to
  install hooks/skills into *this* project's `./.claude/` only.
- **Pick your sound packs** interactively at [peonping.com](https://peonping.com/#picker).
- **Control it:** the `peon` CLI manages config (`peon --help`); in an agent session the
  `/peon-ping-toggle` and `/peon-ping-use` skills mute/unmute and switch voices.

> Source repo: [charliehustle403/peon-ping](https://github.com/charliehustle403/peon-ping).

---

## 6. Start the project

1. On GitHub, open the template repo and click **“Use this template” → Create a new repository**
   (your own copy, with clean history).
2. Clone it and enter the folder (same on Windows and Linux):

   ```bat
   git clone <your-new-repo-url>
   cd <your-new-repo>
   ```

3. Run the bootstrap from inside that folder.

   **Windows (Command Prompt):**

   ```bat
   powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 -ProjectName "My New Thing" -ProjectCode "MNT"
   ```

   **Linux** (needs PowerShell 7 — `sudo apt install -y powershell`, or
   [install docs](https://learn.microsoft.com/powershell/scripting/install/installing-powershell)):

   ```bash
   pwsh ./bootstrap.ps1 -ProjectName "My New Thing" -ProjectCode "MNT"
   ```

   It installs Lattice, creates the Lattice board, makes a `dev` branch, enables Git LFS, and
   protects `main`. See `README.md` for details and the per-project checklist.

> No PowerShell available? Run the equivalent by hand: `lattice init --workflow classic
> --project-code MNT --project-name "My New Thing" --actor human:you`, then `git switch -c dev`.
