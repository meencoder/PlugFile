# Plugfile — Updated Plan (May 2026)

This plan supersedes the original three-weekend Phase 1 plan. The trigger
is a regulatory finding from May 2026: **W-3 (Plugging Record) is still
paper-only**, while RRC has moved adjacent forms (P-5, W-3C, W-3X)
online via LoneSTAR. That gap is the wedge.

## The new working hypothesis

Texas operators filing W-3 today are doing it on paper, in duplicate,
hand-delivered or mailed to the District Office, within 30 days of
plugging. They compute cement volumes in Excel, hand-write the Section
IX surface-restoration narrative, and re-type operator/well data the
RRC already has on them. RRC has digitized the *inactive-well lifecycle*
(P-5, W-3C, W-3X) but has not onboarded the *post-plugging record*
itself, leaving W-3 as the laggard form.

Plugfile's near-term wedge is therefore not "submit to RRC" — it is
**produce a print-ready W-3 PDF, with §3.14-validated cement math and a
drafted Section IX narrative, that the operator signs and walks to the
District Office**. When (not if) RRC eventually onboards W-3 to LoneSTAR
in roughly the next 1–2 years, the deterministic Phase 1 core ports
directly to a JSON/EDI submitter.

## What changes from the original plan

The product wedge shifts from *automated submission* to *print-ready
output*. That is a smaller-feeling claim but a bigger-feeling one: it
honestly describes the workflow operators have today, removes the
implicit promise of online filing (which would mislead), and elevates
the deterministic-math + narrative-drafter work that already exists in
Phase 1 into the headline product surface.

The validation strategy compresses. The Gemini-aided desk research has
already produced enough hypothesis-quality material on Texas SMB
software adoption (PakEnergy / WolfePak back-office, GreaseBook field-
side, with a breakpoint around ~25 wells where operators pair the two)
to brief expert calls. The 3-hour LinkedIn mining grind, originally step
2 of the validation playbook, can be cut. What remains is two expert-
network calls (~$1.4K) and a one-month fractional-advisor / inspector
retainer trial (~$1–2K). Total residual validation spend: $2.5–3.4K.

The retainer becomes a product feature, not just a research expense.
Whoever takes the retainer (former RRC inspector, fractional GC-style
advisor with O&G compliance background, or similar) reviews Plugfile
outputs against current District Office practice and gets named on the
landing page as the regulatory cover. That naming is the difference
between "another oil & gas app" and "the only W-3 tool with named
regulatory review" — and is impossible to manufacture after the fact.

## Updated phase roadmap

**Phase 1 (Complete, May 4, 2026).** Cement-volume math + TAC §3.14
rule engine + W-3 schema with source-of-truth metadata + voice-to-
narrative drafter + 208 passing tests. Public on
github.com/meencoder/PlugFile for Phase 1A; 1B/1C staged locally.

**Phase 2A (Complete, May 5–7, 2026).** Real RRC RoRQ fetcher
(`src/plugfile/lookups_rrc.py`) with retry / throttle / disk-cache,
synthetic HTML fixtures, env-var-driven fetcher selection, and a CLI
debugger for selector calibration. Pyproject bumped to 0.2.0 with
runtime deps requests/lxml/diskcache.

**Phase 2B (Complete, May 8–11, 2026).** Print-ready W-3 PDF generator
(`src/plugfile/pdf_export.py`). Overlays every `W3Form` field onto the
official `w-3p.pdf` template at calibrated coordinates. Free tier
carries a "DRAFT — REVIEW BEFORE FILING" watermark; paid tier outputs
a clean PDF plus an inspector-reviewed audit-trail page. CLI:
`plugfile-pdf`. 238 passing tests at completion.

**Phase 2C (Complete, May 2026).** GAU-letter parser
(`src/plugfile/gau_parser.py`). Operators upload the Texas RRC
Groundwater Advisory Unit letter PDF; Plugfile extracts the BUQW depth,
GAU reference number, letter type (GAU-1 standard / GAU-2 special-case),
and any TAC §3.14(d) special plugging requirements. Supports both
selectable-text and flags likely scans. CLI: `plugfile-gau`. 27 new
tests; 5 synthetic letter fixtures covering all known BUQW phrasing
variants.

**Phase 2D (Complete, May 16, 2026).** LLM fallback slot extractor for
Section IX narrative (`src/plugfile/narrative.py`). Claude Haiku (tool
use, forced via `tool_choice`) fills surface-restoration slots the
regex layer misses. Feature-flagged: `PLUGFILE_LLM_FALLBACK=true` or
`use_llm_fallback=True` kwarg. Regex-filled slots are never overwritten;
provenance marked `llm:<model_id>`. Model overridable via
`PLUGFILE_LLM_MODEL`. 24 new mocked tests; 289 total passing tests.

**Phase 3 (Conditional, watch RRC announcements).** LoneSTAR W-3
electronic submitter. Triggered only by an RRC announcement onboarding
W-3 to LoneSTAR — likely 1–2 years out. The Phase 1 deterministic
core ports directly; only the output adapter changes.

## Updated validation phase

The original 4-step playbook becomes a 2-step playbook:

*Step 1 (compressed): Use the Gemini desk-research output as hypothesis
fodder.* Verify the 5–7 named-individual references in the Gemini
output (Arin Cline / Monterey Production / PakEnergy; Antoinette
Roberson; James Youngblood) against actual LinkedIn profiles. Append
the verified rows to the workbook via `tools/fill_mining_log.py
--batch`. Drop the placeholder-named rows ("Mid-Market Op", "Legacy
SMBs", etc.) — they're not data.

*Step 2: Two expert-network calls (~$1.4K).* Tegus or AlphaSense or
GLG. Brief each call with the Gemini hypothesis: "Texas SMB back-office
is dominated by PakEnergy / WolfePak, field-side is dominated by
GreaseBook, with a ~25-well breakpoint where operators pair them." Ask
each expert to confirm or refute, and to add any tools or vendors the
hypothesis missed. Specifically ask each expert about W-3 paper-filing
pain — has it ever been raised as a problem in their engagements?

*Step 3: Inspector / fractional-advisor retainer (~$1–2K/mo, 2-month
trial).* The named human who reviews Plugfile outputs. Sourcing channels
include former RRC District Office staff (LinkedIn search filtered to
Texas + "RRC" + "former" or "retired"), oil & gas-focused fractional
GC services, and IPAA / Texas Alliance of Energy Producers contacts.
Engagement scope: ~5 hours/month — review one or two Plugfile-generated
W-3s per month against current district practice, flag inaccuracies,
sign off on the public "reviewed by" callout. After 2 months, decide
whether to renew or step down to ad-hoc.

## Landing-page updates

Both `landing/index.html` and `landing/for-engineers.html` currently
imply that Plugfile submits W-3 to the RRC online. With the paper-only
finding, that is misleading and needs to be corrected.

The buyer page (`index.html`) gets four changes: the hero lead drops
"files with the RRC" in favor of "produces a print-ready W-3 your
District Office accepts in duplicate"; the timeline's final step
changes from "8AM tomorrow — one click — RRC has it" to "you sign,
print in duplicate, and walk it to the District Office (or mail with
return-receipt)"; the Suite-tier feature list drops the "One-click
submit to RRC" claim and replaces it with "Inspector-reviewed audit
trail per filing"; and a small "What's online, what's still paper"
explainer goes between the timeline and the trust section so the
distinction lives directly on the page (turning a potential confusion
into credibility).

The engineers page (`for-engineers.html`) gets two changes: the hero
lead drops "submits to the RRC" in favor of "produces print-ready W-3
PDFs"; the Suite-tier features drop "Direct RRC e-filing submission"
and the "District-office liaison" line stays as the substitute. The
architecture diagram is accurate and unchanged.

Once the inspector retainer is signed, both pages add a one-line trust
callout: *"Plugfile outputs are reviewed for compliance by [Name],
former RRC District [N] inspector."* That line is held back until the
retainer is real.

## Employment compliance (Big 4 OBA disclosure)

The founder is employed at a Big 4 firm. The spouse operates Plugfile
publicly; the founder has economic interest (joint bank account) and
technical involvement. This triggers Outside Business Activity (OBA)
disclosure obligations regardless of public-facing identity.

**Required before LinkedIn Company Page goes live:**

1. *Review employment agreement* — locate the OBA / outside employment
   / personal independence section. Confirm the disclosure threshold
   (some firms exempt de minimis revenue under $5K/year).

2. *Confirm no client conflict* — verify no current Big 4 engagements
   involve Texas O&G operators who could be Plugfile customers.

3. *Submit OBA disclosure form* — internal ethics/compliance portal
   (search intranet for "outside business activity" or "personal
   independence"). Fields: business name (Plugfile), nature (SaaS
   compliance software for Texas RRC Form W-3), role (minor technical
   contributor; spouse is owner/operator), time (~5 hrs/week evenings
   and weekends), current revenue (de minimis — $1 deposits only).

4. *Disclosure is confidential* — goes to Ethics/Independence, not
   manager or public record.

Risk of non-disclosure is termination for cause; risk of disclosure is
near-zero given the niche product and de minimis revenue. Disclose first,
then launch LinkedIn ads.

## Cost and timeline

Total residual cash spend through validation: $2.5–3.4K (two expert
calls + 2-month retainer trial).

Total residual time spend (in 4-hour weekend blocks):

- One block for Phase 2B (PDF generator).
- One block for the page copy updates and redeployment.
- Two blocks across two months for retainer onboarding + first review
  cycle.
- ~8 hours scattered for verifying Gemini's named references and
  briefing the expert calls.

Five to six weekend blocks, $3K cash. End state: a public freemium
W-3 PDF generator with named regulatory cover, a paid tier with
inspector-reviewed audit trail, and a validated wedge brief usable for
investor / advisor / customer conversations. The paid tier launches
only after the retainer is signed and the expert calls confirm the
hypothesis.

## Open decisions (need a call before the next block)

*Pricing of the freemium tier.* Free with watermark, or one-time small
fee per filing? Free + watermark generates more inbound; per-filing
($5–15/filing) anchors a price reference and reduces frivolous use.
Recommendation: free + watermark for the first 90 days, then revisit
based on conversion data.

*Whether to open-source Phase 1A (already on GitHub).* Currently
public. Continuing as public communicates "deterministic + auditable"
and helps recruit a future eng hire. Risk: a competitor copies the
§3.14 encoding. Recommendation: keep public — the moat is the
inspector retainer + customer relationships, not the math.

*Whether to add W-15 to the headline.* Phase 2C (W-15 generator) is
deferred. The current copy mentions W-15 in the Suite tier. Either
ship Phase 2C alongside Phase 2B (one extra weekend) or remove the W-15
mention until it ships. Recommendation: remove the W-15 mention now;
add back as a "shipped" line when 2C is real.

## Testing guide

Plugfile has three layers of testing: automated (289 pytest tests, zero
network, zero LLM cost), CLI smoke tests (one-shot command per tool),
and an end-to-end operator simulation.  Run them in this order when
validating a build.

### Layer 1 — Automated test suite (deterministic, ~3 s)

```
cd C:\Users\karee\WellPlug\WellPlug
.venv\Scripts\python.exe -m pytest -q
```

Expected: `289 passed`.  The suite covers cement math, TAC rule engine,
W-3 schema validation, RRC fetcher (mocked HTML), PDF overlay geometry,
GAU letter parsing (5 fixtures, 6 BUQW regex patterns), narrative
extraction, and LLM fallback (mocked Anthropic client).  No API keys
required.

### Layer 2 — CLI smoke tests (requires test PDF and venv active)

**plugfile-rrc** — fetch real well data from RRC (needs network):
```
.venv\Scripts\plugfile-rrc.exe 42-371-30001
# Expect: operator name, lease, county, API printed to stdout.
# On network failure the disk-cache serves the last response.
```

**plugfile-gau** — parse a GAU letter PDF:
```
# Use the fixture text rendered to PDF as a quick smoke test:
python - <<'EOF'
from tests.fixtures.gau_letters.letter_texts import GAU1_STANDARD
from plugfile.gau_parser import parse_gau_text
r = parse_gau_text(GAU1_STANDARD)
print(r.buqw_depth_ft, r.gau_letter_reference, r.letter_type)
EOF
# Expect: 1500.0  GAU-2024-03-12-Pecos-21874  GAU-1
```
Against a real letter PDF:
```
.venv\Scripts\plugfile-gau.exe path\to\gau_letter.pdf --json
```

**plugfile-pdf** — generate a filled W-3 PDF:
```
python - <<'EOF'
from plugfile.lookups import MockFetcher
from plugfile.prefill import prefill_w3
from plugfile.pdf_export import export_w3_pdf

form, _ = prefill_w3(
    "42-371-30001", MockFetcher(),
    operator_overrides={
        "operator_signature_name": "Test Operator",
        "certification_date": "2026-05-16",
    },
    plugging_date="2026-05-16",
)
pdf = export_w3_pdf(form, paid_tier=False)
open("test_output_draft.pdf", "wb").write(pdf)
print("Written test_output_draft.pdf")
EOF
# Open test_output_draft.pdf — confirm DRAFT watermark, well data overlaid.
# Re-run with paid_tier=True for clean version.
```

### Layer 3 — End-to-end operator simulation

This mirrors the full workflow an operator would take from the
landing-page deposit through to a print-ready PDF.

**Step 1: Lookup.** Retrieve well data for a known Texas API number.
```python
from plugfile.lookups_rrc import RrcFetcher
from plugfile.prefill import prefill_w3

fetcher = RrcFetcher()   # set RRC_BASE_URL env var or default
form, warnings = prefill_w3("42-371-30001", fetcher,
    operator_overrides={"operator_signature_name": "Jane Smith",
                        "certification_date": "2026-05-16"},
    plugging_date="2026-05-16")
assert form.operator_name  # confirm RRC data landed
```

**Step 2: GAU letter parse → auto-fill BUQW.**
```python
from plugfile.gau_parser import parse_gau_pdf

gau_bytes = open("gau_letter.pdf", "rb").read()
gau = parse_gau_pdf(gau_bytes)
form, _ = prefill_w3("42-371-30001", fetcher,
    operator_overrides={**gau.as_lookup_result(),
                        "operator_signature_name": "Jane Smith",
                        "certification_date": "2026-05-16"},
    plugging_date="2026-05-16")
assert form.buqw_depth_ft == gau.buqw_depth_ft
```

**Step 3: Voice transcript → Section IX narrative.**
```python
from plugfile.narrative import transcript_to_narrative

transcript = (
    "We cut the casing at three feet below grade and welded a "
    "24-by-24-by-quarter-inch steel plate over the stub. "
    "We filled the cellar with caliche. Removed wellhead and pumping unit. "
    "Re-seeded with native grass, graded and contoured the pad. "
    "Work completed on May 16, 2026."
)
narrative, facts, warnings = transcript_to_narrative(transcript)
print(narrative)
# Verify: no [not stated] placeholders, date appears, equipment listed.
# If any slots missing, repeat with use_llm_fallback=True:
#   ANTHROPIC_API_KEY=sk-ant-... (set first)
#   narrative, facts, _ = transcript_to_narrative(transcript, use_llm_fallback=True)
```

**Step 4: LLM fallback (optional, costs ~$0.001 per call).**
```
set ANTHROPIC_API_KEY=sk-ant-...
set PLUGFILE_LLM_FALLBACK=true
python -c "
from plugfile.narrative import transcript_to_narrative
t = 'Cut casing at 3 ft. Leveled the location.'   # intentionally sparse
n, f, w = transcript_to_narrative(t, use_llm_fallback=True)
print(n)
for slot, prov in f.provenance.items():
    if prov.startswith('llm:'):
        print(f'  LLM filled: {slot}')
"
```

**Step 5: PDF output visual QA.**
```python
from plugfile.pdf_export import export_w3_pdf
pdf = export_w3_pdf(form, paid_tier=False)
open("qa_draft.pdf", "wb").write(pdf)
```
Open `qa_draft.pdf` and verify against this checklist:
- [ ] Operator name, API, lease/well number, county correct in header
- [ ] Plugging date in Section I
- [ ] BUQW depth in Section VIII (if set)
- [ ] GAU reference number present
- [ ] Section IX narrative readable and complete
- [ ] Cement volume totals match hand-calculation for a simple casing
- [ ] "DRAFT — REVIEW BEFORE FILING" watermark visible (free tier)
- [ ] No fields overflowing or clipped

Re-run with `paid_tier=True` and verify watermark is absent.

### Layer 4 — Live / external checks (do before each release)

| Check | Command / URL | Pass criterion |
|---|---|---|
| RRC live lookup | `plugfile-rrc 42-371-30001` | Returns operator name, no error |
| Landing page | https://plugfile.com | Loads, no console errors, Stripe Reserve button works |
| Stripe deposit link | Click Reserve on plugfile.com | Redirects to Stripe checkout, amount $1.00 |
| Legacy redirects | https://kaproq.com | 301 → plugfile.com |
| GitHub public | https://github.com/meencoder/PlugFile | Repo accessible, latest commit visible |

### Layer 5 — Regression after any PLAN change

Whenever you modify `tac_3_14.py`, `cement_volume.py`, `pdf_export.py`,
`gau_parser.py`, or `narrative.py`:

```
.venv\Scripts\python.exe -m pytest -x -q   # fail-fast
```

If tests pass, diff the generated PDF visually against the last
approved baseline PDF before pushing.

---

## How to read this document later

This plan is a snapshot dated May 2026. The W-3 online-filing status
is the load-bearing assumption — if RRC announces W-3 onboarding to
LoneSTAR, re-read the "Phase 3" and "Updated phase roadmap" sections
and re-prioritize. Memory file
`spaces/.../memory/project_w3_filing_status.md` carries the same
finding for future-Claude sessions.
