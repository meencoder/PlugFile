"""Prefill engine for Texas RRC Form W-3.

Given an API number and a `Fetcher`, populate a `W3Form` from authoritative
sources (RRC well/operator/GAU/completion records). Run the deterministic
TAC §3.14 plug-program engine to fill the COMPUTED Section VIII fields.
Cross-check operator-provided overrides against authoritative values and
emit `FieldConflict` warnings (per the warn-and-flag policy).

Architecture:

    api_number + fetcher  -->  Sections I/II/III/IV/VI/VII (authoritative)
            +
    operator_overrides    -->  perforation status, plugging_date, certification
            +
    deterministic core    -->  Section VIII plug_record (computed)
            =
                              W3Form (populated)
                              + list[FieldConflict] (warnings)

The conflict detector treats authoritative sources as primary. If an
operator override disagrees, the *authoritative* value wins in the form,
and a warning is recorded so the operator (or LLM) can review and resolve.
This matches the chosen policy: warn + flag for review, never silently
overwrite a discrepancy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Literal

from .geometry import (
    BUQW,
    CasingKind,
    CasingString,
    OpenHoleSection,
    Perforation,
    Wellbore,
)
from .lookups import Fetcher, FetcherError, MockFetcher
from .tac_3_14 import compute_plug_program
from .w3_schema import FieldSource, W3Form, W3_SCHEMA


# ---- conflict reporting ----------------------------------------------------

Severity = Literal["info", "warn", "error"]


@dataclass(frozen=True)
class FieldConflict:
    """Discrepancy between an operator-provided value and the authoritative
    source for a field."""
    field_name: str
    operator_value: Any
    authoritative_value: Any
    source: FieldSource
    severity: Severity
    message: str

    def render(self) -> str:
        return (
            f"[{self.severity.upper():5s}] {self.field_name}: "
            f"operator={self.operator_value!r} vs "
            f"{self.source.value}={self.authoritative_value!r} -- "
            f"{self.message}"
        )


# ---- helpers: build a Wellbore from a populated W3Form ---------------------

def _wellbore_from_form(form: W3Form) -> Wellbore:
    """Translate a populated W3Form into the Wellbore data model used by the
    deterministic engines.
    """
    if form.api_number is None:
        raise ValueError("Cannot build Wellbore: api_number is unset")
    if form.buqw_depth_ft is None or form.gau_letter_reference is None:
        raise ValueError("Cannot build Wellbore: BUQW data incomplete")
    if form.total_depth_ft is None:
        raise ValueError("Cannot build Wellbore: total_depth_ft is unset")

    casing = tuple(
        CasingString(
            kind=CasingKind(c["kind"]),
            od_in=float(c["od_in"]),
            id_in=_id_from_od(c["od_in"], c.get("weight_lb_per_ft")),
            set_depth_ft=float(c["set_depth_ft"]),
            top_of_cement_ft=float(c["top_of_cement_ft"]),
            weight_lb_per_ft=c.get("weight_lb_per_ft"),
            grade=c.get("grade"),
        )
        for c in form.casing_record
    )

    perfs = tuple(
        Perforation(
            top_ft=float(p["top_ft"]),
            bottom_ft=float(p["bottom_ft"]),
            zone_name=p["zone_name"],
            status=p.get("status", "producing"),
        )
        for p in form.perforations
    )

    # Open hole below the deepest casing shoe down to TD. Bit size is
    # estimated from the deepest casing OD (typical: bit ≈ casing OD - 0.75").
    open_hole: tuple[OpenHoleSection, ...] = ()
    if casing:
        deepest = max(casing, key=lambda c: c.set_depth_ft)
        if deepest.set_depth_ft < form.total_depth_ft:
            open_hole = (
                OpenHoleSection(
                    top_ft=deepest.set_depth_ft,
                    bottom_ft=form.total_depth_ft,
                    bit_size_in=_typical_bit_size_for_od(deepest.od_in),
                ),
            )

    return Wellbore(
        api_number=form.api_number,
        operator=form.operator_name or "",
        lease_name=form.lease_name or "",
        well_number=form.well_number or "",
        county=form.county or "",
        total_depth_ft=form.total_depth_ft,
        buqw=BUQW(
            depth_ft=form.buqw_depth_ft,
            source=form.gau_letter_reference,
        ),
        casing=casing,
        perforations=perfs,
        open_hole=open_hole,
    )


# Casing OD -> ID lookup table for common API casing weights. When a weight
# is provided we use the exact ID; otherwise we fall back to a representative
# nominal ID. Covers the OD/weight combos in the Phase 1A fixtures.
_CASING_ID_TABLE: dict[tuple[float, float | None], float] = {
    (13.375, 54.5): 12.515,
    (9.625, 36.0): 8.921,
    (9.625, 40.0): 8.835,
    (8.625, 24.0): 8.097,
    (7.0, 23.0): 6.366,
    (5.5, 17.0): 4.892,
    (4.5, 11.6): 4.052,
}


def _id_from_od(od_in: float, weight_lb_per_ft: float | None) -> float:
    """Look up casing ID from OD + weight (preferred) or estimate."""
    key = (float(od_in), weight_lb_per_ft)
    if key in _CASING_ID_TABLE:
        return _CASING_ID_TABLE[key]
    # Try without weight
    od_only = [(o, w) for (o, w) in _CASING_ID_TABLE if o == float(od_in)]
    if od_only:
        return _CASING_ID_TABLE[od_only[0]]
    # Fallback: assume thin-wall (ID = OD - 0.5")
    return float(od_in) - 0.5


# Typical bit size used to drill a hole that ends with this casing OD.
# Drift = OD + ~0.5" (annular clearance). Used for open-hole bit_size.
_BIT_SIZE_FOR_OD: dict[float, float] = {
    13.375: 17.5,
    9.625: 12.25,
    8.625: 11.0,
    7.0: 8.75,
    5.5: 6.125,
    4.5: 5.875,
}
# After production casing, the open hole BELOW that shoe is drilled with the
# bit that drilled the production hole — typically 1 size smaller than what
# drilled INTO the production casing seat. Use these for OH-below-deepest.
_OH_BELOW_BIT_FOR_OD: dict[float, float] = {
    5.5: 4.75,
    4.5: 3.875,
    7.0: 6.125,
    9.625: 8.5,
    13.375: 12.25,
}


def _typical_bit_size_for_od(od_in: float) -> float:
    """Bit size used to drill the open-hole interval below a casing shoe of
    the given OD."""
    return _OH_BELOW_BIT_FOR_OD.get(float(od_in), float(od_in) - 0.75)


# ---- conflict detection ----------------------------------------------------

_FIELD_SOURCE_BY_NAME = {f.name: f.source for f in W3_SCHEMA}


def _conflicts_from_overrides(
    form: W3Form, overrides: dict[str, Any]
) -> list[FieldConflict]:
    """Compare each scalar override against the populated form value.

    Per the warn-and-flag policy, mismatches against authoritative-source
    fields produce a `warn`-severity conflict. Mismatches against operator-
    sourced fields (perforation_status, plugging_date) are `info`-only,
    since the operator's own value is supposed to win there.
    """
    conflicts: list[FieldConflict] = []
    for name, op_value in overrides.items():
        if name == "perforations":
            continue  # handled via merging during prefill, not as overrides
        if not hasattr(form, name):
            continue  # unknown field — silently ignore
        auth_value = getattr(form, name)
        if op_value is None or auth_value is None:
            continue
        if op_value == auth_value:
            continue
        source = _FIELD_SOURCE_BY_NAME.get(name, FieldSource.OPERATOR_INPUT)
        severity: Severity = (
            "info"
            if source in (
                FieldSource.OPERATOR_INPUT,
                FieldSource.OPERATOR_OBSERVED,
                FieldSource.OPERATOR_CERTIFICATION,
            )
            else "warn"
        )
        conflicts.append(
            FieldConflict(
                field_name=name,
                operator_value=op_value,
                authoritative_value=auth_value,
                source=source,
                severity=severity,
                message=(
                    f"Operator value differs from {source.value}; "
                    "authoritative value retained — operator should "
                    "verify or update the source record."
                ),
            )
        )
    return conflicts


# ---- main entry point ------------------------------------------------------

def prefill_w3(
    api_number: str,
    fetcher: Fetcher,
    operator_overrides: dict[str, Any] | None = None,
    *,
    plugging_date: str | None = None,
) -> tuple[W3Form, list[FieldConflict]]:
    """Populate a W3Form for the given API number using `fetcher` for
    authoritative data and `operator_overrides` for operator-sourced fields.

    Returns (form, conflicts). Conflicts are purely advisory — the form is
    always populated with authoritative values where available.

    `operator_overrides` keys may include:
      * scalar W-3 field names (e.g. plugging_date, operator_signature_name)
      * "perforations": list of {"top_ft", "zone_name", "status"} that
        merge with the completion-record perforations to set the status
        field (which only the operator knows at plug time).
    """
    overrides = operator_overrides or {}
    form = W3Form()

    # ---- Section I + II: well-master record -------------------------------
    well = fetcher.lookup_well_by_api(api_number)
    for k, v in well.items():
        if hasattr(form, k):
            setattr(form, k, v)

    # ---- Section I (cont.): operator -------------------------------------
    p5 = None
    if hasattr(fetcher, "operator_p5_for_api"):
        try:
            p5 = fetcher.operator_p5_for_api(api_number)  # type: ignore[attr-defined]
        except FetcherError:
            p5 = None
    if p5:
        op = fetcher.lookup_operator(p5)
        for k, v in op.items():
            if hasattr(form, k):
                setattr(form, k, v)

    # ---- Section VII: GAU --------------------------------------------------
    gau = fetcher.lookup_gau(api_number)
    form.buqw_depth_ft = gau["buqw_depth_ft"]
    form.gau_letter_reference = gau["gau_letter_reference"]

    # ---- Section III/IV/VI: completion record -----------------------------
    comp = fetcher.lookup_completion(api_number)
    form.total_depth_ft = comp["total_depth_ft"]
    form.spud_date = comp["spud_date"]
    form.completion_date = comp["completion_date"]
    form.casing_record = list(comp["casing_record"])

    # Perforations: completion record gives geometry; operator gives status.
    op_perfs_index = {
        (float(p["top_ft"]), p["zone_name"]): p
        for p in overrides.get("perforations", [])
    }
    merged_perfs: list[dict[str, Any]] = []
    for cp in comp["perforations"]:
        key = (float(cp["top_ft"]), cp["zone_name"])
        op_match = op_perfs_index.get(key)
        merged_perfs.append({
            **cp,
            "status": (op_match or {}).get("status", "producing"),
        })
    form.perforations = merged_perfs

    # ---- plugging_date (Section III) --------------------------------------
    form.plugging_date = (
        plugging_date
        or overrides.get("plugging_date")
        or form.plugging_date
    )

    # ---- Section VIII: COMPUTED plug record -------------------------------
    well_obj = _wellbore_from_form(form)
    plugs = compute_plug_program(well_obj)
    form.plug_record = [_plug_to_dict(p) for p in plugs]
    form.plug_program_rule_paths = sorted({p.rule_path for p in plugs})
    form.buqw_protected_by_surface_casing = (
        well_obj.buqw_protected_by_surface_casing()
    )

    # ---- Section X: certification (operator-only) -------------------------
    for cert_field in (
        "operator_signature_name",
        "operator_title",
        "certification_date",
        "cementing_company",
    ):
        if cert_field in overrides and overrides[cert_field] is not None:
            setattr(form, cert_field, overrides[cert_field])

    # ---- conflict detection ----------------------------------------------
    conflicts = _conflicts_from_overrides(form, overrides)

    return form, conflicts


def _plug_to_dict(plug: Any) -> dict[str, Any]:
    """Flatten a PlugRequirement (with its embedded CementVolume) into the
    flat shape expected by the W-3 plug_record array."""
    if is_dataclass(plug):
        d = asdict(plug)
    else:
        d = dict(plug)
    vol = d.pop("volume", {}) or {}
    return {
        "name": d.get("name"),
        "top_ft": d.get("top_ft"),
        "bottom_ft": d.get("bottom_ft"),
        "bore": d.get("bore"),
        "bore_diameter_in": d.get("bore_diameter_in"),
        "volume_ft3": vol.get("ft3"),
        "volume_bbl": vol.get("bbl"),
        "volume_sacks": vol.get("sacks"),
        "excess_factor": vol.get("excess_factor"),
        "cite": d.get("cite"),
        "rule_path": d.get("rule_path"),
    }


# Convenience: a one-call prefill using the MockFetcher.
def prefill_w3_with_mock(
    api_number: str,
    operator_overrides: dict[str, Any] | None = None,
    *,
    plugging_date: str | None = None,
) -> tuple[W3Form, list[FieldConflict]]:
    """Shortcut for tests / demos."""
    return prefill_w3(
        api_number,
        MockFetcher(),
        operator_overrides=operator_overrides,
        plugging_date=plugging_date,
    )
