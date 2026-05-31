#!/usr/bin/env bash
# =============================================================================
# Dry-run the PlugFile Builder -> Verifier agent loop, end to end.
#
# What it does:
#   1. Pre-flight: confirms gh is authed WITH WRITE access, the two workflows
#      are active, the ANTHROPIC_API_KEY secret exists, and the agent:build
#      label exists (creates it if missing).
#   2. Ensures one small, test-only issue exists (normalize_api_number).
#   3. Triggers the Builder (workflow_dispatch) on that issue and waits for it.
#   4. Finds the PR the Builder opened, triggers the Verifier (close+reopen so
#      it fires without a PAT), and waits for it.
#   5. Prints links, conclusions, and the Verifier's QA comment.
#
# REQUIREMENTS (read these — most failures are setup, not the agents):
#   * gh authenticated as an account with WRITE on meencoder/PlugFile
#       gh auth login            # as meencoder, OR
#       GH_TOKEN=<pat> bash tools/dry_run_agents.sh   # PAT with repo+workflow
#   * Repo secret ANTHROPIC_API_KEY set (Settings -> Secrets -> Actions).
#   * The two workflows added to the repo (.github/workflows/agent-*.yml).
#
# This makes REAL runs (uses Claude API credits) and opens a REAL PR you can
# review or close. Run from the repo root:  bash tools/dry_run_agents.sh
# =============================================================================
set -uo pipefail

BUILDER="agent-builder.yml"
VERIFIER="agent-verifier.yml"
LABEL="agent:build"
ISSUE_TITLE="normalize_api_number() helper + validation"

say(){ printf '\n\033[1m== %s\033[0m\n' "$*"; }
die(){ printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# Make sure `gh` is on PATH. When bash is launched from PowerShell on Windows,
# the GitHub CLI in Program Files isn't always inherited — find it ourselves.
if ! command -v gh >/dev/null 2>&1; then
  for p in "/c/Program Files/GitHub CLI/gh.exe" \
           "/c/Program Files (x86)/GitHub CLI/gh.exe" \
           "$HOME/AppData/Local/GitHubCLI/gh.exe" \
           "$HOME/scoop/apps/gh/current/gh.exe"; do
    if [ -x "$p" ]; then export PATH="$(dirname "$p"):$PATH"; break; fi
  done
fi
command -v gh >/dev/null 2>&1 || die "gh CLI not found on PATH in this bash.
  Easiest fix: open Git Bash directly (Start menu -> Git Bash) and re-run,
  or add gh's install dir to your bash PATH."

# ---- 1. pre-flight ----------------------------------------------------------
say "1/5  Pre-flight checks"
# Determine the repo from the git remote (robust), falling back to gh.
REPO="$(git remote get-url origin 2>/dev/null | sed -E 's#^(git@github.com:|https://[^/]*/)##; s#\.git$##')"
[ -n "$REPO" ] || REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)"
[ -n "$REPO" ] || die "Could not determine the repo. Run from the repo root (needs an 'origin' git remote)."
echo "  repo: $REPO"

# Confirm gh auth actually works (surfaces a bad/expired/typo'd token clearly).
WHO="$(gh api user --jq .login 2>&1)"
if ! gh api user --jq .login >/dev/null 2>&1; then
  die "gh authentication failed: $WHO
  -> Your token/login isn't working. Create a CLASSIC token (scopes: repo + workflow)
     while signed in as the repo owner (meencoder), then:
       Git Bash:   GH_TOKEN=ghp_xxx bash tools/dry_run_agents.sh
       PowerShell: \$env:GH_TOKEN='ghp_xxx'; bash tools/dry_run_agents.sh
     (or simply: gh auth login  — sign in as meencoder)"
fi
echo "  authenticated as: $WHO"

PUSH="$(gh api "repos/$REPO" --jq '.permissions.push' 2>/dev/null)"
[ "$PUSH" = "true" ] || die "Your gh account has only read access to $REPO (push=$PUSH).
  Re-auth as an account with write access (e.g. meencoder):  gh auth login
  or run with a PAT:  GH_TOKEN=<pat with repo+workflow> bash tools/dry_run_agents.sh"
echo "  write access: yes"

for wf in "$BUILDER" "$VERIFIER"; do
  state="$(gh api "repos/$REPO/actions/workflows/$wf" --jq '.state' 2>/dev/null)"
  [ "$state" = "active" ] || die "Workflow $wf is not active (state=$state). Add it via the GitHub web UI."
  echo "  workflow $wf: active"
done

if gh secret list --repo "$REPO" 2>/dev/null | grep -q '^ANTHROPIC_API_KEY'; then
  echo "  secret ANTHROPIC_API_KEY: present"
else
  die "Repo secret ANTHROPIC_API_KEY is missing. Add it: Settings -> Secrets and variables -> Actions."
fi

if gh label list --repo "$REPO" 2>/dev/null | grep -q "^$LABEL"; then
  echo "  label $LABEL: present"
else
  gh label create "$LABEL" --repo "$REPO" --color FFA500 --description "Build via the Builder agent" >/dev/null \
    && echo "  label $LABEL: created"
fi

# ---- 2. ensure the test issue ----------------------------------------------
say "2/5  Test issue"
ISSUE_NUM="$(gh issue list --repo "$REPO" --state open --search "$ISSUE_TITLE in:title" --json number,title \
  --jq ".[] | select(.title==\"$ISSUE_TITLE\") | .number" 2>/dev/null | head -1)"
if [ -z "$ISSUE_NUM" ]; then
  ISSUE_NUM="$(gh issue create --repo "$REPO" --title "$ISSUE_TITLE" --label "$LABEL" --body "$(cat <<'EOF'
**Task.** Add a pure function `normalize_api_number(raw: str) -> str` (new module `src/plugfile/apinum.py`) that validates and canonicalizes a Texas RRC API number.

**Acceptance criteria**
- [ ] Accepts `"4237130001"`, `"42-371-30001"`, `"42 371 30001"`, `" 42-371-30001 "` and returns `"42-371-30001"`.
- [ ] Raises `ValueError` with a clear message for wrong length, non-numeric, or a state code other than `42`.
- [ ] Pure function (no network/IO).
- [ ] Unit tests in `tests/test_apinum.py` covering >=6 cases. Full suite stays green (`python -m pytest -q`).
EOF
)" --jq '.number' 2>/dev/null)"
  # gh issue create prints a URL, not number, in some versions — fall back:
  [ -z "$ISSUE_NUM" ] && ISSUE_NUM="$(gh issue list --repo "$REPO" --state open --search "$ISSUE_TITLE in:title" --json number --jq '.[0].number')"
  echo "  created issue #$ISSUE_NUM"
else
  echo "  reusing existing issue #$ISSUE_NUM"
fi

# ---- 3. trigger Builder + wait ---------------------------------------------
say "3/5  Builder (implement issue #$ISSUE_NUM -> PR)"
gh workflow run "$BUILDER" --repo "$REPO" -f issue_number="$ISSUE_NUM" >/dev/null || die "Failed to dispatch the Builder workflow."
echo "  dispatched; waiting for the run to register..."
sleep 8
RID="$(gh run list --repo "$REPO" --workflow "$BUILDER" --event workflow_dispatch -L1 --json databaseId --jq '.[0].databaseId')"
[ -n "$RID" ] || die "Could not find the Builder run. Check the Actions tab."
echo "  Builder run: https://github.com/$REPO/actions/runs/$RID"
gh run watch "$RID" --repo "$REPO" --exit-status; BUILD_RC=$?
echo "  Builder conclusion: $([ $BUILD_RC -eq 0 ] && echo SUCCESS || echo FAILURE)"
[ $BUILD_RC -eq 0 ] || die "Builder failed. Open the run URL above to see why (common: API credits/model on the key)."

# ---- 4. find PR + trigger Verifier + wait ----------------------------------
say "4/5  Verifier (QA gate on the PR)"
BRANCH="agent/issue-$ISSUE_NUM"
sleep 4
PR="$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --json number --jq '.[0].number')"
[ -n "$PR" ] || die "Builder finished but no open PR on branch $BRANCH was found. Check the repo's Pull requests tab."
echo "  PR: https://github.com/$REPO/pull/$PR"
echo "  nudging the Verifier (close+reopen so it fires without a PAT)..."
gh pr close "$PR" --repo "$REPO" >/dev/null 2>&1; sleep 2; gh pr reopen "$PR" --repo "$REPO" >/dev/null 2>&1
sleep 8
VRID="$(gh run list --repo "$REPO" --workflow "$VERIFIER" -L1 --json databaseId --jq '.[0].databaseId')"
if [ -n "$VRID" ]; then
  echo "  Verifier run: https://github.com/$REPO/actions/runs/$VRID"
  gh run watch "$VRID" --repo "$REPO" --exit-status; VER_RC=$?
  echo "  Verifier conclusion: $([ $VER_RC -eq 0 ] && echo PASS || echo FAIL/changes-requested)"
else
  echo "  (no Verifier run detected yet — check the PR's Checks tab)"
fi

# ---- 5. summary -------------------------------------------------------------
say "5/5  Result"
echo "  Issue:    https://github.com/$REPO/issues/$ISSUE_NUM"
echo "  PR:       https://github.com/$REPO/pull/$PR"
echo "  Verifier QA comment:"
gh pr view "$PR" --repo "$REPO" --comments --json comments \
  --jq '.comments[-1].body' 2>/dev/null | sed 's/^/    /' | head -40
echo
echo "  Next: review the diff + QA verdict, then merge the PR if it looks good."
echo "  Done."
