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

**Phase 2B (Next — was lower-priority, now elevated).** Print-ready
W-3 PDF generator. Reads the official `w-3p.pdf` template from
rrc.texas.gov as overlay base. Maps every Phase 1B `W3Form` field to a
PDF coordinate. Output: a fillable PDF the operator signs and prints in
duplicate. Free tier carries a "DRAFT — REVIEW BEFORE FILING"
watermark; paid tier carries a clean output plus an audit-trail page
appended to the back. Likely libraries: `pdfrw` for the overlay, `fpdf2`
or `reportlab` for the audit-trail page. One weekend block (4 hours).

**Phase 2C (deferred from earlier slot).** GAU-letter parser. Operators
upload the GAU letter PDF; Plugfile extracts the BUQW depth and any
special-case requirements automatically. Currently the BUQW depth is
operator-input only.

**Phase 2D (deferred).** LLM fallback slot extractor for Section IX.
The current narrative drafter uses regex slot extraction; this would
add a Claude/Sonnet fallback for slots regex misses, behind a
feature flag.

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

## How to read this document later

This plan is a snapshot dated May 2026. The W-3 online-filing status
is the load-bearing assumption — if RRC announces W-3 onboarding to
LoneSTAR, re-read the "Phase 3" and "Updated phase roadmap" sections
and re-prioritize. Memory file
`spaces/.../memory/project_w3_filing_status.md` carries the same
finding for future-Claude sessions.
