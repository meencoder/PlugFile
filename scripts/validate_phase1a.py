"""Phase 1A end-to-end validation runner.

Applies the TAC 3.14 rule engine to all 5 sample wellbores, prints the
resulting plug program for each, and writes a markdown report.

Run from the repo root:
    PYTHONPATH=src python scripts/validate_phase1a.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

# Make `plugfile` and `tests.*` importable regardless of how invoked.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from plugfile.tac_3_14 import compute_plug_program  # noqa: E402
from tests.fixtures.sample_wellbores import ALL_FIXTURES  # noqa: E402


REPORT_PATH = ROOT / "phase1a_validation_report.md"


def fmt_well_header(name: str, well) -> str:
    sc = next((c for c in well.casing if c.kind.value == "surface"), None)
    sc_desc = (
        f"{sc.od_in}\" set @ {sc.set_depth_ft:.0f} ft (ToC {sc.top_of_cement_ft:.0f})"
        if sc else "NONE"
    )
    return dedent(f"""\
        ### {name}

        - **API**: {well.api_number}  |  **Operator**: {well.operator}
        - **Lease/Well**: {well.lease_name} #{well.well_number}, {well.county} County
        - **TD**: {well.total_depth_ft:.0f} ft  |  **BUQW**: {well.buqw.depth_ft:.0f} ft ({well.buqw.source})
        - **Surface casing**: {sc_desc}
        - **Notes**: {well.notes}
        """)


def fmt_plug_table(plugs) -> str:
    lines = [
        "| # | Top (ft) | Bottom (ft) | Bore | Dia (in) | Excess | ft^3 | bbl | sacks | Cite | Path |",
        "|---|---------:|------------:|------|---------:|-------:|-----:|----:|------:|------|------|",
    ]
    for i, p in enumerate(plugs, 1):
        lines.append(
            f"| {i} | {p.top_ft:.0f} | {p.bottom_ft:.0f} | {p.bore} | "
            f"{p.bore_diameter_in:.3f} | {p.volume.excess_factor:.0%} | "
            f"{p.volume.ft3:.2f} | {p.volume.bbl:.2f} | {p.volume.sacks:.1f} | "
            f"{p.cite} | {p.rule_path} |"
        )
    return "\n".join(lines)


def fmt_plug_console(plugs) -> str:
    lines = []
    for p in plugs:
        lines.append(f"  - {p.name}")
        lines.append(
            f"      {p.top_ft:>6.0f} -> {p.bottom_ft:<6.0f} ft  "
            f"({p.bottom_ft - p.top_ft:>4.0f} ft)  "
            f"bore={p.bore} d={p.bore_diameter_in:.3f}\"  "
            f"excess={p.volume.excess_factor:.0%}"
        )
        lines.append(
            f"      {p.volume.ft3:>7.2f} ft^3  |  "
            f"{p.volume.bbl:>6.2f} bbl  |  "
            f"{p.volume.sacks:>6.1f} sx       [{p.rule_path}] {p.cite}"
        )
    return "\n".join(lines)


def main() -> int:
    md_chunks: list[str] = [
        "# Phase 1A Validation Report",
        "",
        "Output of `scripts/validate_phase1a.py`. Every cement volume below ",
        "comes from `plugfile.cement_volume` (deterministic, unit-tested) ",
        "and every plug placement from `plugfile.tac_3_14.compute_plug_program`.",
        "",
        "Five representative Texas wellbore geometries were exercised; one ",
        "triggers the `general` rule path, one triggers the BUQW-uncovered ",
        "`special_buqw_uncovered` path, and the remaining three exercise ",
        "edge cases inside the general path.",
        "",
        "---",
        "",
    ]

    print("=" * 78)
    print("Plugfile — Phase 1A Validation")
    print("=" * 78)

    summary_rows = []
    for name, well in ALL_FIXTURES.items():
        plugs = compute_plug_program(well)
        rule_paths = sorted({p.rule_path for p in plugs})
        total_ft3 = sum(p.volume.ft3 for p in plugs)
        total_bbl = sum(p.volume.bbl for p in plugs)
        total_sx = sum(p.volume.sacks for p in plugs)

        print()
        print(f"--- {name} ({len(plugs)} plugs, paths={rule_paths}) ---")
        print(fmt_plug_console(plugs))
        print(
            f"  TOTAL: {total_ft3:.2f} ft^3 | {total_bbl:.2f} bbl | "
            f"{total_sx:.1f} sx"
        )

        md_chunks.append(fmt_well_header(name, well))
        md_chunks.append("")
        md_chunks.append(f"**Rule path(s) taken**: `{', '.join(rule_paths)}`")
        md_chunks.append("")
        md_chunks.append(fmt_plug_table(plugs))
        md_chunks.append("")
        md_chunks.append(
            f"**Totals**: {total_ft3:.2f} ft^3  |  {total_bbl:.2f} bbl  "
            f"|  {total_sx:.1f} sacks  ({len(plugs)} plugs)"
        )
        md_chunks.append("")
        md_chunks.append("---")
        md_chunks.append("")

        summary_rows.append((name, len(plugs), rule_paths, total_sx))

    # Summary
    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"{'fixture':<28}{'plugs':>6}  {'rule path(s)':<35}{'total sx':>10}")
    for name, n, paths, sx in summary_rows:
        print(f"{name:<28}{n:>6}  {','.join(paths):<35}{sx:>10.1f}")

    md_chunks.insert(11, "## Summary\n")
    summary_md = [
        "| Fixture | Plugs | Rule path(s) | Total sacks |",
        "|---------|------:|--------------|------------:|",
    ]
    for name, n, paths, sx in summary_rows:
        summary_md.append(f"| {name} | {n} | {', '.join(paths)} | {sx:.1f} |")
    md_chunks.insert(12, "\n".join(summary_md) + "\n")

    REPORT_PATH.write_text("\n".join(md_chunks), encoding="utf-8")
    print()
    print(f"Markdown report written to: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
