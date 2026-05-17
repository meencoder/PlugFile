"""Phase 2B: print-ready W-3 PDF generator.

Reads the official RRC `w-3p.pdf` template and overlays values from a
populated `W3Form` at known page coordinates. Two output tiers:

  * `tier="free"`  - red diagonal "DRAFT - REVIEW BEFORE FILING" watermark
                     across both pages.
  * `tier="paid"`  - clean output, plus an appended audit-trail page that
                     lists every field with its FieldSource, the §3.14 rule
                     paths exercised, and the cement-volume calculations.

Why coordinate overlay (and not AcroForm field-fill): the official RRC W-3
PDF references `/AcroForm` in its catalog but contains no `/Widget`
annotations - the document is a flat scan with FreeTextTypewriter overlay
annotations. So named-field fill via `pypdf` returns nothing useful and we
must place text at fixed (x, y) page coordinates.

Coordinate map (`W3_COORDS` and the grid constants) is calibrated against
the Aug 2019 revision of `w-3p.pdf` (612 x 792 user-space units, origin
bottom-left). When RRC publishes a new revision, regenerate the calibration
overlay (`plugfile-pdf --calibrate -o calib.pdf`) and re-tune.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Literal

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor, red
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from .w3_schema import W3_SCHEMA, W3Form

Tier = Literal["free", "paid"]

PAGE_W, PAGE_H = LETTER  # (612.0, 792.0)


# ---- coordinate map --------------------------------------------------------

@dataclass(frozen=True)
class FieldCoord:
    """Where on which page a scalar W-3 field's value is drawn."""
    page: int           # 0-indexed
    x: float            # PDF user-space, origin bottom-left
    y: float
    max_width: float    # truncate / shrink to fit within this width
    font_size: float = 9.0


# Page 0 (Sections I-X recto) and Page 1 (Sections 31-42 verso). Coordinates
# locate the value (not the label) and were derived from label positions
# extracted via pypdf's text-extraction visitor.
W3_COORDS: dict[str, FieldCoord] = {
    "api_number":                 FieldCoord(0, 365.0, 693.0, 95.0),
    "rrc_district":               FieldCoord(0, 472.0, 693.0, 60.0, 10.0),
    "field_name":                 FieldCoord(0, 36.0, 638.0, 195.0),
    "lease_number":               FieldCoord(0, 472.0, 664.0, 90.0),
    "lease_name":                 FieldCoord(0, 268.0, 638.0, 175.0),
    "well_number":                FieldCoord(0, 472.0, 638.0, 50.0),
    "county":                     FieldCoord(0, 472.0, 612.0, 105.0),
    "operator_name":              FieldCoord(0, 36.0, 612.0, 195.0),
    "operator_address":           FieldCoord(0, 36.0, 586.0, 195.0),
    "footage_ns":                 FieldCoord(0, 268.0, 560.0, 100.0, 8.0),
    "footage_ew":                 FieldCoord(0, 300.0, 560.0, 100.0, 8.0),
    "section_block_survey":       FieldCoord(0, 36.0, 533.0, 195.0, 8.0),
    "latitude":                   FieldCoord(0, 268.0, 533.0, 60.0, 8.0),
    "longitude":                  FieldCoord(0, 340.0, 533.0, 60.0, 8.0),
    "total_depth_ft":             FieldCoord(0, 113.0, 511.0, 80.0),
    "spud_date":                  FieldCoord(0, 472.0, 533.0, 90.0),
    "completion_date":            FieldCoord(0, 472.0, 511.0, 90.0),
    "plugging_date":              FieldCoord(0, 472.0, 490.0, 90.0),
    "operator_signature_name":    FieldCoord(0, 72.0, 70.0, 200.0),
    "operator_title":             FieldCoord(0, 280.0, 70.0, 85.0),
    "certification_date":         FieldCoord(0, 380.0, 70.0, 70.0),
    "cementing_company":          FieldCoord(0, 380.0, 150.0, 240.0),
    "buqw_depth_ft":              FieldCoord(1, 90.0,  655.0, 90.0),
    "gau_letter_reference":       FieldCoord(1, 225.0, 655.0, 160.0, 8.0),
    "surface_restoration_narrative": FieldCoord(1, 36.0, 250.0, 540.0, 8.0),
}


# Plug grid (Section VIII, rows *19-*27 across 8 plug columns).
# Column centers for #1..#8 on page 0.
PLUG_COL_X: tuple[float, ...] = (268.0, 309.0, 350.0, 391.0, 432.0, 473.0, 514.0, 555.0)
PLUG_ROW_Y: dict[str, float] = {
    "cement_date":           463.0,
    "hole_size_in":          450.0,
    "drill_pipe_depth":      437.0,
    "sacks":                 424.0,
    "slurry_volume":         411.0,
    "calc_top":              399.0,
    "measured_top":          386.0,
    "slurry_weight":         373.0,
    "type_cement":           361.0,
}

# Casing & tubing record (Section IV/V, rows under "28."), 5 rows max.
CASING_ROW_Y: tuple[float, ...] = (320.0, 308.0, 296.0, 284.0)
CASING_COL_X: dict[str, float] = {
    "size":        40.0,
    "weight":      85.0,
    "put_in":      142.0,
    "left_in":     212.0,
    "hole_size":   270.0,
}

# Open hole / perforated intervals (Section VI), 5 rows x 2 from-to pairs each.
PERF_ROW_Y: tuple[float, ...] = (256.0, 243.0, 230.0, 217.0, 204.0)
PERF_PAIR_X: tuple[tuple[float, float], ...] = (
    (75.0, 225.0),
    (380.0, 480.0),
)


# ---- public API ------------------------------------------------------------

def render_w3_pdf(
    form: W3Form,
    *,
    template_path: Path | None = None,
    tier: Tier = "free",
) -> bytes:
    """Render a print-ready W-3 PDF.

    Returns the raw PDF bytes. The output has 2 pages (the official template)
    plus, when `tier == "paid"`, one or more appended audit-trail pages.
    """
    template_path = _resolve_template(template_path)
    base = PdfReader(str(template_path))
    if len(base.pages) < 2:
        raise ValueError(
            f"Template {template_path} has {len(base.pages)} page(s); "
            "expected 2 (the official W-3 form is double-sided)."
        )

    overlay_bytes = _build_overlay(form, tier=tier)
    overlay = PdfReader(BytesIO(overlay_bytes))

    # Clone the template into the writer first so merged pages are attached
    # (pypdf 7 deprecates merge_page on detached pages).
    writer = PdfWriter(clone_from=base)
    for i, page in enumerate(writer.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])

    if tier == "paid":
        audit = PdfReader(BytesIO(_build_audit_pages(form)))
        for p in audit.pages:
            writer.add_page(p)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def render_calibration_overlay(template_path: Path | None = None) -> bytes:
    """Generate a calibration overlay: every named coord rendered as a labeled
    red crosshair on top of the blank template. Use this to visually tune
    `W3_COORDS` and the grid constants when RRC revises the form.

        plugfile-pdf --calibrate -o calib.pdf

    Open `calib.pdf` and any field whose crosshair sits in the wrong cell
    needs its (x, y) bumped. Re-run after each adjustment.
    """
    template_path = _resolve_template(template_path)
    base = PdfReader(str(template_path))

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)

    # Page 0: scalar fields, plug grid, casing grid, perf grid
    _draw_calibration_marks(c, page=0)
    c.showPage()
    _draw_calibration_marks(c, page=1)
    c.showPage()
    c.save()

    overlay = PdfReader(BytesIO(buf.getvalue()))
    writer = PdfWriter(clone_from=base)
    for i, page in enumerate(writer.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


# ---- overlay construction --------------------------------------------------

def _build_overlay(form: W3Form, *, tier: Tier) -> bytes:
    """Render two pages of overlay (matching the template) into a fresh PDF."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)

    # ---- Page 0 ----
    for name, coord in W3_COORDS.items():
        if coord.page != 0:
            continue
        v = getattr(form, name, None)
        if v is None:
            continue
        # API number: strip "42-" state-code prefix — it is pre-printed on the form.
        if name == "api_number" and isinstance(v, str) and v.upper().startswith("42-"):
            v = v[3:]
        _draw_value(c, coord, v)

    _draw_plug_grid(c, form)
    _draw_casing_grid(c, form)
    _draw_perforation_grid(c, form)

    if tier == "free":
        _draw_watermark(c)
    c.showPage()

    # ---- Page 1 ----
    for name, coord in W3_COORDS.items():
        if coord.page != 1:
            continue
        v = getattr(form, name, None)
        if v is None:
            continue
        # Narrative needs word-wrap; all other page-1 fields are single-line.
        if name == "surface_restoration_narrative":
            _draw_wrapped(c, coord, v)
        else:
            _draw_value(c, coord, v)

    if tier == "free":
        _draw_watermark(c)
    c.showPage()

    c.save()
    return buf.getvalue()


def _draw_value(c: "canvas.Canvas", coord: FieldCoord, value: Any) -> None:
    s = _format_scalar(value)
    if not s:
        return
    c.setFont("Helvetica", coord.font_size)
    fitted = _fit_text(s, coord.max_width, coord.font_size)
    c.drawString(coord.x, coord.y, fitted)


def _draw_wrapped(c: "canvas.Canvas", coord: FieldCoord, value: Any,
                  min_y: float = 40.0) -> None:
    """Word-wrap ``value`` across multiple lines starting at coord.(x, y).

    Each successive line is drawn ``font_size + 2`` points lower.  Stops when
    ``min_y`` is reached so text never runs off the bottom of the page.
    """
    s = _format_scalar(value)
    if not s:
        return
    c.setFont("Helvetica", coord.font_size)
    line_h = coord.font_size + 2.0
    avg_glyph = coord.font_size * 0.55
    chars_per_line = max(1, int(coord.max_width / avg_glyph))

    # Word-wrap
    words = s.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) <= chars_per_line:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    y = coord.y
    for line in lines:
        if y < min_y:
            break
        c.drawString(coord.x, y, line)
        y -= line_h


def _draw_plug_grid(c: "canvas.Canvas", form: W3Form) -> None:
    plugs = form.plug_record[:8]
    if not plugs:
        return
    c.setFont("Helvetica", 7)
    plugging_date = _format_scalar(form.plugging_date)
    for j, plug in enumerate(plugs):
        x = PLUG_COL_X[j]
        # *19 Cementing Date - default to plugging_date if cementer didn't
        # supply a per-plug date. A future revision should let cementer override.
        if plugging_date:
            c.drawCentredString(x, PLUG_ROW_Y["cement_date"], plugging_date)
        c.drawCentredString(x, PLUG_ROW_Y["hole_size_in"],
                            _fmt_num(plug.get("bore_diameter_in")))
        c.drawCentredString(x, PLUG_ROW_Y["sacks"],
                            _fmt_num(plug.get("volume_sacks")))
        c.drawCentredString(x, PLUG_ROW_Y["slurry_volume"],
                            _fmt_num(plug.get("volume_ft3")))
        c.drawCentredString(x, PLUG_ROW_Y["calc_top"],
                            _fmt_num(plug.get("top_ft")))
        # Rows 21, 25, *26, *27 are cementer-supplied at the rig and are not
        # in the W3Form schema today; leave blank for handwriting.


def _draw_casing_grid(c: "canvas.Canvas", form: W3Form) -> None:
    rows = form.casing_record[:5]
    if not rows:
        return
    c.setFont("Helvetica", 8)
    # Fall back to set_depth_ft for "left in well" until the schema models
    # post-plug pulled-back depth separately (Phase 2C+).
    for r, cas in enumerate(rows):
        y = CASING_ROW_Y[r]
        set_depth = cas.get("set_depth_ft")
        c.drawString(CASING_COL_X["size"], y, _fmt_num(cas.get("od_in")))
        c.drawString(CASING_COL_X["weight"], y, _fmt_num(cas.get("weight_lb_per_ft")))
        c.drawString(CASING_COL_X["put_in"], y, _fmt_num(set_depth))
        c.drawString(CASING_COL_X["left_in"], y, _fmt_num(set_depth))
        # Hole size at completion isn't in the schema; leave blank.


def _draw_perforation_grid(c: "canvas.Canvas", form: W3Form) -> None:
    perfs = form.perforations[:10]
    if not perfs:
        return
    c.setFont("Helvetica", 8)
    for idx, perf in enumerate(perfs):
        row = idx // 2
        pair = idx % 2
        y = PERF_ROW_Y[row]
        x_from, x_to = PERF_PAIR_X[pair]
        c.drawString(x_from, y, _fmt_num(perf.get("top_ft")))
        c.drawString(x_to,   y, _fmt_num(perf.get("bottom_ft")))


def _draw_watermark(c: "canvas.Canvas") -> None:
    c.saveState()
    try:
        c.setFillColor(HexColor("#FF0000"), alpha=0.18)
    except TypeError:  # very old reportlab without alpha kw
        c.setFillColor(red)
    c.setFont("Helvetica-Bold", 56)
    c.translate(PAGE_W / 2, PAGE_H / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, "DRAFT — REVIEW BEFORE FILING")
    c.restoreState()


# ---- audit-trail (paid tier) ----------------------------------------------

def _build_audit_pages(form: W3Form) -> bytes:
    """Append a paginated audit trail listing every field with its source,
    the rule paths exercised, and the cement-volume calculations."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    y = _audit_header(c, form)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, y, "Field source-of-truth")
    y -= 14
    c.setFont("Helvetica", 8)
    filled = form.filled_fields()
    for spec in W3_SCHEMA:
        mark = "filled" if spec.name in filled else "blank "
        line = (f"  {mark}  {spec.name:34s} "
                f"[§{spec.rrc_section:<3s}]  "
                f"source={spec.source.value}")
        c.drawString(72, y, line)
        y -= 10
        if y < 60:
            c.showPage()
            y = _audit_header(c, form)
            c.setFont("Helvetica", 8)

    if y < 140:
        c.showPage()
        y = _audit_header(c, form)
    y -= 6
    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, y, "TAC §3.14 rule paths exercised")
    y -= 14
    c.setFont("Helvetica", 9)
    paths = form.plug_program_rule_paths or ["(none)"]
    for rp in paths:
        c.drawString(90, y, f"• {rp}")
        y -= 12
    y -= 6
    if form.buqw_protected_by_surface_casing is not None:
        flag = ("yes" if form.buqw_protected_by_surface_casing else "NO")
        c.drawString(90, y, f"• BUQW protected by surface casing: {flag}")
        y -= 12

    if y < 100:
        c.showPage()
        y = _audit_header(c, form)
    y -= 8
    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, y, "Cement-volume calculations (per plug)")
    y -= 14
    c.setFont("Helvetica", 8)
    for plug in form.plug_record:
        line1 = (f"  {plug.get('name','')}: "
                 f"{_fmt_num(plug.get('top_ft'))}–"
                 f"{_fmt_num(plug.get('bottom_ft'))} ft  "
                 f"× {_fmt_num(plug.get('bore_diameter_in'))}\" "
                 f"{plug.get('bore','')}")
        line2 = (f"        = {_fmt_num(plug.get('volume_ft3'))} ft³, "
                 f"{_fmt_num(plug.get('volume_bbl'))} bbl, "
                 f"{_fmt_num(plug.get('volume_sacks'))} sacks  "
                 f"(excess={_fmt_num(plug.get('excess_factor'))})")
        line3 = f"        cite={plug.get('cite','')}  rule_path={plug.get('rule_path','')}"
        for line in (line1, line2, line3):
            c.drawString(72, y, line)
            y -= 10
            if y < 60:
                c.showPage()
                y = _audit_header(c, form)
                c.setFont("Helvetica", 8)
        y -= 4

    c.showPage()
    c.save()
    return buf.getvalue()


def _audit_header(c: "canvas.Canvas", form: W3Form) -> float:
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 752, "W-3 Audit Trail")
    c.setFont("Helvetica", 9)
    c.drawString(72, 736,
                 f"API {form.api_number or '—'}    "
                 f"{form.operator_name or '—'}    "
                 f"{form.lease_name or '—'} #{form.well_number or '—'}    "
                 f"{form.county or '—'} County")
    c.drawString(72, 722, f"Plugging date: {form.plugging_date or '—'}")
    c.line(72, 716, PAGE_W - 72, 716)
    return 700.0


# ---- calibration overlay ---------------------------------------------------

def _draw_calibration_marks(c: "canvas.Canvas", *, page: int) -> None:
    c.setStrokeColor(HexColor("#FF0000"))
    c.setFillColor(HexColor("#FF0000"))
    c.setFont("Helvetica", 5)

    for name, coord in W3_COORDS.items():
        if coord.page != page:
            continue
        _crosshair(c, coord.x, coord.y, name)

    if page == 0:
        for j, x in enumerate(PLUG_COL_X):
            for label, y in PLUG_ROW_Y.items():
                _crosshair(c, x, y, f"P{j+1}.{label}", centered=True)
        for r, y in enumerate(CASING_ROW_Y):
            for col, x in CASING_COL_X.items():
                _crosshair(c, x, y, f"C{r+1}.{col}")
        for r, y in enumerate(PERF_ROW_Y):
            for pi, (xf, xt) in enumerate(PERF_PAIR_X):
                _crosshair(c, xf, y, f"perf{r+1}.{pi+1}.from")
                _crosshair(c, xt, y, f"perf{r+1}.{pi+1}.to")


def _crosshair(c: "canvas.Canvas", x: float, y: float, label: str,
               *, centered: bool = False) -> None:
    c.line(x - 3, y, x + 3, y)
    c.line(x, y - 3, x, y + 3)
    if centered:
        c.drawCentredString(x, y - 8, label)
    else:
        c.drawString(x + 4, y + 1, label)


# ---- formatting helpers ----------------------------------------------------

def _format_scalar(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _fmt_num(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        if float(v).is_integer():
            return f"{int(v)}"
        return f"{v:.1f}"
    return str(v)


def _fit_text(s: str, max_width: float, font_size: float) -> str:
    """Truncate `s` so its rendered width fits `max_width` at `font_size`.

    Helvetica avg-glyph width is ~0.55 * font_size. This is a pessimistic
    cheap estimate; for the W-3 form-fill use case, truncation with an
    ellipsis is a graceful failure mode."""
    avg_glyph = font_size * 0.55
    max_chars = max(1, int(max_width / avg_glyph))
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return s[:1]
    return s[: max_chars - 1] + "…"


# ---- template resolution ---------------------------------------------------

def _resolve_template(explicit: Path | None) -> Path:
    if explicit is not None:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"W-3 template not found at {p}")
        return p
    # Default: walk up from this file looking for w-3p.pdf at the repo root.
    here = Path(__file__).resolve().parent
    for candidate in (
        here.parent.parent / "w-3p.pdf",         # src/plugfile -> repo_root/w-3p.pdf
        Path.cwd() / "w-3p.pdf",
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Could not locate w-3p.pdf. Pass --template explicitly or place "
        "the official RRC W-3 template at the repo root."
    )


# ---- CLI -------------------------------------------------------------------

def _cli_main() -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="plugfile-pdf",
        description="Render a print-ready W-3 PDF from prefilled W3Form data.",
    )
    p.add_argument("api_number", nargs="?",
                   help="14-char Texas API number, e.g. 42-371-30001 "
                        "(omit when --calibrate)")
    p.add_argument("-o", "--output", required=True, help="Output PDF path")
    p.add_argument("--tier", choices=["free", "paid"], default="free",
                   help="Free = DRAFT watermark; paid = clean + audit page")
    p.add_argument("--plugging-date", default=None,
                   help="ISO YYYY-MM-DD date plugging was performed")
    p.add_argument("--real", action="store_true",
                   help="Use the live RRC fetcher instead of MockFetcher "
                        "(requires network)")
    p.add_argument("--template", default=None,
                   help="Override path to w-3p.pdf")
    p.add_argument("--calibrate", action="store_true",
                   help="Render a calibration overlay (no form data)")
    p.add_argument("--list-fixtures", action="store_true",
                   help="List API numbers known to MockFetcher and exit")
    args = p.parse_args()

    if args.list_fixtures:
        from .lookups import MockFetcher
        for api in MockFetcher.known_api_numbers():
            print(api)
        return 0

    out = Path(args.output)

    if args.calibrate:
        pdf = render_calibration_overlay(
            Path(args.template) if args.template else None
        )
        out.write_bytes(pdf)
        print(f"Wrote calibration overlay to {out} ({len(pdf):,} bytes)")
        return 0

    if not args.api_number:
        p.error("api_number is required unless --calibrate or --list-fixtures")

    from .lookups import MockFetcher
    from .prefill import prefill_w3
    if args.real:
        from .lookups_rrc import RRCRoRQFetcher
        fetcher: Any = RRCRoRQFetcher()
    else:
        fetcher = MockFetcher()

    form, conflicts = prefill_w3(
        args.api_number, fetcher, plugging_date=args.plugging_date
    )
    pdf = render_w3_pdf(
        form,
        tier=args.tier,
        template_path=Path(args.template) if args.template else None,
    )
    out.write_bytes(pdf)
    print(f"Wrote {out} ({len(pdf):,} bytes, tier={args.tier})")
    if conflicts:
        print(f"\n{len(conflicts)} field conflict(s):")
        for fc in conflicts:
            print(f"  {fc.render()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
