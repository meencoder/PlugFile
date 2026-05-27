#!/usr/bin/env bash
# Create the `agent:build` label + three low-risk starter issues to dry-run the
# Builder -> Verifier agent loop.
#
# REQUIRES: `gh` authenticated with an account that has WRITE/TRIAGE on the repo
# (the current quadri-ks token is read-only on meencoder/PlugFile). Either:
#   gh auth login        # as an account with write access (e.g. meencoder), or
#   GH_TOKEN=<pat> bash tools/create_agent_issues.sh   # PAT with `repo` scope
#
# Run from the repo root:  bash tools/create_agent_issues.sh
set -euo pipefail

gh label create "agent:build" --color FFA500 --description "Build via the Builder agent" 2>/dev/null \
  && echo "created label agent:build" || echo "label agent:build already exists (ok)"

gh issue create --title "normalize_api_number() helper + validation" --label "agent:build" --body "$(cat <<'EOF'
**Context.** The wizards each strip/format Texas RRC API numbers ad-hoc. We want one canonical helper.

**Task.** Add a pure function `normalize_api_number(raw: str) -> str` (new module `src/plugfile/apinum.py`) that validates and canonicalizes a Texas API number.

**Acceptance criteria**
- [ ] Accepts `"4237130001"`, `"42-371-30001"`, `"42 371 30001"`, `" 42-371-30001 "` and returns canonical `"42-371-30001"`.
- [ ] Raises `ValueError` with a clear message for: wrong length, non-numeric, or a state code other than `42`.
- [ ] No network, no I/O — pure function.
- [ ] Unit tests in `tests/test_apinum.py` covering >=6 cases (valid variants + each invalid case). Full suite stays green (`python -m pytest -q`).

**Out of scope:** wiring it into the wizards/endpoints (separate issue).
EOF
)"

gh issue create --title "Add GET /api/health endpoint" --label "agent:build" --body "$(cat <<'EOF'
**Context.** We need a lightweight health/version endpoint for deploy monitoring.

**Task.** Add `GET /api/health` to `src/plugfile/api.py`.

**Acceptance criteria**
- [ ] Returns HTTP 200 with JSON: status "ok", a `version` (from package metadata/pyproject), and `fetcher` = "mock" or "live" reflecting the RRC fetcher selection.
- [ ] No auth required (stays open in open mode).
- [ ] Test in `tests/test_api_health.py` using the FastAPI TestClient: asserts 200, status == "ok", and a non-empty version. Suite stays green.

**Out of scope:** uptime dashboards, external monitors.
EOF
)"

gh issue create --title "format_us_phone() helper" --label "agent:build" --body "$(cat <<'EOF'
**Context.** District-office phone numbers should display consistently; start with a tested utility.

**Task.** Add a pure function `format_us_phone(raw: str) -> str` (in `src/plugfile/formatting.py`, create if absent).

**Acceptance criteria**
- [ ] `"4326845581"`, `"432-684-5581"`, `"(432) 684-5581"`, `"+1 432 684 5581"` all return `"(432) 684-5581"`.
- [ ] Returns the input unchanged (no crash) if it can't be parsed to 10 digits.
- [ ] Pure function; unit tests in `tests/test_formatting.py` (>=5 cases). Suite stays green.

**Out of scope:** changing the verbatim district-office data; wiring into responses (follow-up).
EOF
)"

echo "Done. Created 3 issues labeled agent:build."
