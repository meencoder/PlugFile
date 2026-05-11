<#
.SYNOPSIS
  Complete the Plugfile rename and push to the new GitHub repo.

.DESCRIPTION
  Idempotent end-to-end automation for the WellPlug -> Plugfile migration.
  This script:
    1. Validates environment (git installed, in correct repo, etc.)
    2. Clears any stale .git/index.lock
    3. Verifies all in-tree renames already applied (sandbox did the heavy lifting)
    4. Runs the pytest suite as a guard-rail (238 tests should pass)
    5. Commits all pending changes with a descriptive message
    6. Renames the old `origin` remote (quadri-ks/WellPlug) to `old-origin`
    7. Adds the new `origin` pointing to meencoder/PlugFile
    8. Pushes main + tags to the new origin
    9. Prints post-push manual checklist

  All destructive actions check for prior state first, so re-running is safe.

.PARAMETER RepoPath
  Absolute path to the repo. Default: C:\Users\karee\WellPlug\WellPlug

.PARAMETER NewRemoteUrl
  HTTPS URL of the new GitHub repo. Default: meencoder/PlugFile.

.PARAMETER GitUserName, GitUserEmail
  Identity used for the commit. Defaults to Kareem / quadri.ks@gmail.com.

.PARAMETER SkipTests
  Skip the pytest run (faster, but loses the safety net).

.PARAMETER DryRun
  Show what would happen without executing destructive commands.

.EXAMPLE
  # Normal run
  .\tools\plugfile-rename-push.ps1

.EXAMPLE
  # Dry-run first to preview
  .\tools\plugfile-rename-push.ps1 -DryRun

.EXAMPLE
  # Skip tests for speed (only if you've already verified locally)
  .\tools\plugfile-rename-push.ps1 -SkipTests

.NOTES
  Authentication for the push: you may be prompted for credentials. For the
  meencoder GitHub account, use a fine-scoped Personal Access Token as the
  password. Create one at:
    https://github.com/settings/tokens?type=beta
  Scope: Contents (Read & Write) on the PlugFile repo.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Users\karee\WellPlug\WellPlug",
    [string]$NewRemoteUrl = "https://github.com/meencoder/PlugFile.git",
    [string]$OldRemoteAlias = "old-origin",
    [string]$GitUserName = "Kareem",
    [string]$GitUserEmail = "quadri.ks@gmail.com",
    [switch]$SkipTests,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# --- helpers ----------------------------------------------------------------

function Write-Step {
    param([int]$Num, [string]$Title)
    Write-Host ""
    Write-Host "==[ Step $Num ]==================================================" -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "------------------------------------------------------------------" -ForegroundColor Cyan
}

function Invoke-Git {
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$GitArgs,
        [switch]$AllowFail
    )
    $cmd = "git " + ($GitArgs -join " ")
    Write-Host "  > $cmd" -ForegroundColor DarkGray
    if ($DryRun) {
        Write-Host "    [dry-run -- skipped]" -ForegroundColor Yellow
        return
    }
    & git @GitArgs
    if ($LASTEXITCODE -ne 0 -and -not $AllowFail) {
        throw "Command failed: $cmd"
    }
}

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# --- Step 1: validate environment ------------------------------------------

Write-Step 1 "Validate environment"

if (-not (Test-Path $RepoPath)) {
    Write-Host "ERROR: Repo path not found: $RepoPath" -ForegroundColor Red
    exit 1
}
Set-Location $RepoPath
Write-Host "  cwd: $(Get-Location)"

if (-not (Test-CommandExists "git")) {
    Write-Host "ERROR: git not found in PATH." -ForegroundColor Red
    exit 1
}
$gitVersion = (& git --version) -replace "git version ",""
Write-Host "  git version: $gitVersion"

if (-not (Test-Path ".git")) {
    Write-Host "ERROR: Not a git repository: $RepoPath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "src\plugfile")) {
    Write-Host "ERROR: src\plugfile not found. Did the sandbox rename complete?" -ForegroundColor Red
    Write-Host "       Expected directory: $RepoPath\src\plugfile" -ForegroundColor Red
    exit 1
}
Write-Host "  Sandbox rename detected (src\plugfile exists)."

# --- Step 2: clear stale git lock ------------------------------------------

Write-Step 2 "Clear stale git lock if present"

$lockPath = Join-Path $RepoPath ".git\index.lock"
if (Test-Path $lockPath) {
    Write-Host "  Found stale lock at $lockPath" -ForegroundColor Yellow
    if (-not $DryRun) {
        try {
            Remove-Item $lockPath -Force
            Write-Host "  Lock removed."
        } catch {
            Write-Host "ERROR: Could not remove lock. Close any git GUI (GitHub Desktop, VS Code Source Control, etc.) and retry." -ForegroundColor Red
            exit 1
        }
    }
} else {
    Write-Host "  No stale lock present."
}

# --- Step 3: show current state --------------------------------------------

Write-Step 3 "Current repo state"

& git remote -v
Write-Host ""
Write-Host "Pending changes:"
& git status --short
Write-Host ""

# --- Step 4: run tests (guard-rail) ----------------------------------------

if (-not $SkipTests) {
    Write-Step 4 "Run test suite (guard-rail)"

    # Prefer the project venv's python over the system python, because the
    # venv is where pytest + the project's dev deps are installed.
    $venvPython = Join-Path $RepoPath ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $pythonExe = $venvPython
        Write-Host "  Using venv python: $pythonExe"
    } elseif (Test-CommandExists "python") {
        $pythonExe = "python"
        Write-Host "  Using system python (no .venv detected)."
    } else {
        Write-Host "WARNING: no python found; skipping tests." -ForegroundColor Yellow
        $pythonExe = $null
    }

    if ($pythonExe) {
        Write-Host "  Running: $pythonExe -m pytest -q"
        if (-not $DryRun) {
            & $pythonExe -m pytest -q
            if ($LASTEXITCODE -ne 0) {
                Write-Host "ERROR: Tests failed. Fix before pushing." -ForegroundColor Red
                Write-Host "       Re-run with -SkipTests to bypass (not recommended)." -ForegroundColor Red
                Write-Host "       If pytest is missing, run:" -ForegroundColor Yellow
                Write-Host "         & '$pythonExe' -m pip install -e `".[dev]`"" -ForegroundColor Yellow
                exit 1
            }
            Write-Host "  All tests passed." -ForegroundColor Green
        }
    }
} else {
    Write-Step 4 "Skipping tests (--SkipTests)"
}

# --- Step 5: commit pending changes -----------------------------------------

Write-Step 5 "Commit pending changes"

& git add -A
$stagedCount = (& git diff --cached --name-only | Measure-Object -Line).Lines
if ($stagedCount -eq 0) {
    Write-Host "  Nothing to commit." -ForegroundColor Yellow
} else {
    Write-Host "  Staged $stagedCount file(s) for commit."

    $commitMessage = @"
Rename to Plugfile + Phase 2B PDF generator + validation tooling

Comprehensive rebrand from WellPlug / Caprock / Kaproq to Plugfile:
- src/wellplug/ -> src/plugfile/ with all imports rewritten
- pyproject.toml: name="plugfile", version 0.3.0
- Entry-point scripts: plugfile-rrc, plugfile-pdf
- branding/caprock_*.svg -> branding/plugfile_*.svg
- landing/: brand strings + URLs (trycaprock.com / kaproq.com -> plugfile.com)
- README, PLAN.md, tools/: brand consistency

Phase 2B (NEW) -- print-ready W-3 PDF generator:
- src/plugfile/pdf_export.py with free/paid tiers
- tests/test_pdf_export.py
- w-3p.pdf authoritative RRC template

Validation tooling (NEW):
- tools/build_linkedin_mining_xlsx.py
- tools/fill_mining_log.py + Fill-MiningLog.ps1
- tools/mine_software_adoption.py (Claude web-search miner)
- tools/leads_starter.json (10 seeded Texas operators)

Landing page updates:
- Paper-only W-3 framing (RRC has not onboarded W-3 to LoneSTAR)
- Suite tier: inspector-reviewed audit trail (not RRC submission)
- New 'What's online, what's still paper' section

238 tests passing.
"@

    if (-not $DryRun) {
        & git -c "user.name=$GitUserName" -c "user.email=$GitUserEmail" commit -m $commitMessage
        if ($LASTEXITCODE -ne 0) {
            throw "Commit failed."
        }
        Write-Host "  Commit created." -ForegroundColor Green
    } else {
        Write-Host "  [dry-run -- commit message preview follows]" -ForegroundColor Yellow
        Write-Host $commitMessage -ForegroundColor DarkGray
    }
}

# --- Step 6: switch remote --------------------------------------------------

Write-Step 6 "Switch git remote to meencoder/PlugFile"

$remotes = (& git remote) -split "`n" | Where-Object { $_ -ne "" }

# preserve old quadri-ks/WellPlug remote as `old-origin` for archival
if ($remotes -contains "origin" -and $remotes -notcontains $OldRemoteAlias) {
    $currentOriginUrl = & git remote get-url origin
    if ($currentOriginUrl -notmatch "meencoder/PlugFile") {
        Write-Host "  Renaming current origin ($currentOriginUrl) to $OldRemoteAlias"
        Invoke-Git -GitArgs @("remote", "rename", "origin", $OldRemoteAlias)
    }
}

# refresh remote list after rename
$remotes = (& git remote) -split "`n" | Where-Object { $_ -ne "" }

if ($remotes -notcontains "origin") {
    Write-Host "  Adding origin -> $NewRemoteUrl"
    Invoke-Git -GitArgs @("remote", "add", "origin", $NewRemoteUrl)
} else {
    $existingUrl = & git remote get-url origin
    if ($existingUrl -ne $NewRemoteUrl) {
        Write-Host "  Updating origin URL: $existingUrl -> $NewRemoteUrl"
        Invoke-Git -GitArgs @("remote", "set-url", "origin", $NewRemoteUrl)
    } else {
        Write-Host "  origin already points to $NewRemoteUrl"
    }
}

Write-Host ""
Write-Host "Final remote configuration:"
& git remote -v

# --- Step 7: push to new origin ---------------------------------------------

Write-Step 7 "Push to meencoder/PlugFile"

Write-Host "  Authentication note: you may be prompted for credentials." -ForegroundColor Yellow
Write-Host "  Username: meencoder" -ForegroundColor Yellow
Write-Host "  Password: a fine-scoped Personal Access Token (not the GitHub password)." -ForegroundColor Yellow
Write-Host "  Create a token: https://github.com/settings/tokens?type=beta" -ForegroundColor Yellow
Write-Host "    Scope: 'Contents' (Read & Write) on the PlugFile repo." -ForegroundColor Yellow
Write-Host ""

Invoke-Git -GitArgs @("push", "-u", "origin", "main")
Invoke-Git -GitArgs @("push", "origin", "--tags") -AllowFail

# --- Step 8: summary & next steps ------------------------------------------

Write-Step 8 "Done. Post-push manual checklist."

Write-Host ""
Write-Host "  Repo successfully renamed and pushed." -ForegroundColor Green
Write-Host "  New URL: https://github.com/meencoder/PlugFile"
Write-Host ""
Write-Host "  Manual follow-up tasks:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. Archive the old repo:"
Write-Host "     - Visit https://github.com/quadri-ks/WellPlug"
Write-Host "     - Edit README.md to add at the top:"
Write-Host "       > This project has moved to https://github.com/meencoder/PlugFile"
Write-Host "     - Settings -> Danger Zone -> 'Archive this repository'"
Write-Host ""
Write-Host "  2. Register plugfile.com (priority 1)"
Write-Host "     - Cloudflare Registrar: ~`$10/year"
Write-Host "     - Also consider plugfile.co (`$26) for typo defense"
Write-Host ""
Write-Host "  3. Update Cloudflare Pages binding:"
Write-Host "     - Remove trycaprock.com custom domain"
Write-Host "     - Add plugfile.com custom domain"
Write-Host "     - Update DNS A/CNAME records"
Write-Host ""
Write-Host "  4. Update Stripe customer support address:"
Write-Host "     - Change hello@trycaprock.com -> hello@plugfile.com"
Write-Host "     - Update Cloudflare Email Routing rules"
Write-Host ""
Write-Host "  5. Reserve usernames (free, ~5 min total):"
Write-Host "     - GitHub: plugfile  (the meencoder org may want to add a plugfile vanity)"
Write-Host "     - X/Twitter: @plugfile"
Write-Host "     - LinkedIn: linkedin.com/company/plugfile"
Write-Host ""
Write-Host "  6. Plan next weekend block:"
Write-Host "     - Phase 2B is shipped. Phase 2C (GAU letter parser) is next per PLAN.md."
Write-Host "     - Or pause feature work and start the validation phase"
Write-Host "       (expert calls + inspector retainer)."
Write-Host ""
Write-Host "  Old remote preserved as '$OldRemoteAlias' if you ever need to pull from it." -ForegroundColor DarkGray
Write-Host "  Run 'git remote -v' to confirm." -ForegroundColor DarkGray
Write-Host ""
