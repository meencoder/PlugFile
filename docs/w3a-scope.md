# Scope: W-3A (Notice of Intention to Plug and Abandon) support

_Status: scoping. Grounded in the existing W-3 architecture (`w3_schema.py`, `prefill.py`, `tac_3_14.py`, `pdf_export.py`)._

## Why W-3A first (vs the AOR helper)

| | W-3A support | AOR helper |
|---|---|---|
| Reuse of existing engine | **Very high** — `compute_plug_program()` already produces the proposed plugs | Medium |
| New external integration | None (form PDF only) | RRC GIS Viewer (ArcGIS web app) — **uncertain/risky** |
| Strategic value | Captures the operator **before** plugging; the front half of the same job | Defensible, but is actually a *sub-section* of the W-3A |
| Main lift | Source + calibrate a blank W-3A form PDF | Reverse-engineer GIS query layer |

**Recommendation:** build W-3A first. AOR is a *component* of the W-3A plugging proposal — ship it as manual input inside W-3A v1, then automate it as the AOR helper (roadmap #2) in v2.

## The key insight

The W-3 is the *record of what was plugged* (as-built). The W-3A is the *intent — what you propose to plug* (forward-looking). Our deterministic core, `compute_plug_program(wellbore)` in `tac_3_14.py`, computes the **required** plug program from §3.14. That output is *more native to the W-3A proposal than to the W-3*:

- **W-3 today:** computed plugs = the "should-be" the operator reconciles against what they actually did.
- **W-3A:** computed plugs = **the proposal itself.** No reconciliation needed.

So ~70% of W-3A is already built.

## What W-3A shares with W-3 (reuse verbatim)

From `w3_schema.py`, these `FieldSpec` groups carry over unchanged:
- **Section I** — well/operator identity (api, operator, lease, well_no, county, district, field)
- **Section II** — surface location (lat/long, footages, section/block/survey)
- **Section III** — depths (total_depth_ft, plug_back_td)
- **Section IV** — `CASING_RECORD_ITEM` casing strings
- **Section VII** — BUQW depth + GAU reference
- **Proposed plugs** — reuse `PLUG_RECORD_ITEM` shape, source still `COMPUTED`

From `prefill.py`, reuse wholesale:
- `lookup_well_by_api`, `lookup_gau`, `lookup_completion` (casing + TD)
- `_wellbore_from_form()` → `compute_plug_program()` → `_plug_to_dict()`

## What W-3A adds (new)

Per the July 2025 deck:
1. **AOR (Area of Review) findings** (deck p16) — array of nearby disposal/injection wells, unplugged shallower producers, corrosive/over-pressured zones within ½ mi that require isolation plugs. **v1: operator-entered.** v2: auto from GIS helper.
2. **Approved cementer P-5 specialty code** (p19) — the plugging company's P-5 must carry the cementing specialty. New field + (later) validation.
3. **W-3A expiration date** (p20) — approval is time-boxed; track issue + expiry.
4. **Historic plug info** (p14) — prior TA / CIBP-with-cement intervals not previously reported (attach W-15).
5. **Purpose / GW-2 H-15 acceptability** (p12–13) — the GAU determination must be "acceptable for plugging." Ties into the GAU parser check (roadmap #6).

## What W-3A drops (vs W-3)

- Section IX surface-restoration narrative (restoration happens *after* plugging → stays on W-3)
- As-plugged actuals (plugging_date results, cementing company's pumped report)
- Section X becomes an **intent** certification, not a plugging certification

## Implementation outline

1. **`src/plugfile/w3a_schema.py`** — `W3A_SCHEMA` + `W3AForm`. Import shared `FieldSpec` groups from `w3_schema` (Section I/II/III/IV/VII, `PLUG_RECORD_ITEM`); add `aor_findings[]`, `cementer_p5_specialty_code`, `w3a_issue_date`, `w3a_expiration_date`, `historic_plugs[]`. _~0.5 day._
2. **`prefill_w3a(api_number, fetcher, ...)`** in `prefill.py` (or `prefill_w3a.py`) — mirror `prefill_w3`; reuse the wellbore→plug-program path for the **proposal**; AOR via overrides for v1. _~0.5 day._
3. **W-3A PDF overlay** — source the blank W-3A from the RRC Oil & Gas Forms Library (deck p4), add it as `w-3a.pdf`, calibrate coordinate overlay like `w-3p.pdf`. **Biggest lift / slowest part** (manual coordinate calibration, same as W-3 was). _~1.5 days._
4. **API + wizard** — `POST /api/generate-w3a`; add an "Intent" mode to the PWA. _~0.5 day._
5. **Tests** — mirror `test_gau_parser`/prefill tests; fixture wellbores already exist. _~0.5 day._

**Estimate: ~3–4 days**, dominated by PDF calibration (step 3).

## Open questions to resolve before coding

1. **Source the official blank W-3A PDF** + confirm exact field layout against the "W-3A User's Guide" (deck references "Page 4"). Without this, step 3 can't start.
2. **Shared schema vs duplication** — recommend a small shared `_w3_common.py` holding the Section I/II/III/IV/VII `FieldSpec` groups, imported by both `w3_schema` and `w3a_schema`, to avoid drift.
3. **AOR depth** — confirm v1 = manual entry is acceptable, or whether the GIS helper must ship together.
4. **Expiration handling** — does Plugfile just record/display the W-3A expiry, or warn when a plugging_date would fall outside it?
