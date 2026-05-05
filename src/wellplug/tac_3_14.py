"""TAC §3.14 (Statewide Rule 14, *Plugging*) rule encoding.

This module turns a `Wellbore` into a list of `PlugRequirement`s — what plugs
must be set, where, and computed cement volumes — by applying:

    GENERAL RULE
    ------------
    For each "feature" that triggers a plug under §3.14(d), set a cement plug
    extending **at least 50 ft above and 50 ft below** the feature, in the
    bore the feature occupies. Features encoded here:
      * casing shoes (surface, intermediate, production, liner)
      * perforated/producing intervals
      * the BUQW *when surface casing already covers it* (general path)

    SPECIAL CASE: BUQW NOT COVERED BY SURFACE CASING
    -------------------------------------------------
    If the surface-casing string is NOT set deeper than BUQW (or its top of
    cement does not reach surface), §3.14 requires a **continuous cement
    column from BUQW to ground level** rather than a discrete 100-ft plug.
    This is the legacy / pre-modern-permit case — common on Texas wells
    drilled before mandatory BUQW protection requirements were strict.

The CITES below reference §3.14 paragraphs *as best understood at the time of
encoding*. Paragraph numbering must be re-verified against the current
published rule before any production filing — see README "Citation policy".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .cement_volume import (
    DEFAULT_OPEN_HOLE_EXCESS,
    CementVolume,
    annular_plug_volume,
    cylinder_plug_volume,
)
from .geometry import CasingKind, CasingString, Perforation, Wellbore


# ---- TAC §3.14 numeric constants (encode once, cite once) -------------------

GENERAL_PLUG_ABOVE_FT = 50.0          # §3.14(d)(1): "at least 50 ft above"
GENERAL_PLUG_BELOW_FT = 50.0          # §3.14(d)(1): "at least 50 ft below"
SURFACE_PLUG_LENGTH_FT = 50.0         # §3.14(d)(6): top plug from surface
BUQW_GENERAL_ABOVE_FT = 50.0          # §3.14(d)(2) general path
BUQW_GENERAL_BELOW_FT = 50.0


# ---- result type ------------------------------------------------------------

PlugBore = Literal["inside_casing", "open_hole", "annulus"]


@dataclass(frozen=True)
class PlugRequirement:
    """One plug the W-3 program must specify."""
    name: str                       # human label, e.g. "surface_casing_shoe"
    rule_path: Literal["general", "special_buqw_uncovered"]
    cite: str                       # best-effort TAC paragraph cite
    top_ft: float                   # MD ft (0 = surface)
    bottom_ft: float
    bore: PlugBore
    bore_diameter_in: float         # the relevant bore diameter
    annulus_inner_od_in: float | None  # if annular plug
    rationale: str
    volume: CementVolume


# ---- general-rule helpers ---------------------------------------------------

def _bore_for_depth(
    well: Wellbore, depth_ft: float
) -> tuple[PlugBore, float, float | None]:
    """Determine what kind of bore exists at `depth_ft` and the relevant
    diameter(s).

    Returns (bore, bore_diameter_in, inner_od_or_none).
      * "inside_casing"  → diameter = innermost casing ID; inner_od = None
      * "open_hole"      → diameter = bit size; inner_od = None
      * (annular plugs are constructed separately for shoe-coverage cases)
    """
    cas = well.casing_covering(depth_ft)
    if cas is not None:
        return "inside_casing", cas.id_in, None
    for oh in well.open_hole:
        if oh.top_ft <= depth_ft <= oh.bottom_ft:
            return "open_hole", oh.bit_size_in, None
    raise ValueError(
        f"Depth {depth_ft} ft is in neither cased nor open-hole interval — "
        "wellbore description is incomplete."
    )


def _bore_transitions_in(
    well: Wellbore, top_ft: float, bottom_ft: float
) -> list[float]:
    """Return depths strictly between top_ft and bottom_ft where the bore
    *actually* changes (different bore type or different diameter). Used to
    auto-split plugs that straddle a transition.

    Casing shoes that don't change the innermost bore (e.g. an outer surface
    casing shoe when a production casing extends past it) are not transitions
    and don't trigger a split.
    """
    candidates: set[float] = set()
    for c in well.casing:
        if top_ft < c.set_depth_ft < bottom_ft:
            candidates.add(c.set_depth_ft)
    for oh in well.open_hole:
        if top_ft < oh.top_ft < bottom_ft:
            candidates.add(oh.top_ft)
        if top_ft < oh.bottom_ft < bottom_ft:
            candidates.add(oh.bottom_ft)

    transitions: list[float] = []
    eps = 0.01
    for d in sorted(candidates):
        try:
            bore_below, dia_below, _ = _bore_for_depth(well, d - eps)
            bore_above, dia_above, _ = _bore_for_depth(well, d + eps)
        except ValueError:
            # Wellbore description doesn't cover one side — treat as a
            # transition so the caller is forced to think about it.
            transitions.append(d)
            continue
        if bore_below != bore_above or abs(dia_below - dia_above) > 1e-6:
            transitions.append(d)
    return transitions


def _cylinder_plugs_split(
    *,
    name: str,
    cite: str,
    rule_path: Literal["general", "special_buqw_uncovered"],
    top_ft: float,
    bottom_ft: float,
    well: Wellbore,
    rationale: str,
) -> list[PlugRequirement]:
    """Build one or more PlugRequirements covering [top_ft, bottom_ft],
    auto-splitting at bore transitions (casing shoes, open-hole boundaries).

    Common case: a production-casing-shoe plug naturally straddles the shoe
    — half inside casing, half in open hole below. Returning two plugs is
    closer to real W-3 practice than forcing the operator to merge them.
    """
    if bottom_ft <= top_ft:
        raise ValueError(f"{name}: bottom_ft ({bottom_ft}) must be > top_ft ({top_ft})")

    transitions = _bore_transitions_in(well, top_ft, bottom_ft)
    boundaries = [top_ft, *transitions, bottom_ft]

    plugs: list[PlugRequirement] = []
    n_segments = len(boundaries) - 1
    for i in range(n_segments):
        seg_top = boundaries[i]
        seg_bot = boundaries[i + 1]
        # Probe just inside each segment to avoid boundary ambiguity
        midpoint = (seg_top + seg_bot) / 2.0
        bore, dia, _ = _bore_for_depth(well, midpoint)
        excess = DEFAULT_OPEN_HOLE_EXCESS if bore == "open_hole" else 0.0
        vol = cylinder_plug_volume(
            diameter_in=dia,
            length_ft=seg_bot - seg_top,
            excess_factor=excess,
        )
        seg_name = name if n_segments == 1 else f"{name}_seg{i+1}_{bore}"
        seg_rationale = (
            rationale if n_segments == 1
            else f"{rationale} [segment {i+1}/{n_segments}, {bore}]"
        )
        plugs.append(
            PlugRequirement(
                name=seg_name,
                rule_path=rule_path,
                cite=cite,
                top_ft=seg_top,
                bottom_ft=seg_bot,
                bore=bore,
                bore_diameter_in=dia,
                annulus_inner_od_in=None,
                rationale=seg_rationale,
                volume=vol,
            )
        )
    return plugs


# ---- the rule engine --------------------------------------------------------

def general_plug_rule(well: Wellbore) -> list[PlugRequirement]:
    """Apply the §3.14(d) general rule: 50 ft above and below each feature.

    Features:
      * casing shoes (every cemented string in the wellbore)
      * perforated intervals (status != "squeezed")
      * BUQW *only if* surface casing already covers it (general path).
        Otherwise the special-case rule handles BUQW separately.
      * surface plug (50 ft top)
    """
    plugs: list[PlugRequirement] = []

    # --- producing/injection zones (§3.14(d)(3)) ---
    for perf in well.perforations:
        if perf.status == "squeezed":
            continue
        plugs.extend(
            _cylinder_plugs_split(
                name=f"perforation_{perf.zone_name}",
                cite="TAC §3.14(d)(3)",
                rule_path="general",
                top_ft=max(0.0, perf.top_ft - GENERAL_PLUG_ABOVE_FT),
                bottom_ft=perf.bottom_ft + GENERAL_PLUG_BELOW_FT,
                well=well,
                rationale=(
                    f"Plug across {perf.status} zone '{perf.zone_name}' "
                    f"({perf.top_ft:.0f}–{perf.bottom_ft:.0f} ft) with "
                    f"{GENERAL_PLUG_ABOVE_FT:.0f} ft above and "
                    f"{GENERAL_PLUG_BELOW_FT:.0f} ft below."
                ),
            )
        )

    # --- casing shoes (§3.14(d)(1)) ---
    for cas in well.casing:
        # Skip conductor — not a regulated plug feature on its own
        if cas.kind == CasingKind.CONDUCTOR:
            continue
        plugs.extend(
            _cylinder_plugs_split(
                name=f"{cas.kind.value}_casing_shoe",
                cite="TAC §3.14(d)(1)",
                rule_path="general",
                top_ft=max(0.0, cas.set_depth_ft - GENERAL_PLUG_ABOVE_FT),
                bottom_ft=min(
                    cas.set_depth_ft + GENERAL_PLUG_BELOW_FT,
                    well.total_depth_ft,
                ),
                well=well,
                rationale=(
                    f"Plug across {cas.kind.value} casing shoe at "
                    f"{cas.set_depth_ft:.0f} ft with {GENERAL_PLUG_ABOVE_FT:.0f} ft "
                    f"above and {GENERAL_PLUG_BELOW_FT:.0f} ft below."
                ),
            )
        )

    # --- BUQW general path: surface casing covers it ---
    if well.buqw_protected_by_surface_casing():
        plugs.extend(
            _cylinder_plugs_split(
                name="buqw_protective_plug",
                cite="TAC §3.14(d)(2) [general]",
                rule_path="general",
                top_ft=max(0.0, well.buqw.depth_ft - BUQW_GENERAL_ABOVE_FT),
                bottom_ft=well.buqw.depth_ft + BUQW_GENERAL_BELOW_FT,
                well=well,
                rationale=(
                    f"BUQW at {well.buqw.depth_ft:.0f} ft is covered by surface "
                    f"casing; place a 100-ft plug centered on BUQW."
                ),
            )
        )

    # --- surface plug (§3.14(d)(6)) — last 50 ft to ground level ---
    plugs.extend(
        _cylinder_plugs_split(
            name="surface_plug",
            cite="TAC §3.14(d)(6)",
            rule_path="general",
            top_ft=0.0,
            bottom_ft=SURFACE_PLUG_LENGTH_FT,
            well=well,
            rationale=(
                f"Surface plug from ground level to {SURFACE_PLUG_LENGTH_FT:.0f} ft "
                f"to seal the wellbore at the surface."
            ),
        )
    )

    return plugs


def special_buqw_uncovered_rule(well: Wellbore) -> list[PlugRequirement] | None:
    """Apply the §3.14 special case: continuous cement from BUQW to surface
    when surface casing does NOT cover BUQW.

    Returns None if the special case does not apply. Returns a list with one
    long continuous-column plug if it does. The caller is expected to *replace*
    the BUQW plug + surface plug from the general rule with this output.
    """
    if well.buqw_protected_by_surface_casing():
        return None

    # The continuous column runs from surface (0 ft) down to BUQW + 50 ft of
    # margin so the plug is anchored below the protected zone, not just at
    # its base.
    bottom_ft = well.buqw.depth_ft + BUQW_GENERAL_BELOW_FT

    return _cylinder_plugs_split(
        name="buqw_continuous_to_surface",
        cite="TAC §3.14 [special case: BUQW not covered by surface casing]",
        rule_path="special_buqw_uncovered",
        top_ft=0.0,
        bottom_ft=bottom_ft,
        well=well,
        rationale=(
            f"Surface casing does NOT cover BUQW (BUQW at "
            f"{well.buqw.depth_ft:.0f} ft; surface casing inadequate). "
            f"§3.14 special case requires a continuous cement column from "
            f"surface to {bottom_ft:.0f} ft (BUQW + "
            f"{BUQW_GENERAL_BELOW_FT:.0f} ft margin) — replaces both the "
            f"discrete BUQW plug and the surface plug."
        ),
    )


def compute_plug_program(well: Wellbore) -> list[PlugRequirement]:
    """Top-level entry point. Apply the general rule, then merge in the
    special case if it triggers.

    When the BUQW-uncovered special case fires, a continuous cement column
    from surface to BUQW+50 ft supersedes:
      * the surface plug (§3.14(d)(6))
      * the surface-casing-shoe plug (subsumed by the column)

    Plugs deeper than the column (perforation plugs, intermediate/production
    shoe plugs) remain unchanged — they're set first, the column poured on
    top.
    """
    program = general_plug_rule(well)
    special = special_buqw_uncovered_rule(well)
    if special is None:
        program.sort(key=lambda p: p.top_ft)
        return program

    column_bottom = max(p.bottom_ft for p in special)

    def _superseded_by_column(p: PlugRequirement) -> bool:
        # Surface plug always superseded by the continuous column.
        if p.name == "surface_plug" or p.name.startswith("surface_plug_seg"):
            return True
        # Surface casing shoe plug is subsumed if it lies entirely within
        # the column's [0, column_bottom] span.
        if (p.name.startswith("surface_casing_shoe")
                and p.top_ft >= 0.0 and p.bottom_ft <= column_bottom):
            return True
        return False

    program = [p for p in program if not _superseded_by_column(p)]
    program.extend(special)

    # Sort top-down for readability (smallest top_ft first)
    program.sort(key=lambda p: p.top_ft)
    return program
