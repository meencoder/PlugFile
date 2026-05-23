"""Area-of-Review (AOR) Helper for Texas RRC plugging.

Before a well is plugged the operator must review the area around it for
other wells and zones that could provide a conduit for fluid movement —
the "area of review" (AOR). The RRC recommends doing this search in the
RRC GIS Viewer (submission training deck, p.16).

The GIS Viewer is an **external, interactive map with no public API**, so
Plugfile cannot run the spatial query itself. This module instead does the
two things software *can* do well:

  1. ``build_review_guidance()`` — emit a deterministic, well-specific
     checklist that walks the operator through the GIS Viewer search:
     where to click, the ½-mile radius, which well categories to look for,
     and exactly what to record for each hit.

  2. ``assess_aor()`` — take the findings the operator entered (the
     ``aor_findings`` list on the W-3A) and evaluate each one against the
     AOR rules: is it inside the review radius? does the zone it penetrates
     need an isolation plug? For zones that do, it computes the required
     §3.14(d)(1) straddle plug (50 ft above / 50 ft below) and its cement
     volume by reusing the existing rule engine — no new plug math here.

Usage::

    from plugfile.aor import assess_aor_with_mock

    findings = [
        {"well_id": "42-371-99887", "zone_name": "San Andres",
         "depth_ft": 4200, "distance_mi": 0.3, "direction": "NE"},
    ]
    assessment, conflicts = assess_aor_with_mock(
        "42-371-30001", operator_overrides={"aor_findings": findings}
    )
    for f in assessment.findings:
        print(f.well_id, f.requires_isolation, f.isolation_volume_sacks)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .lookups import Fetcher, MockFetcher
from .prefill import FieldConflict, _wellbore_from_form
from .prefill_w3a import prefill_w3a
from .tac_3_14 import (
    GENERAL_PLUG_ABOVE_FT,
    GENERAL_PLUG_BELOW_FT,
    _cylinder_plugs_split,
)


# ---- AOR constants ----------------------------------------------------------

AOR_RADIUS_MI = 0.5                       # ½-mile review radius (standard SWR AOR)
AOR_RADIUS_FT = 2640.0                    # 0.5 mi expressed in feet
AOR_STRADDLE_ABOVE_FT = GENERAL_PLUG_ABOVE_FT   # 50 ft above the zone
AOR_STRADDLE_BELOW_FT = GENERAL_PLUG_BELOW_FT   # 50 ft below the zone
AOR_CITE = "16 TAC §3.14(d)(1)"           # general-rule straddle plug
RRC_GIS_VIEWER_URL = "https://gis.rrc.texas.gov/GISViewer/"


# ---- output types -----------------------------------------------------------

@dataclass
class AORReviewStep:
    """One step in the manual GIS-Viewer AOR review checklist."""
    order: int
    title: str
    detail: str


@dataclass
class AORFindingAssessment:
    """Evaluation of one operator-entered nearby-well finding."""
    well_id: str | None
    zone_name: str | None
    depth_ft: float | None
    distance_mi: float | None
    direction: str | None
    in_aor: bool                       # within the ½-mile review radius
    requires_isolation: bool           # zone must be isolated by a plug
    isolation_top_ft: float | None     # recommended straddle plug top
    isolation_bottom_ft: float | None  # recommended straddle plug bottom
    isolation_volume_sacks: float | None
    isolation_bore: str | None         # bore at the zone (inside_casing / open_hole)
    cite: str | None
    note: str                          # human-readable explanation


@dataclass
class AORAssessment:
    """Full AOR assessment for one wellbore."""
    api_number: str
    operator_name: str | None
    lease_name: str | None
    county: str | None
    rrc_district: str | None
    radius_mi: float
    total_depth_ft: float
    finding_count: int
    in_aor_count: int
    isolation_required_count: int
    total_isolation_sacks: float | None
    findings: list[AORFindingAssessment]
    review_guidance: list[AORReviewStep]
    gis_viewer_url: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_number": self.api_number,
            "operator_name": self.operator_name,
            "lease_name": self.lease_name,
            "county": self.county,
            "rrc_district": self.rrc_district,
            "radius_mi": self.radius_mi,
            "total_depth_ft": self.total_depth_ft,
            "finding_count": self.finding_count,
            "in_aor_count": self.in_aor_count,
            "isolation_required_count": self.isolation_required_count,
            "total_isolation_sacks": self.total_isolation_sacks,
            "gis_viewer_url": self.gis_viewer_url,
            "warnings": self.warnings,
            "review_guidance": [
                {"order": s.order, "title": s.title, "detail": s.detail}
                for s in self.review_guidance
            ],
            "findings": [
                {
                    "well_id": f.well_id,
                    "zone_name": f.zone_name,
                    "depth_ft": f.depth_ft,
                    "distance_mi": f.distance_mi,
                    "direction": f.direction,
                    "in_aor": f.in_aor,
                    "requires_isolation": f.requires_isolation,
                    "isolation_top_ft": f.isolation_top_ft,
                    "isolation_bottom_ft": f.isolation_bottom_ft,
                    "isolation_volume_sacks": f.isolation_volume_sacks,
                    "isolation_bore": f.isolation_bore,
                    "cite": f.cite,
                    "note": f.note,
                }
                for f in self.findings
            ],
        }


# ---- manual GIS-Viewer review checklist -------------------------------------

def build_review_guidance(
    *,
    api_number: str,
    operator_name: str | None,
    county: str | None,
    rrc_district: str | None,
) -> list[AORReviewStep]:
    """Build the well-specific manual AOR review checklist.

    The steps are deterministic but interpolate the well's identity so the
    operator sees exactly what to search for. This is the part of the AOR
    that must be done by hand in the GIS Viewer (no public spatial API).
    """
    where = county or "the well's county"
    dist = rrc_district or "the well's district"
    return [
        AORReviewStep(
            1,
            "Open the RRC Public GIS Viewer",
            f"Go to {RRC_GIS_VIEWER_URL} and accept the disclaimer. "
            "Turn on the 'Wells' and 'Injection/Disposal (UIC)' map layers.",
        ),
        AORReviewStep(
            2,
            "Locate the subject well",
            f"Search API {api_number} (operator: {operator_name or 'see Form P-5'}, "
            f"county: {where}, district {dist}). Confirm the surface location "
            "pin matches the W-3A footages before measuring.",
        ),
        AORReviewStep(
            3,
            f"Draw the {AOR_RADIUS_MI}-mile review radius",
            f"Use the Measure / Buffer tool to draw a {AOR_RADIUS_MI}-mile "
            f"({int(AOR_RADIUS_FT)} ft) circle centered on the subject well. "
            "Everything inside this circle is in the area of review.",
        ),
        AORReviewStep(
            4,
            "Identify wells of concern inside the radius",
            "Within the circle, list every: (a) active or inactive "
            "injection/disposal (UIC) well, (b) unplugged well — producing or "
            "shut-in, and (c) well completed in a shallower zone that could "
            "act as a fluid conduit. Ignore wells already plugged with a "
            "filed W-3.",
        ),
        AORReviewStep(
            5,
            "Record the data for each well of concern",
            "For each, note: API/lease-well id, the producing or injection "
            "zone name, that zone's approximate depth (ft), and the distance "
            "and direction from the subject well.",
        ),
        AORReviewStep(
            6,
            "Flag corrosive / over-pressured zones",
            "Check district records for any corrosive or abnormally "
            "pressured zone the subject wellbore penetrates. These require "
            "isolation regardless of nearby wells.",
        ),
        AORReviewStep(
            7,
            "Enter findings into Plugfile",
            "Add each well of concern to the W-3A 'aor_findings' list "
            "(well_id, zone_name, depth_ft, distance_mi, direction). Re-run "
            "the AOR assessment — Plugfile will compute the required isolation "
            "plug for every zone that needs one.",
        ),
    ]


# ---- isolation-plug computation ---------------------------------------------

def _isolation_plug(well, depth_ft: float, total_depth_ft: float):
    """Compute the §3.14(d)(1) straddle plug for a zone at *depth_ft*.

    Returns ``(top_ft, bottom_ft, sacks, bore)`` or raises ValueError when
    the depth falls outside the described wellbore. The plug straddles the
    zone (50 ft above / 50 ft below), clamped to [0, total_depth_ft].
    """
    top = max(0.0, depth_ft - AOR_STRADDLE_ABOVE_FT)
    bottom = min(total_depth_ft, depth_ft + AOR_STRADDLE_BELOW_FT)
    if bottom <= top:
        raise ValueError(
            f"straddle interval collapses (top={top}, bottom={bottom})"
        )
    segs = _cylinder_plugs_split(
        name=f"aor_isolation_{int(round(depth_ft))}",
        cite=AOR_CITE,
        rule_path="general",
        top_ft=top,
        bottom_ft=bottom,
        well=well,
        rationale=(
            f"Isolation plug straddling the {int(round(depth_ft))} ft zone "
            "open to a nearby well within the area of review."
        ),
    )
    sacks = sum(s.volume.sacks for s in segs)
    bore = segs[0].bore if len(segs) == 1 else "mixed"
    return top, bottom, round(sacks, 2), bore


# ---- public API -------------------------------------------------------------

def assess_aor(
    api_number: str,
    fetcher: Fetcher,
    operator_overrides: dict[str, Any] | None = None,
) -> tuple[AORAssessment, list[FieldConflict]]:
    """Evaluate the area of review for a wellbore.

    Gathers well identity + completion data via :func:`prefill_w3a`, builds
    the manual GIS-Viewer review checklist, and evaluates every operator-
    entered ``aor_findings`` entry: classifies it as in/out of the review
    radius and, when isolation is required, computes the §3.14(d)(1)
    straddle plug and its cement volume.

    Returns ``(AORAssessment, conflicts)`` where *conflicts* comes from
    :func:`prefill_w3a` (advisory override/RRC mismatches).
    """
    form, conflicts = prefill_w3a(
        api_number, fetcher, operator_overrides=operator_overrides
    )

    total_depth_ft = form.total_depth_ft or 0.0
    well = _wellbore_from_form(form)

    warnings: list[str] = []
    findings_out: list[AORFindingAssessment] = []
    total_sacks = 0.0
    in_aor_count = 0
    isolation_count = 0

    raw_findings = list(form.aor_findings or [])

    for idx, raw in enumerate(raw_findings, start=1):
        well_id = raw.get("well_id")
        zone_name = raw.get("zone_name")
        depth_ft = raw.get("depth_ft")
        distance_mi = raw.get("distance_mi")
        direction = raw.get("direction")
        explicit_iso = raw.get("requires_isolation")  # may be None

        label = well_id or zone_name or f"finding {idx}"

        # ── inside the review radius? ──────────────────────────────────────
        if distance_mi is None:
            in_aor = True
            warnings.append(
                f"{label}: no distance_mi given — assumed inside the "
                f"{AOR_RADIUS_MI}-mi review radius. Verify in the GIS Viewer."
            )
        else:
            in_aor = distance_mi <= AOR_RADIUS_MI
        if in_aor:
            in_aor_count += 1

        # ── does the zone require isolation? ───────────────────────────────
        if explicit_iso is not None:
            requires_iso = bool(explicit_iso) and in_aor
        else:
            # Infer: a zone inside the AOR, penetrated by the subject wellbore
            # (0 < depth ≤ TD), is a conduit risk → isolate it.
            requires_iso = (
                in_aor
                and depth_ft is not None
                and 0 < depth_ft <= total_depth_ft
            )

        iso_top = iso_bottom = iso_sacks = iso_bore = None
        cite = None

        if requires_iso:
            if depth_ft is None:
                requires_iso = False
                note = (
                    "Marked for isolation but no zone depth given — cannot "
                    "place a plug. Add depth_ft to compute the straddle plug."
                )
                warnings.append(f"{label}: {note}")
            elif depth_ft > total_depth_ft:
                requires_iso = False
                note = (
                    f"Zone depth {depth_ft} ft is below the subject well TD "
                    f"({total_depth_ft} ft) — not penetrated, no plug needed."
                )
            else:
                try:
                    iso_top, iso_bottom, iso_sacks, iso_bore = _isolation_plug(
                        well, float(depth_ft), total_depth_ft
                    )
                    cite = AOR_CITE
                    isolation_count += 1
                    if iso_sacks:
                        total_sacks += iso_sacks
                    note = (
                        f"Requires a §3.14(d)(1) isolation plug from "
                        f"{int(iso_top)}–{int(iso_bottom)} ft "
                        f"(~{iso_sacks} sx) to isolate the {zone_name or 'zone'}."
                    )
                except ValueError as exc:
                    note = (
                        f"Zone needs isolation but the plug interval could "
                        f"not be computed: {exc}"
                    )
                    warnings.append(f"{label}: {note}")
        else:
            if not in_aor:
                note = (
                    f"Outside the {AOR_RADIUS_MI}-mi review radius "
                    f"({distance_mi} mi) — informational only."
                )
            else:
                note = (
                    "Inside the review radius but does not require an "
                    "isolation plug (no penetrated zone flagged)."
                )

        findings_out.append(AORFindingAssessment(
            well_id=well_id,
            zone_name=zone_name,
            depth_ft=depth_ft,
            distance_mi=distance_mi,
            direction=direction,
            in_aor=in_aor,
            requires_isolation=requires_iso,
            isolation_top_ft=iso_top,
            isolation_bottom_ft=iso_bottom,
            isolation_volume_sacks=iso_sacks,
            isolation_bore=iso_bore,
            cite=cite,
            note=note,
        ))

    if not raw_findings:
        warnings.append(
            "No AOR findings entered yet. Complete the GIS-Viewer review "
            "checklist below, then add each well of concern to aor_findings."
        )

    guidance = build_review_guidance(
        api_number=api_number,
        operator_name=form.operator_name,
        county=form.county,
        rrc_district=form.rrc_district,
    )

    assessment = AORAssessment(
        api_number=api_number,
        operator_name=form.operator_name,
        lease_name=form.lease_name,
        county=form.county,
        rrc_district=form.rrc_district,
        radius_mi=AOR_RADIUS_MI,
        total_depth_ft=total_depth_ft,
        finding_count=len(raw_findings),
        in_aor_count=in_aor_count,
        isolation_required_count=isolation_count,
        total_isolation_sacks=round(total_sacks, 2) if total_sacks else None,
        findings=findings_out,
        review_guidance=guidance,
        gis_viewer_url=RRC_GIS_VIEWER_URL,
        warnings=warnings,
    )
    return assessment, conflicts


def assess_aor_with_mock(
    api_number: str,
    operator_overrides: dict[str, Any] | None = None,
) -> tuple[AORAssessment, list[FieldConflict]]:
    """Shortcut for tests / demos using the in-memory MockFetcher."""
    return assess_aor(api_number, MockFetcher(), operator_overrides)
