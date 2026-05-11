"""Unit tests for the deterministic cement-volume math.

Each test uses hand-computed expected values so a regulator or operator can
audit the math line by line without trusting the implementation.
"""

from __future__ import annotations

import math

import pytest

from plugfile.cement_volume import (
    DEFAULT_SACK_YIELD_FT3,
    FT3_PER_BBL,
    annular_plug_volume,
    cylinder_plug_volume,
)


# Cylinder volume per foot, ft^3/ft = pi * d^2(in) / 576
# Annular volume per foot, ft^3/ft = pi * (do^2 - di^2) / 576


def test_cylinder_basic_4892_id_100ft_no_excess() -> None:
    # 4.892" production-casing ID, 100-ft plug, 0% excess.
    # Hand calc: pi * 4.892^2 * 100 / 576 = 13.0527 ft^3
    v = cylinder_plug_volume(diameter_in=4.892, length_ft=100.0)
    expected = math.pi * 4.892**2 * 100.0 / 576.0
    assert v.ft3 == pytest.approx(expected, rel=1e-9)
    assert v.ft3 == pytest.approx(13.0527, rel=1e-4)
    assert v.bbl == pytest.approx(v.ft3 / FT3_PER_BBL, rel=1e-9)
    assert v.sacks == pytest.approx(v.ft3 / DEFAULT_SACK_YIELD_FT3, rel=1e-9)
    assert v.excess_factor == 0.0
    assert v.placement == "cylinder"


def test_cylinder_open_hole_with_25pct_excess() -> None:
    # 4.75" open-hole bit, 50-ft plug, +25% excess (open-hole default).
    # Hand calc:
    #   base = pi * 4.75^2 * 50 / 576 = 6.15296 ft^3
    #   with +25%: 6.15296 * 1.25 = 7.69121 ft^3
    v = cylinder_plug_volume(diameter_in=4.75, length_ft=50.0, excess_factor=0.25)
    expected = math.pi * 4.75**2 * 50.0 / 576.0 * 1.25
    assert v.ft3 == pytest.approx(expected, rel=1e-9)
    assert v.ft3 == pytest.approx(7.69121, rel=1e-4)
    assert v.excess_factor == 0.25


def test_annulus_8835_over_5500_100ft_no_excess() -> None:
    # 8.835" intermediate ID outer, 5.5" production OD inner, 100 ft.
    # Hand calc:
    #   8.835^2 - 5.5^2 = 78.057225 - 30.25 = 47.807225
    #   * 100 / 576 = 8.30021
    #   * pi = 26.0748 ft^3
    v = annular_plug_volume(outer_id_in=8.835, inner_od_in=5.5, length_ft=100.0)
    expected = math.pi * (8.835**2 - 5.5**2) * 100.0 / 576.0
    assert v.ft3 == pytest.approx(expected, rel=1e-9)
    assert v.ft3 == pytest.approx(26.0748, rel=1e-4)
    assert v.placement == "annulus"


def test_annulus_with_excess() -> None:
    v_no = annular_plug_volume(outer_id_in=8.835, inner_od_in=5.5, length_ft=100.0)
    v_ex = annular_plug_volume(
        outer_id_in=8.835, inner_od_in=5.5, length_ft=100.0, excess_factor=0.5
    )
    assert v_ex.ft3 == pytest.approx(v_no.ft3 * 1.5, rel=1e-9)


def test_unit_conversion_consistency() -> None:
    v = cylinder_plug_volume(diameter_in=8.097, length_ft=100.0)
    assert v.bbl == pytest.approx(v.ft3 / FT3_PER_BBL, rel=1e-9)
    assert v.sacks == pytest.approx(v.ft3 / DEFAULT_SACK_YIELD_FT3, rel=1e-9)


def test_custom_sack_yield() -> None:
    yield_ft3 = 1.18
    v = cylinder_plug_volume(
        diameter_in=4.892, length_ft=100.0, sack_yield_ft3=yield_ft3
    )
    assert v.sacks == pytest.approx(v.ft3 / yield_ft3, rel=1e-9)


# Input validation


def test_cylinder_rejects_nonpositive_diameter() -> None:
    with pytest.raises(ValueError):
        cylinder_plug_volume(diameter_in=0, length_ft=100.0)
    with pytest.raises(ValueError):
        cylinder_plug_volume(diameter_in=-1, length_ft=100.0)


def test_cylinder_rejects_nonpositive_length() -> None:
    with pytest.raises(ValueError):
        cylinder_plug_volume(diameter_in=5.0, length_ft=0)


def test_cylinder_rejects_negative_excess() -> None:
    with pytest.raises(ValueError):
        cylinder_plug_volume(diameter_in=5.0, length_ft=100.0, excess_factor=-0.1)


def test_annulus_rejects_inverted_geometry() -> None:
    with pytest.raises(ValueError):
        annular_plug_volume(outer_id_in=5.5, inner_od_in=8.835, length_ft=100.0)
    with pytest.raises(ValueError):
        annular_plug_volume(outer_id_in=5.5, inner_od_in=5.5, length_ft=100.0)


# Algebraic invariants


def test_doubling_length_doubles_volume() -> None:
    a = cylinder_plug_volume(diameter_in=5.0, length_ft=100.0)
    b = cylinder_plug_volume(diameter_in=5.0, length_ft=200.0)
    assert b.ft3 == pytest.approx(2 * a.ft3, rel=1e-9)


def test_excess_is_linear() -> None:
    base = cylinder_plug_volume(diameter_in=5.0, length_ft=100.0)
    ex = cylinder_plug_volume(diameter_in=5.0, length_ft=100.0, excess_factor=0.3)
    assert ex.ft3 == pytest.approx(base.ft3 * 1.3, rel=1e-9)


def test_quadratic_in_diameter() -> None:
    a = cylinder_plug_volume(diameter_in=5.0, length_ft=100.0)
    b = cylinder_plug_volume(diameter_in=10.0, length_ft=100.0)
    assert b.ft3 == pytest.approx(4 * a.ft3, rel=1e-9)


def test_pi_appears_in_formula() -> None:
    # Sanity: a 12" / 1ft cylinder = pi/4 ft^3.
    v = cylinder_plug_volume(diameter_in=12.0, length_ft=1.0)
    assert v.ft3 == pytest.approx(math.pi / 4, rel=1e-9)
