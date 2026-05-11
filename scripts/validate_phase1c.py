"""Phase 1C end-to-end validation runner.

For each of the 8 golden voice transcripts:
  1. Run the deterministic slot extractor.
  2. Print the extracted facts (with provenance).
  3. Print the drafted Section IX narrative.
  4. Print any ExtractionWarning entries.
  5. Demonstrate end-to-end integration: for the one transcript whose
     api_number matches a Phase 1B fixture, run the full prefill +
     narrative pipeline and show the populated W-3 form's Section IX.

Writes phase1c_validation_report.md.

Run from the repo root:
    PYTHONPATH=src python scripts/validate_phase1c.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from plugfile.lookups import MockFetcher  # noqa: E402
from plugfile.narrative import (  # noqa: E402
    extract_facts_from_transcript,
    transcript_to_narrative,
)
from plugfile.prefill import prefill_w3_with_mock  # noqa: E402
from tests.fixtures.voice_transcripts import ALL_TRANSCRIPTS  # noqa: E402


REPORT_PATH = ROOT / "phase1c_validation_report.md"


def main() -> int:
    md: list[str] = [
        "# Phase 1C Validation Report",
        "",
        "Output of `scripts/validate_phase1c.py`. Demonstrates the surface-",
        "restoration narrative drafter (`plugfile.narrative`) against 8 ",
        "golden voice transcripts representing real-style operator dictation.",
        "",
        "Each transcript is exercised through:",
        "1. Deterministic regex/keyword slot extraction.",
        "2. Template-based narrative drafting.",
        "3. ExtractionWarning emission for missing required slots.",
        "",
        "One transcript is also run through full Phase 1B prefill so the",
        "Section IX narrative populates a complete W-3 form end-to-end.",
        "",
        "---",
        "",
    ]

    print("=" * 78)
    print("Plugfile -- Phase 1C Validation")
    print("=" * 78)

    summary_rows = []
    known_apis = set(MockFetcher().known_api_numbers())

    for fx in ALL_TRANSCRIPTS:
        facts, _ = extract_facts_from_transcript(fx.transcript, fallback_year=2026)
        narrative, _, warnings = transcript_to_narrative(
            fx.transcript, fallback_year=2026,
            well_context=(
                {"api_number": fx.api_number} if fx.api_number else None
            ),
        )
        n_filled = len(facts.filled_slots())
        n_warn = sum(1 for w in warnings if w.severity == "warn")

        print()
        print(f"--- {fx.name} (API: {fx.api_number or 'n/a'}) ---")
        print(f"  filled slots ({n_filled}): {sorted(facts.filled_slots())}")
        if facts.equipment_removed:
            print(f"  equipment removed: {facts.equipment_removed}")
        if warnings:
            print(f"  warnings ({n_warn}):")
            for w in warnings:
                print(f"    {w.render()}")
        print(f"  drafted narrative:")
        # Wrap narrative for readability
        for chunk in _wrap(narrative, 72, indent=4):
            print(chunk)

        summary_rows.append((fx.name, fx.api_number, n_filled, n_warn))

        md.append(f"### {fx.name}")
        md.append("")
        md.append(f"- API: `{fx.api_number or 'n/a'}`")
        md.append(f"- Filled slots ({n_filled}): "
                  f"{', '.join(f'`{s}`' for s in sorted(facts.filled_slots()))}")
        if facts.equipment_removed:
            md.append(f"- Equipment removed: "
                      f"{', '.join(facts.equipment_removed)}")
        if warnings:
            md.append("- Warnings:")
            for w in warnings:
                md.append(f"  - `{w.severity}` `{w.slot}`: {w.message}")
        md.append("")
        md.append("**Transcript** (operator dictation):")
        md.append("")
        md.append(f"> {fx.transcript}")
        md.append("")
        md.append("**Drafted Section IX narrative**:")
        md.append("")
        md.append(f"> {narrative}")
        md.append("")
        md.append("---")
        md.append("")

    # End-to-end demo: prefill + narrative
    e2e_fx = next((f for f in ALL_TRANSCRIPTS
                   if f.api_number and f.api_number in known_apis), None)
    if e2e_fx:
        print()
        print("=" * 78)
        print(f"END-TO-END: prefill + narrative for API {e2e_fx.api_number}")
        print("=" * 78)
        form, _ = prefill_w3_with_mock(
            e2e_fx.api_number,
            {"operator_signature_name": "Jane Doe",
             "operator_title": "Production Engineer",
             "certification_date": "2026-05-04"},
            plugging_date="2026-05-04",
        )
        narrative, _, _ = transcript_to_narrative(
            e2e_fx.transcript,
            well_context={
                "api_number": form.api_number,
                "lease_name": form.lease_name,
                "well_number": form.well_number,
                "county": form.county,
            },
            fallback_year=2026,
        )
        form.surface_restoration_narrative = narrative
        print(f"  W3Form populated for {form.lease_name} #{form.well_number}")
        print(f"  Section VIII plug count: {len(form.plug_record)}")
        print(f"  Section IX narrative length: {len(narrative)} chars")
        print(f"  Missing required fields: {sorted(form.missing_required())}")
        print()
        print("  Section IX narrative:")
        for chunk in _wrap(narrative, 72, indent=4):
            print(chunk)

        md.append("## End-to-end pipeline demo")
        md.append("")
        md.append(
            f"For API `{e2e_fx.api_number}` (a Phase 1B fixture), the full "
            f"pipeline runs:"
        )
        md.append("")
        md.append(
            "  `prefill_w3_with_mock(api)` -> populates Sections I-VIII -> "
            "`transcript_to_narrative(...)` -> populates Section IX"
        )
        md.append("")
        md.append(
            f"- Lease/Well: **{form.lease_name} #{form.well_number}**"
        )
        md.append(f"- Plugs computed: **{len(form.plug_record)}**")
        md.append(
            f"- Missing required after pipeline: "
            f"`{sorted(form.missing_required()) or '(none)'}`"
        )
        md.append("")
        md.append("**Section IX narrative**:")
        md.append("")
        md.append(f"> {narrative}")
        md.append("")

    # Summary
    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"{'transcript':<32}{'API':<18}{'slots':>7}{'warns':>7}")
    for name, api, n_filled, n_warn in summary_rows:
        print(f"{name:<32}{(api or '-'):<18}{n_filled:>7}{n_warn:>7}")

    md.insert(15, "## Summary\n")
    summary_md = [
        "| Transcript | API | Filled slots | Warnings |",
        "|------------|-----|-------------:|---------:|",
    ]
    for name, api, n_filled, n_warn in summary_rows:
        summary_md.append(
            f"| `{name}` | `{api or 'n/a'}` | {n_filled} | {n_warn} |"
        )
    md.insert(16, "\n".join(summary_md) + "\n")

    REPORT_PATH.write_text("\n".join(md), encoding="utf-8")
    print()
    print(f"Markdown report written to: {REPORT_PATH}")
    return 0


def _wrap(text: str, width: int, indent: int = 0):
    """Simple word-wrapper for console output."""
    pad = " " * indent
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width - indent:
            yield pad + line
            line = word
        else:
            line = (line + " " + word) if line else word
    if line:
        yield pad + line


if __name__ == "__main__":
    raise SystemExit(main())
