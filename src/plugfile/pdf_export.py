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

import re
from dataclasses import dataclass
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Literal

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor, red
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from .w3_schema import W3_SCHEMA, W3Form
from .w3a_schema import W3A_SCHEMA, W3AForm

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
    "lease_number":               FieldCoord(0, 472.0, 659.0, 90.0, 8.0),
    "lease_name":                 FieldCoord(0, 268.0, 638.0, 175.0),
    "well_number":                FieldCoord(0, 472.0, 638.0, 50.0),
    "county":                     FieldCoord(0, 472.0, 612.0, 105.0),
    "operator_name":              FieldCoord(0, 36.0, 612.0, 195.0),
    "operator_address":           FieldCoord(0, 36.0, 586.0, 195.0),
    # Box 8 footage: values sit in the "___ feet from ... ___ feet from" blanks
    # on the first printed line (not the "line of the ... lease" line below).
    "footage_ns":                 FieldCoord(0, 235.0, 578.0, 55.0, 8.0),
    "footage_ew":                 FieldCoord(0, 382.0, 578.0, 40.0, 8.0),
    "section_block_survey":       FieldCoord(0, 36.0, 533.0, 195.0, 8.0),
    "latitude":                   FieldCoord(0, 268.0, 533.0, 60.0, 8.0),
    "longitude":                  FieldCoord(0, 340.0, 533.0, 60.0, 8.0),
    "total_depth_ft":             FieldCoord(0, 113.0, 511.0, 80.0),
    "spud_date":                  FieldCoord(0, 472.0, 533.0, 90.0),
    "completion_date":            FieldCoord(0, 472.0, 511.0, 90.0),
    "plugging_date":              FieldCoord(0, 472.0, 485.0, 90.0, 8.0),
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
        c.drawString(CASING_COL_X["size"], y, _fmt_od(cas.get("od_in")))
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


def _fmt_od(v: Any) -> str:
    """Format a casing OD as the fractional string operators write on the form.

    9.625 -> "9 5/8", 5.5 -> "5 1/2", 7.0 -> "7". Avoids the lossy 1-decimal
    rounding of ``_fmt_num`` (which turned 9.625 into "9.6").
    """
    if v is None:
        return ""
    try:
        frac = Fraction(float(v)).limit_denominator(64)
    except (TypeError, ValueError):
        return _fmt_num(v)
    whole = int(frac)
    rem = frac - whole
    if rem == 0:
        return str(whole)
    if whole == 0:
        return f"{rem.numerator}/{rem.denominator}"
    return f"{whole} {rem.numerator}/{rem.denominator}"


def _humanize_plug_name(name: str | None) -> str:
    """Turn an engine plug name into a readable label.

    surface_plug                                -> "Surface plug"
    buqw_protective_plug                        -> "BUQW protective plug"
    perforation_Upper Spraberry                 -> "Perforation: Upper Spraberry"
    production_casing_shoe_seg1_inside_casing   -> "Production casing shoe (seg 1, inside casing)"
    """
    n = (name or "plug").strip()
    seg = ""
    m = re.search(r"_seg(\d+)_(inside_casing|open_hole|annulus)$", n)
    if m:
        seg = f" (seg {m.group(1)}, {m.group(2).replace('_', ' ')})"
        n = n[: m.start()]
    # Zone-qualified names use "<label>_<Zone Name>" where the zone may contain
    # spaces (e.g. "perforation_Upper Spraberry").
    label_part, sep, zone = n.partition("_")
    if sep and " " in zone:
        words = label_part.split("_")
        rendered = " ".join("BUQW" if w.lower() == "buqw" else w for w in words)
        head = rendered[:1].upper() + rendered[1:]
        return f"{head}: {zone}{seg}"
    words = n.split("_")
    rendered = " ".join("BUQW" if w.lower() == "buqw" else w for w in words)
    return (rendered[:1].upper() + rendered[1:]) + seg


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


# ===========================================================================
# W-3A (Notice of Intention to Plug and Abandon) overlay
# ===========================================================================
#
# The W-3A is a single-page form (`docs/w-3ap.pdf`, Rev 1/1/83, 612x792).
# Like the W-3 it has no AcroForm widgets, so values are placed at fixed
# (x, y) page coordinates.  The coordinates below are a FIRST-PASS calibration
# derived programmatically from label positions (pypdf text-extraction
# visitor); fine-tune visually with `render_w3a_calibration_overlay()`.

W3A_WELL_TYPE_NO: dict[str, str] = {
    "oil": "1", "gas": "2", "disposal": "3", "injection": "4", "other": "5",
}

# Box 13 "Enter appropriate no. in box" square (well-type number goes here) and
# Box 14 "Type of completion" Single/Multiple checkboxes. Centres detected from
# the blank template; values are drawn as a centred digit / "X" tick, not text.
W3A_WELL_TYPE_BOX: tuple[float, float] = (305.8, 487.5)
W3A_COMPLETION_BOX: dict[str, tuple[float, float]] = {
    "single":   (373.0, 487.5),
    "multiple": (449.0, 487.5),
}

W3A_COORDS: dict[str, FieldCoord] = {
    # Box 1/2/3/4 — operator + district/county (top block)
    "operator_name":            FieldCoord(0, 48.0, 660.0, 300.0, 9.0),
    "operator_address":         FieldCoord(0, 48.0, 648.0, 300.0, 8.0),
    "operator_p5_number":       FieldCoord(0, 175.0, 580.0, 150.0, 9.0),
    "rrc_district":             FieldCoord(0, 392.0, 660.0, 70.0, 9.0),
    "county":                   FieldCoord(0, 478.0, 660.0, 120.0, 9.0),
    # Box 5/6/7/8/9 — ids
    "api_number":               FieldCoord(0, 395.0, 620.0, 90.0, 9.0),
    "drilling_permit_no":       FieldCoord(0, 470.0, 620.0, 120.0, 9.0),
    "rule_37_case_no":          FieldCoord(0, 275.0, 590.0, 95.0, 8.0),
    "lease_number":             FieldCoord(0, 378.0, 582.0, 100.0, 8.0),
    "well_number":              FieldCoord(0, 500.0, 590.0, 80.0, 9.0),
    # Box 10/11 — field + lease name
    "field_name":               FieldCoord(0, 45.0, 554.0, 230.0, 8.0),
    "lease_name":               FieldCoord(0, 300.0, 554.0, 175.0, 8.0),
    # Box 12 — location
    "section_block_survey":     FieldCoord(0, 70.0, 526.0, 380.0, 7.0),
    "abstract_no":              FieldCoord(0, 470.0, 535.0, 80.0, 8.0),
    "location_description":     FieldCoord(0, 360.0, 519.0, 230.0, 7.0),
    # Box 13/14/15 — type + depth. well_type (Box 13 number) and
    # completion_type (Box 14 Single/Multiple tick) are drawn specially by
    # _draw_w3a_type_boxes(), not as free text, so they are not listed here.
    "total_depth_ft":           FieldCoord(0, 480.0, 495.0, 90.0, 9.0),
    # Box 16 — BUQW / GAU. The form has no dedicated GAU-reference field, so the
    # letter reference + date go in the empty right half of Box 16's first
    # printed line (after "...occur to a"), clear of Box 17's printed text.
    "buqw_depth_ft":            FieldCoord(0, 110.0, 463.0, 60.0, 8.0),
    "gau_letter_reference":     FieldCoord(0, 356.0, 470.0, 145.0, 6.5),
    "gau_letter_date":          FieldCoord(0, 505.0, 470.0, 58.0, 6.5),
    # Box 22 — cementer
    "cementing_company":        FieldCoord(0, 48.0, 160.0, 360.0, 8.0),
    "cementer_p5_specialty_code": FieldCoord(0, 430.0, 173.0, 120.0, 8.0),
    # certification (bottom)
    "operator_signature_name":  FieldCoord(0, 45.0, 88.0, 230.0, 8.0),
    "operator_title":           FieldCoord(0, 300.0, 88.0, 130.0, 8.0),
    "certification_date":       FieldCoord(0, 250.0, 86.0, 90.0, 8.0),
}

# Casing grid (Box 18): rows print "<size>  set @ <depth>  w/ <sacks>".
W3A_CASING_ROW_Y: tuple[float, ...] = (373.7, 362.8, 350.8, 338.8, 326.8)
W3A_CASING_SIZE_X = 45.0
W3A_CASING_DEPTH_X = 112.0
W3A_CASING_SACKS_X = 165.0

# Proposed-plug program → Box 20's numbered rows. Box 20 captures only
# "No. of sacks" and "Depth in feet (top & bottom)" per plug (no names), so
# rendering here both places the program in the correct box and avoids leaking
# the engine's internal plug names onto the form. Row baselines were detected
# from the blank template (docs/w-3ap.pdf); the named program with TAC cites
# lives on the paid-tier audit page.
W3A_PROPOSAL_SACKS_X = 379.0   # centred in the "No. of sacks" column
W3A_PROPOSAL_DEPTH_X = 428.0   # left of the "Depth in feet (top & bottom)" rule
W3A_PROPOSAL_ROW_Y: tuple[float, ...] = (
    260.0, 248.5, 237.0, 225.5, 213.9, 202.4, 189.5, 177.7,
)


def render_w3a_pdf(
    form: W3AForm,
    *,
    template_path: Path | None = None,
    tier: Tier = "free",
) -> bytes:
    """Render a print-ready W-3A PDF (Notice of Intention to Plug).

    Single-page overlay onto `docs/w-3ap.pdf`. `tier="free"` adds the DRAFT
    watermark; `tier="paid"` is clean and appends a W-3A audit-trail page.
    """
    template_path = _resolve_w3a_template(template_path)
    base = PdfReader(str(template_path))

    overlay = PdfReader(BytesIO(_build_w3a_overlay(form, tier=tier)))
    writer = PdfWriter(clone_from=base)
    for i, page in enumerate(writer.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])

    if tier == "paid":
        audit = PdfReader(BytesIO(_build_w3a_audit_pages(form)))
        for p in audit.pages:
            writer.add_page(p)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def render_w3a_calibration_overlay(template_path: Path | None = None) -> bytes:
    """Calibration overlay for the W-3A: every coord as a labeled red crosshair
    on the blank form. Use it to visually tune `W3A_COORDS`."""
    template_path = _resolve_w3a_template(template_path)
    base = PdfReader(str(template_path))
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setStrokeColor(HexColor("#FF0000"))
    c.setFillColor(HexColor("#FF0000"))
    c.setFont("Helvetica", 5)
    for name, coord in W3A_COORDS.items():
        _crosshair(c, coord.x, coord.y, name)
    for r, y in enumerate(W3A_CASING_ROW_Y):
        _crosshair(c, W3A_CASING_SIZE_X, y, f"cas{r+1}.size")
        _crosshair(c, W3A_CASING_DEPTH_X, y, f"cas{r+1}.depth")
        _crosshair(c, W3A_CASING_SACKS_X, y, f"cas{r+1}.sacks")
    for r, y in enumerate(W3A_PROPOSAL_ROW_Y):
        _crosshair(c, W3A_PROPOSAL_SACKS_X, y, f"prop{r+1}.sacks")
        _crosshair(c, W3A_PROPOSAL_DEPTH_X, y, f"prop{r+1}.depth")
    _crosshair(c, *W3A_WELL_TYPE_BOX, "well_type.box")
    for k, pos in W3A_COMPLETION_BOX.items():
        _crosshair(c, pos[0], pos[1], f"completion.{k}")
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


def _build_w3a_overlay(form: W3AForm, *, tier: Tier) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)

    for name, coord in W3A_COORDS.items():
        v = getattr(form, name, None)
        if v is None:
            continue
        if name == "api_number" and isinstance(v, str) and v.upper().startswith("42-"):
            v = v[3:]  # state-code prefix is pre-printed
        _draw_value(c, coord, v)

    _draw_w3a_type_boxes(c, form)
    _draw_w3a_casing(c, form)
    _draw_w3a_proposal(c, form)

    if tier == "free":
        _draw_watermark(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def _draw_w3a_type_boxes(c: "canvas.Canvas", form: W3AForm) -> None:
    """Box 13 (well type → number in the entry box) and Box 14 (completion
    type → X in the Single/Multiple checkbox). Both are checkbox-style fields,
    not free text, so they're rendered as a centred digit / tick mark."""
    wt = getattr(form, "well_type", None)
    if wt:
        num = W3A_WELL_TYPE_NO.get(str(wt).lower())
        if num:
            c.setFont("Helvetica", 9)
            c.drawCentredString(W3A_WELL_TYPE_BOX[0], W3A_WELL_TYPE_BOX[1], num)

    ct = getattr(form, "completion_type", None)
    if ct:
        pos = W3A_COMPLETION_BOX.get(str(ct).lower())
        if pos:
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(pos[0], pos[1], "X")


def _draw_w3a_casing(c: "canvas.Canvas", form: W3AForm) -> None:
    rows = form.casing_record[:len(W3A_CASING_ROW_Y)]
    if not rows:
        return
    c.setFont("Helvetica", 8)
    for r, cas in enumerate(rows):
        y = W3A_CASING_ROW_Y[r]
        c.drawString(W3A_CASING_SIZE_X, y, _fmt_od(cas.get("od_in")))
        c.drawString(W3A_CASING_DEPTH_X, y, _fmt_num(cas.get("set_depth_ft")))
        c.drawString(W3A_CASING_SACKS_X, y, _fmt_num(cas.get("sacks_cemented")))


def _draw_w3a_proposal(c: "canvas.Canvas", form: W3AForm) -> None:
    """Render the proposed plug program into Box 20's numbered rows.

    Box 20 records only sacks + depth (top & bottom) per plug — no names — so
    nothing collides with the form's printed Box 19/21 and no internal plug
    name leaks onto the form. The full named program with TAC citations is on
    the paid-tier audit page. Plugs beyond the printed rows are flagged as
    continued on the attached program.
    """
    plugs = form.proposed_plug_record
    if not plugs:
        return
    rows = W3A_PROPOSAL_ROW_Y
    c.setFont("Helvetica", 8)
    for i, plug in enumerate(plugs[:len(rows)]):
        y = rows[i]
        sacks = _fmt_num(plug.get("volume_sacks"))
        if sacks:
            c.drawCentredString(W3A_PROPOSAL_SACKS_X, y, sacks)
        top = _fmt_num(plug.get("top_ft"))
        bot = _fmt_num(plug.get("bottom_ft"))
        c.drawString(W3A_PROPOSAL_DEPTH_X, y, f"{top} - {bot}")
    extra = len(plugs) - len(rows)
    if extra > 0:
        c.setFont("Helvetica-Oblique", 6.5)
        c.drawString(W3A_PROPOSAL_DEPTH_X, rows[-1] - 9.0,
                     f"+{extra} more — see attached program")


def _build_w3a_audit_pages(form: W3AForm) -> bytes:
    """Paid-tier W-3A audit page: field sources, rule paths, proposed-plug volumes."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    y = _w3a_audit_header(c, form)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, y, "Field source-of-truth")
    y -= 14
    c.setFont("Helvetica", 8)
    filled = form.filled_fields()
    for spec in W3A_SCHEMA:
        mark = "filled" if spec.name in filled else "blank "
        c.drawString(72, y, f"  {mark}  {spec.name:34s} [box {spec.rrc_section:<8s}] "
                            f"source={spec.source.value}")
        y -= 10
        if y < 60:
            c.showPage(); y = _w3a_audit_header(c, form); c.setFont("Helvetica", 8)

    if y < 160:
        c.showPage(); y = _w3a_audit_header(c, form)
    y -= 6
    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, y, "TAC §3.14 rule paths exercised (proposal)")
    y -= 14
    c.setFont("Helvetica", 9)
    for rp in (form.plug_program_rule_paths or ["(none)"]):
        c.drawString(90, y, f"• {rp}"); y -= 12

    y -= 6
    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, y, "Proposed plug program (per plug)")
    y -= 14
    c.setFont("Helvetica", 8)
    for plug in form.proposed_plug_record:
        line = (f"  {_humanize_plug_name(plug.get('name'))}: "
                f"{_fmt_num(plug.get('top_ft'))}–"
                f"{_fmt_num(plug.get('bottom_ft'))} ft  "
                f"{_fmt_num(plug.get('volume_sacks'))} sacks  "
                f"({_fmt_num(plug.get('volume_ft3'))} ft³)  cite={plug.get('cite','')}")
        c.drawString(72, y, line); y -= 10
        if y < 60:
            c.showPage(); y = _w3a_audit_header(c, form); c.setFont("Helvetica", 8)

    c.showPage()
    c.save()
    return buf.getvalue()


def _w3a_audit_header(c: "canvas.Canvas", form: W3AForm) -> float:
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 752, "W-3A Audit Trail — Notice of Intention to Plug")
    c.setFont("Helvetica", 9)
    c.drawString(72, 736,
                 f"API {form.api_number or '—'}    {form.operator_name or '—'}    "
                 f"{form.lease_name or '—'} #{form.well_number or '—'}    "
                 f"{form.county or '—'} County")
    if form.w3a_expiration_date:
        c.drawString(72, 722, f"W-3A expires: {form.w3a_expiration_date}")
    c.line(72, 716, PAGE_W - 72, 716)
    return 700.0


def _resolve_w3a_template(explicit: Path | None) -> Path:
    if explicit is not None:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"W-3A template not found at {p}")
        return p
    here = Path(__file__).resolve().parent
    for candidate in (
        here.parent.parent / "docs" / "w-3ap.pdf",
        here.parent.parent / "w-3ap.pdf",
        Path.cwd() / "docs" / "w-3ap.pdf",
        Path.cwd() / "w-3ap.pdf",
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Could not locate w-3ap.pdf. Pass template_path explicitly or place "
        "the official RRC W-3A form at docs/w-3ap.pdf."
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
