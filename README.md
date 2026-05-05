# WellPlug

Deterministic tooling and an LLM prompt scaffold for filing Texas Railroad
Commission **Form W-3 (Plugging Record)** in compliance with **16 TAC §3.14**
(Statewide Rule 14, *Plugging*).

This is the **Phase 1A** deliverable of a 3-weekend Phase 1 plan:

| Phase | Weekend | Hours | Goal |
|-------|---------|-------|------|
| 1A    | 1       | 4     | Cement-volume calc: encode TAC §3.14 general + special-case rule as deterministic functions; validate against 5 sample wellbore geometries. *(this commit)* |
| 1B    | 2       | 4     | W-3 form-field schema as JSON; map every field to source-of-truth; auto-pre-fill from API-keyed lookups. |
| 1C    | 3       | 4     | Surface-restoration narrative drafter; golden set of 8 voice transcripts → drafted narrative. |

## Design philosophy

W-3 filings are **regulated engineering documents**. Hallucination by an LLM
on cement volumes or plug placement is unacceptable — a missed plug at the
base of usable-quality water (BUQW) is a violation. So the architecture is:

```
voice/text input  ->  LLM (parse, classify, narrate)
                         |
                         v
                deterministic Python tools
                (cement_volume, tac_3_14)
                         |
                         v
                  structured plug program
                         |
                         v
              LLM (draft narrative + W-3 fields)
```

The LLM never does arithmetic. It calls tools. The tools are pure, unit-tested
Python functions that an inspector or operator can audit line by line.

## Layout

```
src/wellplug/
  geometry.py        # Wellbore, CasingString, Perforation, BUQW data models
  cement_volume.py   # Pure math: cylinder + annulus volume in ft^3, bbl, sacks
  tac_3_14.py        # Rule encoding: general 50-ft above/below + BUQW special case
  prompt_scaffold.py # Anthropic-API system prompt + tool JSON schemas

tests/
  fixtures/sample_wellbores.py  # 5 representative Texas wellbores
  test_cement_volume.py         # Volume math vs hand calculation (14 tests)
  test_tac_3_14.py              # Rule output golden tests        (41 tests)

scripts/
  validate_phase1a.py           # End-to-end runner; produces report
```

## Requirements

- Python **3.11+**
- That's it — the deterministic core has zero runtime dependencies.
  `pytest` and `anthropic` are dev-only (for tests and the LLM scaffold).

## How to test Phase 1A

From a fresh clone:

```bash
git clone https://github.com/<your-username>/WellPlug.git
cd WellPlug

# Recommended: virtualenv
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

# Install (editable, with dev extras)
pip install -e ".[dev]"
```

### 1. Run the unit + golden test suite

```bash
pytest -v
```

Expected: **55 passed** in under a second.
The suite covers:

- `test_cement_volume.py` (14 tests) — cylinder and annulus volume math against
  hand-calculated expected values; algebraic invariants (V ∝ L, V ∝ d²,
  excess-factor linearity); input-validation rejections.
- `test_tac_3_14.py` (41 tests) — the rule engine applied to all 5 fixtures.
  Verifies the general rule, the BUQW-uncovered special case, the auto-split
  behavior at casing-to-open-hole transitions, and program ordering.

### 2. Run the end-to-end validation script

```bash
python scripts/validate_phase1a.py
```

This prints the plug program for each of the 5 fixtures and writes
`phase1a_validation_report.md` with a markdown summary table. Expected console
summary:

```
fixture                      plugs  rule path(s)                     total sx
permian_deep_gas                 7  general                              75.0
east_texas_shallow_oil           6  general                              41.2
buqw_uncovered_legacy            4  general,special_buqw_uncovered      184.6
no_surface_casing_legacy         4  general,special_buqw_uncovered      183.1
multi_zone_producer              8  general                              98.4
```

`buqw_uncovered_legacy` and `no_surface_casing_legacy` are the two fixtures
where the **special-case rule fires**: surface casing does not cover BUQW, so
a continuous cement column from surface to BUQW + 50 ft replaces the discrete
surface plug and surface-casing-shoe plug.

### 3. (Optional) Try the LLM scaffold

The Anthropic-API system prompt and tool-use schemas are defined in
`src/wellplug/prompt_scaffold.py`. A working integration looks like:

```python
import os
from anthropic import Anthropic
from wellplug.prompt_scaffold import SYSTEM_PROMPT, TOOL_SCHEMAS, dispatch_tool_call

client = Anthropic()  # uses ANTHROPIC_API_KEY
messages = [{"role": "user", "content": "<operator narrative...>"}]

while True:
    resp = client.messages.create(
        model="claude-haiku-4-5",
        system=SYSTEM_PROMPT,
        tools=TOOL_SCHEMAS,
        max_tokens=4096,
        messages=messages,
    )
    if resp.stop_reason != "tool_use":
        print(resp.content)
        break
    tool_results = []
    for block in resp.content:
        if block.type == "tool_use":
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": dispatch_tool_call(block.name, block.input),
            })
    messages.append({"role": "assistant", "content": resp.content})
    messages.append({"role": "user", "content": tool_results})
```

## Citation policy

References to TAC §3.14 paragraphs in this repo are **best-effort and must be
verified against the current published rule** before any production filing.
The Texas Secretary of State's TAC site and the RRC's Statewide Rules page
are the sources of truth. This repo encodes the *substance* of the rule, but
paragraph numbering occasionally shifts with rule amendments.

## License

MIT.
