# Monorepo layout

```
caprock/  (this repo)
  pyproject.toml            # ROOT package = plugfile (unchanged) + [tool.uv.workspace]
  src/plugfile/             # RRC W-3 product — domain code, untouched by step 1
  packages/
    agent-chassis/          # shared, domain-free kernel
      src/agent_chassis/    #   model.py · toolloop.py · serialize.py
  apps/
    familyops/              # AI family chief-of-staff MVP
      src/familyops/        #   graph.py (the household graph = the moat)
  .github/workflows/ci.yml  # per-member matrix; eval gate stubbed (FO-3)
```

## Reuse rule
**Chassis owns the verb, apps own the noun.**
- LLM call / tool loop / serialize / persist / serve → `agent-chassis`
- RRC, TAC §3.14, well, GAU → `plugfile`
- child, school, family, household → `familyops`

**Dependency direction:** apps → chassis only. Chassis imports no app; no app→app.

## Local dev
`uv` is not yet installed on this machine. Two ways to work:

```powershell
# Option A (recommended): install uv, then from repo root
#   irm https://astral.sh/uv/install.ps1 | iex
uv sync                      # resolves the whole workspace, one lockfile
uv run pytest packages/agent-chassis apps/familyops

# Option B: existing .venv, no new tooling — run a member's tests directly
$env:PYTHONPATH = "packages/agent-chassis/src"
.\.venv\Scripts\python.exe -m pytest packages/agent-chassis/tests -q
```

> Note on Python 3.14: plugfile's native deps (lxml, reportlab, cryptography)
> may lack 3.14 wheels. The CI matrix pins Python 3.12 for `uv sync`. Keep the
> existing .venv as-is until those wheels are confirmed on 3.14.

## Not done in step 1 (tracked as reviewed PRs, not a blind big-bang)
1. **CH-1** Move `plugfile` under `apps/plugfile/` for symmetry (optional).
2. **CH-2** Decouple plugfile to *consume* chassis primitives
   (`prompt_scaffold` → `agent_chassis.run_tool_loop`; `_serialize` →
   `agent_chassis.to_jsonable`), guarded by the existing 358 tests.
3. **CH-3** Implement `GeminiModel.create` (Gemini function-calling → block shape) + tests.
