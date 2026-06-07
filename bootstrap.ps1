<#
.SYNOPSIS
    Bootstrap a new project created from agent-starter-kit.

.DESCRIPTION
    Run once, from the repo root, after creating a repo via "Use this template" and cloning it.
    Initializes the per-project Lattice board, creates and pushes a `dev` branch, and applies
    `main` branch protection (best-effort, requires `gh` auth + admin on the repo).

    The governance docs (CLAUDE.md / AGENTS.md / GEMINI.md) already carry the full Lattice
    mandate, so this skips re-injecting it into CLAUDE.md.

.PARAMETER ProjectName
    Human-readable project name, e.g. "My New Thing".

.PARAMETER ProjectCode
    1-5 uppercase letters for Lattice short IDs, e.g. "MNT" (gives MNT-1, MNT-2, ...).

.PARAMETER Actor
    Default Lattice actor identity. Defaults to human:david.

.PARAMETER Description
    Optional one-line project description stored in Lattice config.

.EXAMPLE
    ./bootstrap.ps1 -ProjectName "My New Thing" -ProjectCode "MNT"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $ProjectName,
    [Parameter(Mandatory = $true)] [ValidatePattern('^[A-Z]{1,5}$')] [string] $ProjectCode,
    [string] $Actor = 'human:david',
    [string] $Description = ''
)

$ErrorActionPreference = 'Stop'

function Info($msg) { Write-Host "  $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  !   $msg" -ForegroundColor Yellow }

function Test-Lattice { [bool](Get-Command lattice -ErrorAction SilentlyContinue) }

# Ensure the Lattice CLI (PyPI package: lattice-tracker) is installed. Prefer uv, then
# pipx, then pip --user. We install the lightweight package, never vendor a binary.
function Ensure-Lattice {
    if (Test-Lattice) { Ok "lattice CLI found ($((lattice --version 2>&1) -replace '[\r\n]+',' '))."; return }

    Info "lattice CLI not found — installing 'lattice-tracker' from PyPI."
    $installed = $false
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Info "Using uv: uv tool install lattice-tracker"
        try { uv tool install lattice-tracker; $installed = $true } catch { Warn "uv install failed: $($_.Exception.Message)" }
    }
    if (-not $installed -and (Get-Command pipx -ErrorAction SilentlyContinue)) {
        Info "Using pipx: pipx install lattice-tracker"
        try { pipx install lattice-tracker; $installed = $true } catch { Warn "pipx install failed: $($_.Exception.Message)" }
    }
    if (-not $installed -and (Get-Command pip -ErrorAction SilentlyContinue)) {
        Info "Using pip: pip install --user lattice-tracker"
        try { pip install --user lattice-tracker; $installed = $true } catch { Warn "pip install failed: $($_.Exception.Message)" }
    }
    if (-not $installed) {
        throw "Could not install lattice-tracker (no uv/pipx/pip found). See GETTING_STARTED.md, install it, then re-run."
    }

    # Re-check: the install dir (e.g. ~/.local/bin) may not be on PATH for this session.
    if (Test-Lattice) {
        Ok "Installed: $((lattice --version 2>&1) -replace '[\r\n]+',' ')."
    } else {
        $binHint = Join-Path $HOME '.local\bin'
        throw "lattice-tracker installed but 'lattice' is not on PATH. Add '$binHint' to PATH (restart the shell), then re-run. See GETTING_STARTED.md."
    }
}

function Test-GitLfs { try { git lfs version *> $null; return ($LASTEXITCODE -eq 0) } catch { return $false } }

# Ensure Git LFS is available and enable it for THIS repo (repo-scoped filters). Best-effort
# binary install; NON-FATAL if it can't be installed — the project still works and the shipped
# .gitattributes takes effect once git-lfs is present.
function Ensure-GitLfs {
    if (-not (Test-GitLfs)) {
        Info "git-lfs not found — attempting best-effort install."
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            try { winget install --id GitHub.GitLFS -e --silent --accept-source-agreements --accept-package-agreements } catch { Warn "winget git-lfs install failed: $($_.Exception.Message)" }
        } elseif (Get-Command brew -ErrorAction SilentlyContinue) {
            try { brew install git-lfs } catch { Warn "brew git-lfs install failed: $($_.Exception.Message)" }
        } elseif (Get-Command apt-get -ErrorAction SilentlyContinue) {
            try { sudo apt-get update; sudo apt-get install -y git-lfs } catch { Warn "apt git-lfs install failed: $($_.Exception.Message)" }
        } else {
            Warn "No package manager (winget/brew/apt) found to auto-install git-lfs."
        }
    }
    if (Test-GitLfs) {
        git lfs install --local | Out-Null
        Ok "Git LFS enabled for this repo ($((git lfs version) -replace '[\r\n]+',' '))."
    } else {
        Warn "git-lfs unavailable — skipped 'git lfs install'. Install it (see GETTING_STARTED.md); the shipped .gitattributes takes effect once it's present."
    }
}

Write-Host "`nBootstrapping '$ProjectName' ($ProjectCode)`n" -ForegroundColor White

# --- Pre-flight -----------------------------------------------------------
if (-not (Test-Path '.git')) {
    throw "No .git here. Run this from the repo root of your new (cloned) project."
}
Ensure-Lattice
Ensure-GitLfs
if (Test-Path '.lattice') {
    Warn ".lattice already exists — skipping 'lattice init' (already bootstrapped?)."
    $skipLattice = $true
} else {
    $skipLattice = $false
}

# --- 1. dev branch --------------------------------------------------------
$branches = (git branch --format '%(refname:short)') -split "`n"
if ($branches -contains 'dev') {
    Info "Branch 'dev' already exists — switching to it."
    git switch dev | Out-Null
} else {
    Info "Creating 'dev' branch off current HEAD."
    git switch -c dev | Out-Null
}
Ok "On branch dev."

# --- 2. Lattice init ------------------------------------------------------
if (-not $skipLattice) {
    Info "Initializing Lattice board (classic workflow)."
    $initArgs = @(
        'init',
        '--project-code', $ProjectCode,
        '--project-name', $ProjectName,
        '--actor', $Actor,
        '--workflow', 'classic',
        '--no-setup-claude',   # mandate already lives in CLAUDE.md
        '--no-setup-agents'    # AGENTS.md already present
    )
    if ($Description) { $initArgs += @('--description', $Description) }
    & lattice @initArgs
    Ok "Lattice board created (project code $ProjectCode)."

    Info "Committing Lattice board on dev."
    git add -A
    git commit -m "chore: bootstrap Lattice board ($ProjectCode)" | Out-Null
    Ok "Committed."
}

# --- 3. Push dev (if a remote exists) ------------------------------------
$originUrl = (git remote get-url origin 2>$null)
if ($originUrl) {
    Info "Pushing dev to origin."
    git push -u origin dev | Out-Null
    Ok "dev pushed and tracking origin/dev."
} else {
    Warn "No 'origin' remote — skipping push and branch protection. Add a remote, then push dev."
}

# --- 4. main branch protection (best-effort) -----------------------------
if ($originUrl -and ($originUrl -match 'github\.com[:/]([^/]+)/(.+?)(?:\.git)?$')) {
    $owner = $Matches[1]; $repo = $Matches[2]
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        Info "Applying branch protection to $owner/$repo : main."
        $protection = [ordered]@{
            required_status_checks        = $null
            enforce_admins                = $true
            required_pull_request_reviews = [ordered]@{
                required_approving_review_count = 0
                dismiss_stale_reviews           = $false
                require_code_owner_reviews      = $false
            }
            restrictions                  = $null
            allow_force_pushes            = $false
            allow_deletions               = $false
        } | ConvertTo-Json -Depth 6
        $tmp = New-TemporaryFile
        try {
            Set-Content -Path $tmp -Value $protection -Encoding utf8
            gh api -X PUT "repos/$owner/$repo/branches/main/protection" --input $tmp | Out-Null
            Ok "main protected: PRs only, force-push + deletion blocked, admins enforced."
        } catch {
            Warn "Branch protection failed ($($_.Exception.Message)). Apply manually in repo Settings -> Branches."
        } finally {
            Remove-Item $tmp -ErrorAction SilentlyContinue
        }
    } else {
        Warn "gh CLI not found — skipping branch protection. Apply manually in repo Settings -> Branches."
    }
}

# --- Done -----------------------------------------------------------------
Write-Host "`nDone. Next steps:" -ForegroundColor White
Write-Host "  1. Fill in CLAUDE.md placeholders (<PROJECT NAME>, Stack, Commands, Structure, Remote)."
Write-Host "  2. Fill in section 5 'Project specifics' of AGENTS.md and GEMINI.md."
Write-Host "  3. Track that edit as your first Lattice task:"
Write-Host "       lattice create `"Fill in project docs`" --actor $Actor" -ForegroundColor DarkGray
Write-Host "  4. Develop on dev; promote to main via PR."
Write-Host "  5. Optional: install peon-ping for agent voice notifications - see GETTING_STARTED.md (section 5)."
Write-Host "  Git LFS is enabled and .gitattributes is ready - track more types with: git lfs track `"*.ext`"" -ForegroundColor DarkGray
Write-Host ""
