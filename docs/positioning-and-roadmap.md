# Plugfile — Repositioned Wedge & Feature Roadmap

_Last updated: 2026-05-21. Trigger: RRC training deck "Form W-3A and W-3 Submission and Review" (Borrego/Beckham, July 2025) showing W-3 now files online._

---

## The shift

| | Before | Now |
|---|---|---|
| **Belief** | W-3 is paper-only; operator walks it to the District Office | W-3 (and W-3A) file **online** via the RRC Online System |
| **Wedge** | "We print your W-3 PDF" | "We get your W-3 **correct and complete** before it touches the portal" |
| **Product surface** | The PDF generator *is* the product | The PDF is **one output**; the deterministic correctness engine is the product |

**This does NOT invalidate the business.** Three facts protect it:

1. **No third-party submission API.** The RRC Online System is a human web portal — log in, click ~10 screens, hand off Operator → Plugger → Operator → RRC, then "Submit to District." Software can't auto-submit; it can prepare and verify.
2. **Hardcopy still legal.** SWR 14(b)(1): file a verified plugging record "in duplicate" at the district office within 30 days. Paper coexists with online.
3. **The pain is data, not the submit button.** Cement math, plug placement, GAU depth, required attachments, and the portal's quirky formats are all *upstream* of submission — and are where filings get rejected.

> **Positioning line:** *TurboTax doesn't mail your return — it gets the numbers right and hands you a verified package. Plugfile does that for the W-3.*

---

## What we already have (shipped, 298 tests)

- §3.14 rule engine + cement-volume math (`tac_3_14.py`, `cement_volume.py`)
- W-3 schema + prefill from RRC lookups + conflict warnings (`w3_schema.py`, `prefill.py`)
- Live RRC EWA fetcher (`lookups_rrc.py`)
- GAU letter parser w/ Sonnet OCR for scanned letters (`gau_parser.py`)
- Section IX narrative drafter, regex + LLM fallback (`narrative.py`)
- Print-ready W-3 PDF, free/paid tiers (`pdf_export.py`)
- Web API + PWA wizard (`api.py`, `static/`)

---

## Roadmap — ranked by leverage

| # | Feature | Why it wins | Reuses |
|---|---|---|---|
| 1 | **W-3A (Notice of Intent to Plug)** | Captures the operator *before* plugging, not just after. The deck is half about W-3A. Doubles surface area. | schema/prefill pattern, RRC lookups, PDF engine |
| 2 | **AOR (Area of Review) helper** | Query RRC GIS Viewer for disposal/injection wells + unplugged producers within ½ mi and corrosive/over-pressured zones; flag zones needing isolation plugs. Unique, defensible. | RRC fetcher, county/district map |
| 3 | **Plug-placement / proposal generator** | From wellbore + zones, compute *required* plugs (CIBP+20ft or 100ft+10%, 50ft straddle, BUQW tag, GAU zones, surface-casing shoe, surface plug) + cement each. | §3.14 + cement engines (most of this exists) |
| 4 | **Required-attachments checklist + bundler** | GAU letter, W-15, L-1 log report, P-13. Block "ready" until complete — #1 cause of district rejection. | GAU parser |
| 5 | **Portal field-format validator** | Output exact portal formats: surface=`0`, sizes as fractions (`4 1/2` not `4.5`, `8 5/8` not `8.625`, `16` not `16.0`). Copy-paste without rejection. | schema |
| 6 | **GW-2 / GAU "H-15 acceptable for plugging" check** | Verify the uploaded GAU letter is the right *type* for plugging; warn if not. | GAU parser |
| 7 | **Operator ↔ plugger collaboration handoff** | Mirror the RRC role workflow; gives both parties a reason to use Plugfile. | web API |
| 8 | **Auto district-office routing** | Surface correct office address/contact from well's county. | existing county→district map |

---

## Source evidence (deck page refs)

- W-3 online flow: pp. 24–33 ("W-3 Online 1–10 of 10")
- 3-party workflow + "Submit to District" + emailed PDF: pp. 23, 38
- Hardcopy still legal (SWR 14(b)(1), "in duplicate", 30 days): pp. 21, 39
- AOR / RRC GIS Viewer recommendation: p. 16
- Plug requirements (CIBP+20, 100+10%, 50ft straddle, BUQW tag): pp. 17–18
- Required attachments (GAU, W-15, L-1, P-13): p. 34
- Portal data-format quirks (surface=0, fractions not decimals): p. 37
- GW-2 H-15 acceptable vs not: pp. 12–13
- District office contacts: p. 44
