"""Five representative Texas wellbore geometries for Phase 1A validation.

Each fixture covers a distinct §3.14 path or edge case:

  1. PERMIAN_DEEP_GAS         - Modern deep-gas well; surface casing protects
                                BUQW; production shoe straddles open hole.
  2. EAST_TEXAS_SHALLOW_OIL   - Modern shallow oil well; clean general-rule
                                application.
  3. BUQW_UNCOVERED_LEGACY    - Surface casing set ABOVE BUQW → triggers the
                                special-case continuous-column rule.
  4. NO_SURFACE_CASING_LEGACY - 1950s-era well, no surface-casing string at
                                all → triggers special-case rule.
  5. MULTI_ZONE_PRODUCER      - Multiple producing zones plus an abandoned
                                zone — exercises perforation-plug logic.

Geometries are SYNTHETIC but representative of typical Texas completion
practice. They are not drawn from any specific filed W-3.
"""

from __future__ import annotations

from plugfile.geometry import (
    BUQW,
    CasingKind,
    CasingString,
    OpenHoleSection,
    Perforation,
    Wellbore,
)


# -----------------------------------------------------------------------------
# Fixture 1 — Permian deep gas
# -----------------------------------------------------------------------------

PERMIAN_DEEP_GAS = Wellbore(
    api_number="42-371-30001",          # Pecos County prefix
    operator="Apex Permian Operating LLC",
    lease_name="Heritage A",
    well_number="1H",
    county="Pecos",
    total_depth_ft=10500.0,
    buqw=BUQW(depth_ft=1500.0, source="GAU letter dated 2024-03-12"),
    casing=(
        CasingString(
            kind=CasingKind.SURFACE,
            od_in=13.375, id_in=12.515,
            set_depth_ft=1800.0, top_of_cement_ft=0.0,
            weight_lb_per_ft=54.5, grade="J-55",
        ),
        CasingString(
            kind=CasingKind.INTERMEDIATE,
            od_in=9.625, id_in=8.835,
            set_depth_ft=6500.0, top_of_cement_ft=0.0,
            weight_lb_per_ft=40.0, grade="N-80",
        ),
        CasingString(
            kind=CasingKind.PRODUCTION,
            od_in=5.5, id_in=4.892,
            set_depth_ft=10300.0, top_of_cement_ft=5000.0,
            weight_lb_per_ft=17.0, grade="P-110",
        ),
    ),
    open_hole=(
        OpenHoleSection(top_ft=10300.0, bottom_ft=10500.0, bit_size_in=4.75),
    ),
    perforations=(
        Perforation(
            top_ft=10150.0, bottom_ft=10200.0,
            zone_name="Wolfcamp A", status="producing",
        ),
    ),
    notes="Modern Permian deep gas; surface casing protects BUQW (general rule).",
)


# -----------------------------------------------------------------------------
# Fixture 2 — East Texas shallow oil
# -----------------------------------------------------------------------------

EAST_TEXAS_SHALLOW_OIL = Wellbore(
    api_number="42-401-12345",          # Rusk County
    operator="Pine Belt Energy Inc.",
    lease_name="Whitfield",
    well_number="3",
    county="Rusk",
    total_depth_ft=4500.0,
    buqw=BUQW(depth_ft=800.0, source="GAU letter dated 2024-08-04"),
    casing=(
        CasingString(
            kind=CasingKind.SURFACE,
            od_in=8.625, id_in=8.097,
            set_depth_ft=1100.0, top_of_cement_ft=0.0,
            weight_lb_per_ft=24.0, grade="J-55",
        ),
        CasingString(
            kind=CasingKind.PRODUCTION,
            od_in=4.5, id_in=4.052,
            set_depth_ft=4400.0, top_of_cement_ft=1000.0,
            weight_lb_per_ft=11.6, grade="J-55",
        ),
    ),
    open_hole=(
        OpenHoleSection(top_ft=4400.0, bottom_ft=4500.0, bit_size_in=3.875),
    ),
    perforations=(
        Perforation(
            top_ft=4250.0, bottom_ft=4280.0,
            zone_name="Travis Peak", status="producing",
        ),
    ),
    notes="Typical East Texas shallow oil; clean general-rule case.",
)


# -----------------------------------------------------------------------------
# Fixture 3 — BUQW uncovered (special-case trigger)
# -----------------------------------------------------------------------------

BUQW_UNCOVERED_LEGACY = Wellbore(
    api_number="42-103-77001",          # Crane County
    operator="Sunset Heritage Wells LLC",
    lease_name="Old Yellowhouse",
    well_number="2",
    county="Crane",
    total_depth_ft=6000.0,
    # BUQW is at 1200 ft but surface casing was set to only 800 ft. NOT
    # protected by surface casing → triggers §3.14 special case.
    buqw=BUQW(depth_ft=1200.0, source="GAU letter dated 2024-05-19"),
    casing=(
        CasingString(
            kind=CasingKind.SURFACE,
            od_in=9.625, id_in=8.835,
            set_depth_ft=800.0, top_of_cement_ft=0.0,
            weight_lb_per_ft=36.0, grade="J-55",
        ),
        CasingString(
            kind=CasingKind.PRODUCTION,
            od_in=5.5, id_in=4.892,
            set_depth_ft=5900.0, top_of_cement_ft=2000.0,
            weight_lb_per_ft=17.0, grade="J-55",
        ),
    ),
    open_hole=(
        OpenHoleSection(top_ft=5900.0, bottom_ft=6000.0, bit_size_in=4.75),
    ),
    perforations=(
        Perforation(
            top_ft=5800.0, bottom_ft=5840.0,
            zone_name="Austin Chalk", status="producing",
        ),
    ),
    notes=(
        "Legacy permitted well: surface casing only to 800 ft, BUQW at 1200 ft. "
        "Special-case continuous-column rule must trigger."
    ),
)


# -----------------------------------------------------------------------------
# Fixture 4 — No surface casing at all (legacy)
# -----------------------------------------------------------------------------

NO_SURFACE_CASING_LEGACY = Wellbore(
    api_number="42-461-00042",          # Throckmorton County (legacy area)
    operator="Estate of J.M. Hardin (Operator of Record)",
    lease_name="Hardin Heirs",
    well_number="A-1",
    county="Throckmorton",
    total_depth_ft=3500.0,
    buqw=BUQW(depth_ft=600.0, source="GAU letter dated 2024-09-22"),
    casing=(
        # No surface casing string! Only production casing, with cement
        # confined to the lower interval — leaves shallow zone unprotected.
        CasingString(
            kind=CasingKind.PRODUCTION,
            od_in=7.0, id_in=6.366,
            set_depth_ft=3400.0, top_of_cement_ft=1500.0,
            weight_lb_per_ft=23.0, grade="J-55",
        ),
    ),
    open_hole=(
        OpenHoleSection(top_ft=3400.0, bottom_ft=3500.0, bit_size_in=6.125),
    ),
    perforations=(
        Perforation(
            top_ft=3300.0, bottom_ft=3320.0,
            zone_name="Strawn", status="abandoned",
        ),
    ),
    notes=(
        "1950s-vintage well with no surface casing string and production "
        "cement starting at 1500 ft. BUQW at 600 ft is unprotected. "
        "Special case must trigger."
    ),
)


# -----------------------------------------------------------------------------
# Fixture 5 — Multi-zone producer
# -----------------------------------------------------------------------------

MULTI_ZONE_PRODUCER = Wellbore(
    api_number="42-329-55555",          # Midland County
    operator="Stacked Pay Operating LP",
    lease_name="Spraberry Ranch",
    well_number="7",
    county="Midland",
    total_depth_ft=8000.0,
    buqw=BUQW(depth_ft=1200.0, source="GAU letter dated 2024-02-28"),
    casing=(
        CasingString(
            kind=CasingKind.SURFACE,
            od_in=9.625, id_in=8.835,
            set_depth_ft=1500.0, top_of_cement_ft=0.0,
            weight_lb_per_ft=36.0, grade="J-55",
        ),
        CasingString(
            kind=CasingKind.PRODUCTION,
            od_in=5.5, id_in=4.892,
            set_depth_ft=7900.0, top_of_cement_ft=3000.0,
            weight_lb_per_ft=17.0, grade="N-80",
        ),
    ),
    open_hole=(
        OpenHoleSection(top_ft=7900.0, bottom_ft=8000.0, bit_size_in=4.75),
    ),
    perforations=(
        Perforation(top_ft=6900.0, bottom_ft=6950.0,
                    zone_name="Dean", status="abandoned"),
        Perforation(top_ft=7350.0, bottom_ft=7400.0,
                    zone_name="Upper Spraberry", status="producing"),
        Perforation(top_ft=7700.0, bottom_ft=7740.0,
                    zone_name="Lower Spraberry", status="producing"),
    ),
    notes="Modern stacked-pay producer; three zones, one already abandoned.",
)


# -----------------------------------------------------------------------------
# Registry — for iteration in tests and the validation runner.
# -----------------------------------------------------------------------------

ALL_FIXTURES: dict[str, Wellbore] = {
    "permian_deep_gas": PERMIAN_DEEP_GAS,
    "east_texas_shallow_oil": EAST_TEXAS_SHALLOW_OIL,
    "buqw_uncovered_legacy": BUQW_UNCOVERED_LEGACY,
    "no_surface_casing_legacy": NO_SURFACE_CASING_LEGACY,
    "multi_zone_producer": MULTI_ZONE_PRODUCER,
}
