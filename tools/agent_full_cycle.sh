#!/usr/bin/env bash
# =============================================================================
# PlugFile agent full-cycle orchestrator.
#
# Idempotent end-to-end automation of: (a) merge the latest agent PR if green,
# (b) bump the workflow turn caps to known-good values, (c) ensure the next
# backlog issue exists, (d) run the Builder -> Verifier dry-run on it.
#
# REQUIRES gh authenticated with WRITE on meencoder/PlugFile (i.e. a PAT with
# `repo` + `workflow` scope set as GH_TOKEN, or `gh auth login` as meencoder).
#
# Usage:
#   bash tools/agent_full_cycle.sh                    # default scenario: health
#   bash tools/agent_full_cycle.sh health|phone|normalize
#   bash tools/agent_full_cycle.sh 9                  # dispatch on existing issue #9
#
# Each step prints whether it acted or skipped. The script can be re-run safely.
# =============================================================================
set -uo pipefail

SCENARIO="${1:-health}"
LABEL="agent:build"

say(){ printf '\n\033[1m== %s\033[0m\n' "$*"; }
die(){ printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# Ensure gh is on PATH. PowerShell-spawned bash often doesn't inherit it.
if ! command -v gh >/dev/null 2>&1; then
  # Quoted paths first (literal locations), then unquoted globs (winget installs).
  for p in \
    "/c/Program Files/GitHub CLI/gh.exe" \
    "/c/Program Files (x86)/GitHub CLI/gh.exe" \
    "$HOME/AppData/Local/Programs/GitHub CLI/gh.exe" \
    "$HOME/AppData/Local/GitHubCLI/gh.exe" \
    "$HOME/scoop/shims/gh.exe" \
    "$HOME/scoop/apps/gh/current/gh.exe" \
    $HOME/AppData/Local/Microsoft/WinGet/Packages/GitHub.cli_*/gh_*/bin/gh.exe \
    /c/Users/*/AppData/Local/Microsoft/WinGet/Packages/GitHub.cli_*/gh_*/bin/gh.exe \
  ; do
    if [ -x "$p" ]; then export PATH="$(dirname "$p"):$PATH"; break; fi
  done
fi
command -v gh >/dev/null 2>&1 || die "gh CLI not on PATH in this bash.
  EASIEST FIX: open Git Bash directly (Start menu -> Git Bash) and re-run.
  Or run 'where.exe gh' in PowerShell, then add that folder to this bash's PATH."
command -v jq >/dev/null 2>&1 || die "jq not on PATH. Install jq or run from Git Bash."

# ---- Pre-flight -------------------------------------------------------------
say "0/5  Pre-flight"
REPO="$(git remote get-url origin 2>/dev/null | sed -E 's#^(git@github.com:|https://[^/]*/)##; s#\.git$##')"
[ -n "$REPO" ] || die "Run from the repo root."
echo "  repo: $REPO"

WHO="$(gh api user --jq .login 2>&1)"
gh api user --jq .login >/dev/null 2>&1 \
  || die "gh auth failed: $WHO -> set GH_TOKEN to a PAT with repo+workflow (created as the repo owner)."
echo "  authenticated as: $WHO"

PUSH="$(gh api "repos/$REPO" --jq '.permissions.push' 2>/dev/null)"
[ "$PUSH" = "true" ] || die "$WHO has no write access to $REPO. Use a meencoder PAT."
echo "  write access: yes"

git pull --no-edit origin main 2>&1 | tail -1
echo "  local repo synced"

# ---- 1. Merge the latest agent PR if its test gate is green -----------------
say "1/5  Auto-merge any green agent PR"
PRS="$(gh pr list --repo "$REPO" --state open --json number,headRefName,mergeable \
  --jq '.[] | select(.headRefName | startswith("agent/issue-")) | .number')"
if [ -z "$PRS" ]; then
  echo "  no open agent/issue-* PRs to consider"
else
  for PR in $PRS; do
    GATE="$(gh pr checks "$PR" --repo "$REPO" --json name,state \
      --jq '[.[] | select(.name == "Test gate (pytest)")][0].state' 2>/dev/null)"
    if [ "$GATE" = "SUCCESS" ]; then
      echo "  PR #$PR  test gate: SUCCESS  ->  squash-merging..."
      gh pr merge "$PR" --repo "$REPO" --squash --delete-branch 2>&1 | sed 's/^/    /' || echo "    (merge failed — may need branch update; continuing)"
    else
      echo "  PR #$PR  test gate: ${GATE:-pending/missing}  ->  skipped (only auto-merge when SUCCESS)"
    fi
  done
fi

# ---- 2. Bump turn caps (idempotent; via API so workflow-scope token works) --
say "2/5  Bump workflow turn caps if needed"
bump_caps() {
  local file="$1" old="$2" new="$3"
  local resp sha content
  resp="$(gh api "repos/$REPO/contents/$file" 2>/dev/null)" || { echo "  (could not fetch $file)"; return; }
  sha="$(printf '%s' "$resp" | jq -r .sha)"
  content="$(printf '%s' "$resp" | jq -r .content | base64 --decode)"
  if printf '%s' "$content" | grep -qF -- "$old"; then
    local new_content b64
    new_content="$(printf '%s' "$content" | sed "s|$old|$new|")"
    b64="$(printf '%s' "$new_content" | base64 | tr -d '\n')"
    gh api -X PUT "repos/$REPO/contents/$file" \
      -f message="ci: bump $file turn cap ($old -> $new)" \
      -f content="$b64" -f sha="$sha" -f branch="main" >/dev/null 2>&1 \
      && echo "  ✓ $file: $old -> $new" || echo "  ✗ $file: PUT failed (token needs workflow scope)"
  else
    echo "  ✓ $file: already updated (no '$old' present) — skipped"
  fi
}
bump_caps ".github/workflows/agent-builder.yml"  "--max-turns 25" "--max-turns 60"
bump_caps ".github/workflows/agent-verifier.yml" "--max-turns 12" "--max-turns 30"
git pull --no-edit origin main 2>&1 | tail -1

# ---- 3. Resolve / ensure the target issue -----------------------------------
say "3/5  Resolve target issue (scenario: $SCENARIO)"
case "$SCENARIO" in
  [0-9]*)
    ISSUE_NUM="$SCENARIO"
    gh api "repos/$REPO/issues/$ISSUE_NUM" --jq .number >/dev/null 2>&1 \
      || die "Issue #$ISSUE_NUM not found in $REPO."
    echo "  using provided issue #$ISSUE_NUM"
    ;;
  health)
    TITLE="Add GET /api/health endpoint"
    BODY=$'**Context.** We need a lightweight health/version endpoint for deploy monitoring.\n\n**Task.** Add `GET /api/health` to `src/plugfile/api.py`.\n\n**Acceptance criteria**\n- [ ] Returns HTTP 200 with JSON: status "ok", a `version` (from package metadata/pyproject), and `fetcher` = "mock" or "live" reflecting the RRC fetcher selection.\n- [ ] No auth required (stays open in open mode).\n- [ ] Test in `tests/test_api_health.py` using the FastAPI TestClient: asserts 200, status == "ok", and a non-empty version. Suite stays green.\n\n**Out of scope:** uptime dashboards, external monitors.'
    ;;
  phone)
    TITLE="format_us_phone() helper"
    BODY=$'**Context.** District-office phone numbers should display consistently; start with a tested utility.\n\n**Task.** Add a pure function `format_us_phone(raw: str) -> str` (in `src/plugfile/formatting.py`, create if absent).\n\n**Acceptance criteria**\n- [ ] `"4326845581"`, `"432-684-5581"`, `"(432) 684-5581"`, `"+1 432 684 5581"` all return `"(432) 684-5581"`.\n- [ ] Returns the input unchanged (no crash) if it can\'t be parsed to 10 digits.\n- [ ] Pure function; unit tests in `tests/test_formatting.py` (>=5 cases). Suite stays green.\n\n**Out of scope:** changing the verbatim district-office data; wiring into responses (follow-up).'
    ;;
  normalize)
    TITLE="normalize_api_number() helper + validation"
    BODY=$'**Task.** Add a pure function `normalize_api_number(raw: str) -> str` (new module `src/plugfile/apinum.py`) that validates and canonicalizes a Texas RRC API number.\n\n**Acceptance criteria**\n- [ ] Accepts variants and returns `"42-371-30001"`.\n- [ ] Raises `ValueError` for wrong length, non-numeric, or non-42 state code.\n- [ ] Pure function (no network/IO).\n- [ ] Unit tests in `tests/test_apinum.py` covering >=6 cases. Suite stays green.'
    ;;
  *)  die "Unknown scenario: $SCENARIO  (use: health, phone, normalize, or an issue number)" ;;
esac

if [ -z "${ISSUE_NUM:-}" ]; then
  ISSUE_NUM="$(gh issue list --repo "$REPO" --state open --label "$LABEL" --json number,title \
    --jq "[.[] | select(.title == \"$TITLE\")] | .[0].number // empty" 2>/dev/null)"
  if [ -n "$ISSUE_NUM" ]; then
    echo "  reusing existing issue #$ISSUE_NUM ($TITLE)"
  else
    # ensure the label exists
    gh label list --repo "$REPO" 2>/dev/null | grep -q "^$LABEL" \
      || gh label create "$LABEL" --repo "$REPO" --color FFA500 --description "Build via the Builder agent" >/dev/null
    URL="$(gh issue create --repo "$REPO" --title "$TITLE" --label "$LABEL" --body "$BODY" 2>&1)"
    ISSUE_NUM="$(printf '%s\n' "$URL" | grep -oE '/issues/[0-9]+' | grep -oE '[0-9]+' | tail -1)"
    [ -n "$ISSUE_NUM" ] || die "Failed to create issue. gh output: $URL"
    echo "  created issue #$ISSUE_NUM ($TITLE)"
  fi
fi

# ---- 4. Dispatch Builder + wait + nudge Verifier + wait (delegates to dry_run) ----
say "4/5  Run dry-run on issue #$ISSUE_NUM"
bash tools/dry_run_agents.sh "$ISSUE_NUM"
RC=$?

# ---- 5. Summary -------------------------------------------------------------
say "5/5  Cycle complete"
echo "  scenario:   $SCENARIO"
echo "  issue:      https://github.com/$REPO/issues/$ISSUE_NUM"
PR="$(gh pr list --repo "$REPO" --head "agent/issue-$ISSUE_NUM" --state open --json number --jq '.[0].number // empty')"
[ -n "$PR" ] && echo "  PR:         https://github.com/$REPO/pull/$PR"
echo "  dry_run rc: $RC"
echo "  Next: review the PR + QA verdict, merge, then re-run this script with a new scenario."
exit "$RC"
