# WellPlug

Deterministic tooling and an LLM prompt scaffold for filing Texas Railroad
Commission **Form W-3 (Plugging Record)** in compliance with **16 TAC §3.14**
(Statewide Rule 14, *Plugging*).

| Phase | Weekend | Hours | Goal | Status |
|-------|---------|-------|------|--------|
| 1A    | 1       | 4     | Cement-volume calc: encode TAC §3.14 general + special-case rule as deterministic functions; validate against 5 sample wellbore geometries. | shipped 2026-05-04 |
| 1B    | 2       | 4     | W-3 form-field schema as JSON; map every field to source-of-truth; auto-pre-fill from API-keyed lookups. | shipped 2026-05-04 |
| 1C    | 3       | 4     | Surface-restoration narrative drafter; golden set of 8 voice transcripts → drafted narrative. | **shipped 2026-05-04** |

## Phase 1 is now complete.

End-to-end, an operator can hand the system an API number and a voice
transcript and receive a fully-populated W-3 form with zero missing
required fields. Every cement volume comes from unit-tested deterministic
math. Every plug placement comes from the encoded TAC §3.14 rule engine.
Every Section IX narrative is built from regex-extracted facts with
clearly-flagged placeholders for slots the operator forgot to mention.

## Design philosophy

W-3 filings are **regulated engineering documents**. Hallucination by an
LLM on cement volumes, plug placement, or surface-restoration narrative
is unacceptable -- a missed plug at the base of usable-quality water (BUQW)
is a violation; a fabricated cap dimension is a misstatement. So every
fact-bearing path is deterministic, auditable Python; the LLM only routes,
classifies, and occasionally narrates around the trusted core.

```
            voice/text input
                  |
                  v
   +---------------------------------+
   |  LLM: parse, classify, narrate  |
   +---------------------------------+
                  |
                  v
   +---------------------------------+
   |  deterministic Python tools     |
   |  - cement_volume                |
   |  - tac_3_14                     |
   |  - lookups + prefill            |
   |  - narrative (regex extractor)  |
   +---------------------------------+
                  |
                  v
   +---------------------------------+
   |  populated W3Form               |
   |  + FieldConflict warnings       |
   |  + ExtractionWarning warnings   |
   +---------------------------------+
```

## Layout

```
src/wellplug/
  geometry.py             # Wellbore / casing / perforation data models    (1A)
  cement_volume.py        # Pure cement-volume math                         (1A)
  tac_3_14.py             # TAC 3.14 rule engine                            (1A)
  prompt_scaffold.py      # LLM system prompt + 6 deterministic tools     (1A+B+C)
  w3_schema.py            # 33-field W-3 schema + source-of-truth          (1B)
  json_schema_export.py   # Draft 2020-12 JSON Schema exporter              (1B)
  lookups.py              # Fetcher protocol + MockFetcher + RRCRoRQ stub   (1B)
  prefill.py              # Prefill engine + FieldConflict detector         (1B)
  narrative.py            # Surface-restoration extractor + drafter         (1C)

tests/
  fixtures/sample_wellbores.py   # 5 representative Texas wellbores       (1A)
  fixtures/voice_transcripts.py  # 8 golden voice transcripts             (1C)
  test_cement_volume.py          # 14 hand-calc tests                     (1A)
  test_tac_3_14.py               # 41 rule-engine golden tests            (1A)
  test_w3_schema.py              # 41 schema + JSON-schema-export tests   (1B)
  test_lookups.py                # 25 mock-fetcher tests                  (1B)
  test_prefill.py                # 34 prefill + conflict-detector tests   (1B)
  test_narrative_extraction.py   # 29 slot-extractor tests                (1C)
  test_narrative_drafter.py      # 24 drafter + golden-phrase tests       (1C)

scripts/
  validate_phase1a.py            # 1A end-to-end: prints all 5 plug programs
  validate_phase1b.py            # 1B end-to-end: prints prefill + conflicts
  validate_phase1c.py            # 1C end-to-end: prints all 8 narratives + e2e

schemas/
  w3.schema.json                 # Generated JSON Schema (Phase 1B output)
```

## Requirements

- Python **3.11+**
- Zero runtime dependencies. `pytest` and `anthropic` are dev-only.

## Test workflow

From a fresh clone:

```bash
git clone https://github.com/quadri-ks/WellPlug.git
cd WellPlug

python -m venv .venv
# Linux/macOS:  source .venv/bin/activate
# Windows:      .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

### 1. Run the unit + golden test suite

```bash
pytest -v
```

Expected: **208 passed** (14 cement-math + 41 TAC §3.14 + 41 W-3 schema +
25 lookups + 34 prefill + 29 extractor + 24 drafter).

### 2. Run all three validation scripts

```bash
python scripts/validate_phase1a.py
python scripts/validate_phase1b.py
python scripts/validate_phase1c.py
```

Each writes its own markdown report:

- `phase1a_validation_report.md` — 5 plug programs, special-case trigger
  on the two unprotected-BUQW fixtures.
- `phase1b_validation_report.md` — pre-fill coverage by source-of-truth,
  conflict detection demo, regenerated `schemas/w3.schema.json`.
- `phase1c_validation_report.md` — 8 transcripts → 8 drafted narratives,
  plus an end-to-end demo where one transcript flows through prefill +
  narrative to produce a complete W-3 with zero missing required fields.

### 3. Inspect outputs

```bash
# Windows
type schemas\w3.schema.json
type phase1c_validation_report.md
# Unix
cat schemas/w3.schema.json
cat phase1c_validation_report.md
```

The JSON Schema lists 33 top-level W-3 fields with full source-of-truth
annotations and is consumable by any standard JSON Schema validator.

### 4. (Optional) Try the LLM scaffold

The Anthropic-API system prompt and tool-use schemas are in
`src/wellplug/prompt_scaffold.py`. Phase 1C completes the tool registry:

| Tool | What it does |
|------|--------------|
| `compute_cement_volume_cylinder`            | Cylinder plug volume math |
| `compute_cement_volume_annulus`             | Annulus plug volume math |
| `compute_plug_program`                      | TAC 3.14 rule engine on raw geometry |
| `lookup_well_by_api`                        | Raw RRC/GAU/operator data for an API |
| `prefill_w3_form`                           | End-to-end W-3 prefill from an API |
| `draft_surface_restoration_narrative`       | Voice transcript → Section IX narrative |

The LLM should prefer `prefill_w3_form` for facts and
`draft_surface_restoration_narrative` for Section IX prose. Together they
cover ~95% of a typical W-3; the remaining ~5% is operator certification
fields that legally must come from the operator.

## Citation policy

References to TAC §3.14 paragraphs in this repo are **best-effort and must
be verified against the current published rule** before any production
filing. The Texas Secretary of State's TAC site and the RRC's Statewide
Rules page are the sources of truth.

## License

MIT.
