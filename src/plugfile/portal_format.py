"""Portal Field-Format Validator for Texas RRC Online System.

Converts Plugfile internal values to the exact string formats required when
a user is copying data into the RRC Online System web portal — the same
formats documented in the RRC submission training deck (p.37).

Formatting rules
----------------
  * API number        XX-XXX-XXXXX  (validated, not re-formatted)
  * Casing OD         decimal → fractional string, e.g. 9.625 → "9 5/8"
  * Depths            float → integer string,  e.g. 1500.0 → "1500"
                      Surface depth must be "0", not "0.0"
  * Dates             ISO YYYY-MM-DD → MM/DD/YYYY
  * Cement sacks      float → rounded integer string
  * Perforation depth same as depth rule

The ``format_for_portal()`` function returns a :class:`PortalFormatResult`
whose ``to_dict()`` output is JSON-serialisable and can be displayed as a
copy-paste cheat-sheet in the PWA.

Usage::

    from plugfile.portal_format import format_for_portal_with_mock

    result = format_for_portal_with_mock("42-371-30001")
    if result.ready_to_copy:
        print(result.to_dict())
    else:
        print("Warnings:", result.warnings)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Optional

from plugfile.lookups import MockFetcher
from plugfile.prefill_w3a import prefill_w3a
from plugfile.tac_3_14 import compute_plug_program
from plugfile.prefill import _wellbore_from_form


# ---------------------------------------------------------------------------
# Low-level formatters
# ---------------------------------------------------------------------------

def od_to_fraction(value: float) -> str:
    """Convert a decimal casing OD to the fractional string the RRC uses.

    Examples::

        od_to_fraction(4.5)    → "4 1/2"
        od_to_fraction(8.625)  → "8 5/8"
        od_to_fraction(9.625)  → "9 5/8"
        od_to_fraction(13.375) → "13 3/8"
        od_to_fraction(16.0)   → "16"

    Uses :func:`fractions.Fraction` with denominator limited to 64 —
    sufficient for all standard API casing sizes.
    """
    frac = Fraction(value).limit_denominator(64)
    whole = int(frac)
    remainder = frac - whole
    if remainder == 0:
        return str(whole)
    elif whole == 0:
        return f"{remainder.numerator}/{remainder.denominator}"
    else:
        return f"{whole} {remainder.numerator}/{remainder.denominator}"


def depth_to_portal(depth_ft: float | None) -> str | None:
    """Convert a depth float to the integer string the portal expects.

    ``None`` passes through as ``None`` (field not populated).
    ``0.0`` → ``"0"`` (surface depth must not be ``"0.0"``).

    Examples::

        depth_to_portal(1500.0)  → "1500"
        depth_to_portal(0.0)     → "0"
        depth_to_portal(None)    → None
    """
    if depth_ft is None:
        return None
    return str(int(round(depth_ft)))


def date_to_portal(iso_date: str | None) -> str | None:
    """Convert an ISO date string to MM/DD/YYYY.

    Examples::

        date_to_portal("2026-05-21") → "05/21/2026"
        date_to_portal(None)         → None

    Raises:
        ValueError: if *iso_date* is not blank but doesn't match YYYY-MM-DD.
    """
    if not iso_date:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso_date.strip())
    if not m:
        raise ValueError(
            f"Date {iso_date!r} is not ISO YYYY-MM-DD format — cannot convert."
        )
    yyyy, mm, dd = m.groups()
    return f"{mm}/{dd}/{yyyy}"


def sacks_to_portal(sacks: float | None) -> str | None:
    """Round cement sacks to the nearest integer string.

    Examples::

        sacks_to_portal(47.8) → "48"
        sacks_to_portal(None) → None
    """
    if sacks is None:
        return None
    return str(int(round(sacks)))


def validate_api_number(api: str) -> tuple[bool, str | None]:
    """Check that *api* matches the RRC XX-XXX-XXXXX format.

    Returns ``(True, None)`` when valid, ``(False, message)`` when not.
    """
    if re.fullmatch(r"\d{2}-\d{3}-\d{5}", api.strip()):
        return True, None
    return False, (
        f"API number {api!r} should be XX-XXX-XXXXX "
        "(two-digit district, three-digit county, five-digit lease)."
    )


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class PortalFormatResult:
    """Portal-ready formatted values for one wellbore, copy-paste ready.

    Attributes:
        api_number:      The RRC API number (validated, not modified).
        warnings:        Any formatting problems found (non-fatal).
        ready_to_copy:   True when no warnings were raised.
        well_identity:   Operator / lease / district fields as strings.
        depths:          Total depth, BUQW depth, plug-back TD (if any).
        casing:          List of casing rows with fractional OD strings.
        perforations:    List of perforation intervals.
        proposed_plugs:  Plug program rows with integer depth strings.
        certification:   Signature name, title, and formatted date.
    """
    api_number: str
    warnings: list[str]
    ready_to_copy: bool
    well_identity: dict[str, str | None]
    depths: dict[str, str | None]
    casing: list[dict[str, str | None]]
    perforations: list[dict[str, str | None]]
    proposed_plugs: list[dict[str, str | None]]
    certification: dict[str, str | None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_number":     self.api_number,
            "warnings":       self.warnings,
            "ready_to_copy":  self.ready_to_copy,
            "well_identity":  self.well_identity,
            "depths":         self.depths,
            "casing":         self.casing,
            "perforations":   self.perforations,
            "proposed_plugs": self.proposed_plugs,
            "certification":  self.certification,
        }


# ---------------------------------------------------------------------------
# Main formatter
# ---------------------------------------------------------------------------

def format_for_portal(
    api_number: str,
    fetcher,
    operator_overrides: Optional[dict[str, Any]] = None,
) -> tuple[PortalFormatResult, list]:
    """Build portal-ready string values from RRC lookup + §3.14 engine output.

    Single fetcher call: calls :func:`prefill_w3a` once, then runs
    ``_wellbore_from_form`` + ``compute_plug_program`` locally so there is
    no second network round-trip.

    Args:
        api_number:        RRC API number for the well.
        fetcher:           Any object with a ``lookup_well_by_api`` method
                           (RRCRoRQFetcher or MockFetcher).
        operator_overrides: Optional dict of operator-supplied field values
                            passed straight to :func:`prefill_w3a`.

    Returns:
        A ``(PortalFormatResult, conflicts)`` tuple where *conflicts* is the
        list of :class:`~plugfile.w3a_schema.FieldConflict` objects from
        :func:`prefill_w3a`.
    """
    form, conflicts = prefill_w3a(
        api_number, fetcher, operator_overrides=operator_overrides
    )

    warnings: list[str] = []

    # ── API number validation ────────────────────────────────────────────────
    api_valid, api_msg = validate_api_number(api_number)
    if not api_valid and api_msg:
        warnings.append(api_msg)

    # ── Well identity ────────────────────────────────────────────────────────
    well_identity: dict[str, str | None] = {
        "operator_name":     form.operator_name,
        "operator_p5_number": form.operator_p5_number,
        "rrc_district":      form.rrc_district,
        "county":            form.county,
        "well_number":       form.well_number,
        "lease_name":        form.lease_name,
        "field_name":        getattr(form, "field_name", None),
        "lease_number":      getattr(form, "lease_number", None),
    }

    # ── Depths ──────────────────────────────────────────────────────────────
    total_depth_ft    = getattr(form, "total_depth_ft", None)
    buqw_depth_ft     = getattr(form, "buqw_depth_ft", None)
    plug_back_td_ft   = getattr(form, "plug_back_td_ft", None)  # W3Form only

    if total_depth_ft is None:
        warnings.append("total_depth_ft is not set — depth fields will be blank.")
    if buqw_depth_ft is None:
        warnings.append(
            "buqw_depth_ft is not set — BUQW depth field will be blank. "
            "Upload the GAU letter to auto-populate."
        )

    depths: dict[str, str | None] = {
        "total_depth_ft":    depth_to_portal(total_depth_ft),
        "buqw_depth_ft":     depth_to_portal(buqw_depth_ft),
        "plug_back_td_ft":   depth_to_portal(plug_back_td_ft),
        "gau_letter_reference": getattr(form, "gau_letter_reference", None),
        "gau_letter_date":   _safe_date(form, "gau_letter_date", warnings),
    }

    # ── Casing ──────────────────────────────────────────────────────────────
    casing_rows: list[dict[str, str | None]] = []
    for i, row in enumerate(getattr(form, "casing_record", []) or []):
        od_raw = row.get("od_in")
        if od_raw is None:
            warnings.append(f"Casing row {i+1}: od_in is missing.")
            od_fmt = None
        else:
            try:
                od_fmt = od_to_fraction(float(od_raw))
            except Exception:
                warnings.append(
                    f"Casing row {i+1}: cannot convert od_in={od_raw!r} to fraction."
                )
                od_fmt = str(od_raw)

        casing_rows.append({
            "kind":              row.get("kind"),
            "od_in":             od_fmt,
            "set_depth_ft":      depth_to_portal(row.get("set_depth_ft")),
            "top_of_cement_ft":  depth_to_portal(row.get("top_of_cement_ft")),
            "weight_lb_per_ft":  _optional_str(row.get("weight_lb_per_ft")),
            "grade":             row.get("grade"),
        })

    # ── Perforations ────────────────────────────────────────────────────────
    perf_rows: list[dict[str, str | None]] = []
    for row in getattr(form, "perforations", []) or []:
        perf_rows.append({
            "top_ft":    depth_to_portal(row.get("top_ft")),
            "bottom_ft": depth_to_portal(row.get("bottom_ft")),
            "zone_name": row.get("zone_name"),
            "status":    row.get("status"),
        })

    # ── Proposed plug program ────────────────────────────────────────────────
    # Build fresh from engine — no second fetcher call.
    try:
        wellbore  = _wellbore_from_form(form)
        plug_reqs = compute_plug_program(wellbore)
    except Exception as exc:
        warnings.append(f"Plug-program computation failed: {exc}")
        plug_reqs = []

    proposed_plugs: list[dict[str, str | None]] = []
    for rank, plug in enumerate(plug_reqs, start=1):
        vol = plug.volume
        proposed_plugs.append({
            "rank":            str(rank),
            "name":            plug.name,
            "top_ft":          depth_to_portal(plug.top_ft),
            "bottom_ft":       depth_to_portal(plug.bottom_ft),
            "bore":            plug.bore,
            "cite":            plug.cite,
            "volume_sacks":    sacks_to_portal(getattr(vol, "volume_sacks", None)),
            "rationale":       plug.rationale,
        })

    # ── Certification ────────────────────────────────────────────────────────
    certification: dict[str, str | None] = {
        "operator_signature_name": getattr(form, "operator_signature_name", None),
        "operator_title":          getattr(form, "operator_title", None),
        "certification_date":      _safe_date(form, "certification_date", warnings),
    }

    ready_to_copy = len(warnings) == 0

    result = PortalFormatResult(
        api_number=api_number,
        warnings=warnings,
        ready_to_copy=ready_to_copy,
        well_identity=well_identity,
        depths=depths,
        casing=casing_rows,
        perforations=perf_rows,
        proposed_plugs=proposed_plugs,
        certification=certification,
    )
    return result, conflicts


def format_for_portal_with_mock(
    api_number: str,
    operator_overrides: Optional[dict[str, Any]] = None,
) -> tuple[PortalFormatResult, list]:
    """Convenience wrapper that uses :class:`~plugfile.lookups.MockFetcher`."""
    return format_for_portal(api_number, MockFetcher(), operator_overrides)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _safe_date(form, attr: str, warnings: list[str]) -> str | None:
    """Try to format a date field; append a warning if conversion fails."""
    raw = getattr(form, attr, None)
    if not raw:
        return None
    try:
        return date_to_portal(raw)
    except ValueError as exc:
        warnings.append(str(exc))
        return raw  # return raw value so the UI can still display it


def _optional_str(value) -> str | None:
    """Return str(value) or None when value is None."""
    return None if value is None else str(value)
