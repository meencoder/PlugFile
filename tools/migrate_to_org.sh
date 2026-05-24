#!/usr/bin/env bash
# Migrate the Plugfile repo + local identity from the personal GitHub account
# (meencoder) to a company-owned GitHub organization.
#
# Run this AFTER you have, in the dashboards (these CANNOT be scripted):
#   1) Created the company GitHub org  (ideally signed in with a company
#      Workspace email, e.g. founders@plugfile.com), and
#   2) Transferred the repo into it:
#      GitHub -> meencoder/PlugFile -> Settings -> Danger Zone -> Transfer.
#
# What this script DOES (in-repo, reversible via git):
#   - rewrites "meencoder/PlugFile" references in tracked files to the new org
#   - points the local "origin" remote at the new org
#   - (optional) sets the local commit author email to the company address
#
# Usage:
#   tools/migrate_to_org.sh <NEW_ORG> [COMPANY_EMAIL]            # DRY RUN (shows what would change)
#   tools/migrate_to_org.sh <NEW_ORG> [COMPANY_EMAIL] --apply    # make the changes
#
# Examples:
#   tools/migrate_to_org.sh plugfile-inc founders@plugfile.com
#   tools/migrate_to_org.sh plugfile-inc founders@plugfile.com --apply
set -euo pipefail

NEW_ORG="${1:-}"
[ -z "$NEW_ORG" ] && { echo "usage: tools/migrate_to_org.sh <NEW_ORG> [COMPANY_EMAIL] [--apply]"; exit 1; }
COMPANY_EMAIL=""
APPLY=""
shift
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    *@*)     COMPANY_EMAIL="$a" ;;
  esac
done

OLD="meencoder/PlugFile"
NEW="${NEW_ORG}/PlugFile"
NEW_REMOTE="https://github.com/${NEW}.git"

echo "== Plugfile org migration =="
echo "  repo refs : $OLD  ->  $NEW"
echo "  remote    : origin -> $NEW_REMOTE"
[ -n "$COMPANY_EMAIL" ] && echo "  git email : -> $COMPANY_EMAIL" || echo "  git email : (unchanged; pass a company email to set it)"
echo

mapfile -t FILES < <(git grep -lI "$OLD" 2>/dev/null || true)
echo "Tracked files referencing $OLD (${#FILES[@]}):"
for f in "${FILES[@]}"; do echo "  $f"; done
echo

if [ -z "$APPLY" ]; then
  echo "DRY RUN — nothing changed. Re-run with --apply to perform the migration."
  exit 0
fi

# 1) rewrite references
for f in "${FILES[@]}"; do
  sed -i "s#${OLD}#${NEW}#g" "$f"
done
echo "Rewrote references in ${#FILES[@]} file(s)."

# 2) repoint the remote
git remote set-url origin "$NEW_REMOTE"
echo "origin is now: $(git remote get-url origin)"

# 3) set the local commit identity (this repo only)
if [ -n "$COMPANY_EMAIL" ]; then
  git config user.email "$COMPANY_EMAIL"
  echo "Local git user.email is now: $(git config user.email)"
fi

cat <<NEXT

In-repo migration done. Review with 'git diff', then commit + push:
  git add -A && git commit -m "chore: point repo at ${NEW}" && git push origin main

Still TODO in the dashboards (manual — cannot be scripted):
  - Cloudflare Pages : reconnect the GitHub repo under ${NEW_ORG} so auto-deploy keeps working.
  - Supabase         : re-link the GitHub integration to ${NEW}.
  - GitHub Actions    : confirm the ANTHROPIC_API_KEY repo secret transferred (it should).
  - Auth tokens       : create a workflow-scoped Personal Access Token under the company account for pushes.
  - Update billing on Cloudflare / Supabase / Stripe / Anthropic to the company card/email.
NEXT
