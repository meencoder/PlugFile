"""Golden tests for the TAC §3.14 rule engine, applied to the 5 fixtures.

Each fixture has an expected plug-program signature: how many plugs, which
named plugs are present, what rule path was taken, and that volumes match
hand-calculated values for the critical plugs.
"""

from __future__ import annotations

import math

import pytest

from wellplug.tac_3_14 import (
    GENERAL_PLUG_ABOVE_FT,
    GENERAL_PLUG_BELOW_FT,
    SURFACE_PLUG_LENGTH_FT,
    compute_plug_program,
)
from tests.fixtures.sample_wellbores import (
    ALL_FIXTURES,
    BUQW_UNCOVERED_LEGACY,
    EAST_TEXAS_SHALLOW_OIL,
    MULTI_ZONE_PRODUCER,
    NO_SURFACE_CASING_LEGACY,
    PERMIAN_DEEP_GAS,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _names(plugs) -> list[str]:
    return [p.name for p in plugs]


def _rule_paths(plugs) -> set[str]:
    return {p.rule_path for p in plugs}


def _by_name(plugs, name: str):
    matches = [p for p in plugs if p.name == name]
    if not matches:
        raise AssertionError(
            f"plug '{name}' not in program. Got: {_names(plugs)}"
        )
    if len(matches) > 1:
        raise AssertionError(f"multiple plugs named '{name}'")
    return matches[0]


# -----------------------------------------------------------------------------
# Fixture 1: Permian deep gas — general rule, production shoe auto-splits
# -----------------------------------------------------------------------------

def test_permian_deep_gas_uses_general_rule() -> None:
    plugs = compute_plug_program(PERMIAN_DEEP_GAS)
    assert _rule_paths(plugs) == {"general"}


def test_permian_deep_gas_production_shoe_splits_at_open_hole() -> None:
    """Production shoe at 10,300 ft → plug 10,250–10,350 must split into:
        seg1 inside casing (10250–10300, 4.892" ID, 0% excess)
        seg2 in open hole  (10300–10350, 4.75" bit,  +25% excess)
    """
    plugs = compute_plug_program(PERMIAN_DEEP_GAS)
    seg1 = _by_name(plugs, "production_casing_shoe_seg1_inside_casing")
    seg2 = _by_name(plugs, "production_casing_shoe_seg2_open_hole")

    assert seg1.bore == "inside_casing"
    assert seg1.bore_diameter_in == pytest.approx(4.892)
    assert seg1.volume.excess_factor == 0.0
    assert seg1.top_ft == 10250.0
    assert seg1.bottom_ft == 10300.0

    assert seg2.bore == "open_hole"
    assert seg2.bore_diameter_in == pytest.approx(4.75)
    assert seg2.volume.excess_factor == 0.25
    assert seg2.top_ft == 10300.0
    assert seg2.bottom_ft == 10350.0


def test_permian_deep_gas_perforation_plug_volume() -> None:
    """Perforation 10,150–10,200 → plug 10,100–10,250 (150 ft) inside the
    4.892" production casing, 0% excess.

    Hand calc: π × 4.892² × 150 / 576 = 19.5775 ft³
    """
    plugs = compute_plug_program(PERMIAN_DEEP_GAS)
    perf = _by_name(plugs, "perforation_Wolfcamp A")
    assert perf.top_ft == pytest.approx(10150.0 - GENERAL_PLUG_ABOVE_FT)
    assert perf.bottom_ft == pytest.approx(10200.0 + GENERAL_PLUG_BELOW_FT)
    assert perf.volume.ft3 == pytest.approx(
        math.pi * 4.892**2 * 150 / 576, rel=1e-6
    )


def test_permian_deep_gas_buqw_uses_general_path() -> None:
    """Surface casing covers BUQW (1800 > 1500, ToC=0) → general BUQW plug."""
    plugs = compute_plug_program(PERMIAN_DEEP_GAS)
    buqw = _by_name(plugs, "buqw_protective_plug")
    assert buqw.rule_path == "general"
    assert buqw.top_ft == 1450.0
    assert buqw.bottom_ft == 1550.0


def test_permian_deep_gas_has_surface_plug() -> None:
    plugs = compute_plug_program(PERMIAN_DEEP_GAS)
    sp = _by_name(plugs, "surface_plug")
    assert sp.top_ft == 0.0
    assert sp.bottom_ft == SURFACE_PLUG_LENGTH_FT


def test_permian_deep_gas_program_is_top_down_sorted() -> None:
    plugs = compute_plug_program(PERMIAN_DEEP_GAS)
    tops = [p.top_ft for p in plugs]
    assert tops == sorted(tops)


# -----------------------------------------------------------------------------
# Fixture 2: East Texas shallow oil — clean general rule
# -----------------------------------------------------------------------------

def test_east_texas_uses_general_rule() -> None:
    plugs = compute_plug_program(EAST_TEXAS_SHALLOW_OIL)
    assert _rule_paths(plugs) == {"general"}


def test_east_texas_buqw_protected() -> None:
    plugs = compute_plug_program(EAST_TEXAS_SHALLOW_OIL)
    buqw = _by_name(plugs, "buqw_protective_plug")
    assert buqw.top_ft == 750.0   # 800 - 50
    assert buqw.bottom_ft == 850.0


def test_east_texas_surface_shoe_inside_production() -> None:
    """Surface shoe at 1100 ft → plug 1050–1150. At those depths the
    innermost pipe is the production casing (4.052" ID).
    """
    plugs = compute_plug_program(EAST_TEXAS_SHALLOW_OIL)
    shoe = _by_name(plugs, "surface_casing_shoe")
    assert shoe.bore == "inside_casing"
    assert shoe.bore_diameter_in == pytest.approx(4.052)


# -----------------------------------------------------------------------------
# Fixture 3: BUQW uncovered → SPECIAL CASE fires
# -----------------------------------------------------------------------------

def test_buqw_uncovered_triggers_special_case() -> None:
    plugs = compute_plug_program(BUQW_UNCOVERED_LEGACY)
    assert "special_buqw_uncovered" in _rule_paths(plugs)


def test_buqw_uncovered_continuous_column_to_surface() -> None:
    """BUQW at 1200 ft with no surface-casing protection →
    continuous column from 0 to 1250 ft (BUQW + 50 ft margin)."""
    plugs = compute_plug_program(BUQW_UNCOVERED_LEGACY)
    column = _by_name(plugs, "buqw_continuous_to_surface")
    assert column.rule_path == "special_buqw_uncovered"
    assert column.top_ft == 0.0
    assert column.bottom_ft == 1250.0


def test_buqw_uncovered_no_separate_surface_plug() -> None:
    """The continuous column supersedes the surface plug."""
    plugs = compute_plug_program(BUQW_UNCOVERED_LEGACY)
    assert "surface_plug" not in _names(plugs)


def test_buqw_uncovered_no_separate_surface_casing_shoe_plug() -> None:
    """Surface casing shoe at 800 ft is fully within the continuous column
    (0–1250 ft), so it's superseded."""
    plugs = compute_plug_program(BUQW_UNCOVERED_LEGACY)
    names = _names(plugs)
    assert "surface_casing_shoe" not in names
    assert not any(n.startswith("surface_casing_shoe_seg") for n in names)


def test_buqw_uncovered_perforation_plug_unaffected() -> None:
    """Plugs deeper than the column (perfs, production shoe) still appear."""
    plugs = compute_plug_program(BUQW_UNCOVERED_LEGACY)
    assert any(p.name == "perforation_Austin Chalk" for p in plugs)


def test_buqw_uncovered_column_volume_inside_production_casing() -> None:
    """Production casing extends to 5900 ft and is the innermost string at
    every depth from 0–1250, so the continuous column sits inside the 4.892"
    production-casing ID for its full length.

    Hand calc: π × 4.892² × 1250 / 576 = 163.146 ft³
    """
    plugs = compute_plug_program(BUQW_UNCOVERED_LEGACY)
    column = _by_name(plugs, "buqw_continuous_to_surface")
    assert column.bore == "inside_casing"
    assert column.bore_diameter_in == pytest.approx(4.892)
    assert column.volume.ft3 == pytest.approx(
        math.pi * 4.892**2 * 1250 / 576, rel=1e-6
    )


# -----------------------------------------------------------------------------
# Fixture 4: No surface casing at all → SPECIAL CASE fires
# -----------------------------------------------------------------------------

def test_no_surface_casing_triggers_special_case() -> None:
    plugs = compute_plug_program(NO_SURFACE_CASING_LEGACY)
    assert "special_buqw_uncovered" in _rule_paths(plugs)


def test_no_surface_casing_column_endpoints() -> None:
    plugs = compute_plug_program(NO_SURFACE_CASING_LEGACY)
    column = _by_name(plugs, "buqw_continuous_to_surface")
    assert column.top_ft == 0.0
    assert column.bottom_ft == 650.0   # BUQW 600 + 50


def test_no_surface_casing_abandoned_perf_still_plugged() -> None:
    """Status='abandoned' is still a plug-required perforation; only
    'squeezed' status is exempt."""
    plugs = compute_plug_program(NO_SURFACE_CASING_LEGACY)
    assert any(p.name == "perforation_Strawn" for p in plugs)


# -----------------------------------------------------------------------------
# Fixture 5: Multi-zone producer
# -----------------------------------------------------------------------------

def test_multi_zone_uses_general_rule() -> None:
    plugs = compute_plug_program(MULTI_ZONE_PRODUCER)
    assert _rule_paths(plugs) == {"general"}


def test_multi_zone_three_perforation_plugs() -> None:
    """One plug per perforation (none are squeezed)."""
    plugs = compute_plug_program(MULTI_ZONE_PRODUCER)
    perf_plugs = [p for p in plugs if p.name.startswith("perforation_")]
    assert len(perf_plugs) == 3
    assert {p.name for p in perf_plugs} == {
        "perforation_Dean",
        "perforation_Upper Spraberry",
        "perforation_Lower Spraberry",
    }


def test_multi_zone_perforations_dont_overlap_each_other() -> None:
    """Sanity: with 50ft margins, the three zones (6900-6950, 7350-7400,
    7700-7740) generate plugs (6850-7000, 7300-7450, 7650-7790) that
    don't overlap.
    """
    plugs = compute_plug_program(MULTI_ZONE_PRODUCER)
    perfs = sorted(
        (p for p in plugs if p.name.startswith("perforation_")),
        key=lambda p: p.top_ft,
    )
    for a, b in zip(perfs, perfs[1:]):
        assert a.bottom_ft <= b.top_ft, (
            f"{a.name} ({a.top_ft}-{a.bottom_ft}) overlaps "
            f"{b.name} ({b.top_ft}-{b.bottom_ft})"
        )


# -----------------------------------------------------------------------------
# All-fixture invariants
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("name,well", list(ALL_FIXTURES.items()))
def test_every_fixture_produces_at_least_one_plug(name, well) -> None:
    plugs = compute_plug_program(well)
    assert plugs, f"no plugs generated for fixture {name}"


@pytest.mark.parametrize("name,well", list(ALL_FIXTURES.items()))
def test_every_plug_has_positive_volume(name, well) -> None:
    plugs = compute_plug_program(well)
    for p in plugs:
        assert p.volume.ft3 > 0, f"{name}: {p.name} has non-positive volume"
        assert p.bottom_ft > p.top_ft


@pytest.mark.parametrize("name,well", list(ALL_FIXTURES.items()))
def test_every_plug_has_a_cite(name, well) -> None:
    plugs = compute_plug_program(well)
    for p in plugs:
        assert p.cite, f"{name}: {p.name} missing citation"
        assert "TAC §3.14" in p.cite


@pytest.mark.parametrize("name,well", list(ALL_FIXTURES.items()))
def test_every_program_is_top_down_sorted(name, well) -> None:
    plugs = compute_plug_program(well)
    tops = [p.top_ft for p in plugs]
    assert tops == sorted(tops), f"{name}: program not sorted top-down"
