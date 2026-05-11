"""Deterministic cement-volume math for plug calculations.

Two geometric primitives are sufficient for every plug placement on a W-3:

  1. **Cylinder** — plug placed inside a single cylindrical bore (open hole
     or inside one casing string).
  2. **Annulus** — plug placed in the annular space between two casings.

Outputs are reported in three units that an operator/inspector will all want:

  * cubic feet   (engineering)
  * barrels      (oilfield slurry handling)
  * sacks        (procurement / cementer)

All inputs are oil-field standard: diameters in **inches**, lengths in **feet**.

Conversions used (sourced from API RP 10B and SPE/IADC standard handbooks):
  * 1 barrel (US oilfield) = 5.6145833 ft³  (= 42 US gal)
  * Class H neat cement default slurry yield = 1.06 ft³/sack at 15.6 ppg
    (operator may override; some Texas jobs run 1.18 ft³/sack with extender)

Excess factor:
  * Inside cased hole: 0% (geometry is known).
  * In open hole: typically 25–50% to account for caliper washout. Default
    25%; the `excess_factor` argument lets the operator dial it per job.

The functions in this module are **pure**. No I/O, no globals, no LLM calls.
They are the trusted core that the LLM scaffold delegates math to.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


# ---- physical constants -----------------------------------------------------

FT3_PER_BBL = 5.6145833
DEFAULT_SACK_YIELD_FT3 = 1.06          # Class H neat at 15.6 ppg
DEFAULT_OPEN_HOLE_EXCESS = 0.25        # +25% for washouts
INCHES_PER_FOOT = 12.0


# ---- result type ------------------------------------------------------------

@dataclass(frozen=True)
class CementVolume:
    """Computed cement volume in three units, with provenance."""
    ft3: float
    bbl: float
    sacks: float
    plug_length_ft: float
    placement: Literal["cylinder", "annulus"]
    excess_factor: float
    sack_yield_ft3: float
    inputs: dict[str, float]      # echo of inputs for audit/log

    def render(self) -> str:
        return (
            f"{self.ft3:7.2f} ft³  |  {self.bbl:6.2f} bbl  |  "
            f"{self.sacks:6.1f} sx   ({self.placement}, "
            f"L={self.plug_length_ft:.0f} ft, excess={self.excess_factor:.0%})"
        )


# ---- core math --------------------------------------------------------------

def _cylinder_ft3_per_ft(diameter_in: float) -> float:
    """Internal volume of a cylinder per foot of length, ft³/ft.

    V/L = π * (d/2)² where d is in feet.  With d in inches:
        V/L (ft³/ft) = π * (d_in / 24)² = π * d_in² / 576
    """
    if diameter_in <= 0:
        raise ValueError("diameter_in must be positive")
    return math.pi * diameter_in * diameter_in / 576.0


def _annulus_ft3_per_ft(outer_id_in: float, inner_od_in: float) -> float:
    """Annular volume per foot, ft³/ft. outer_id is the bore the cement sits
    in (e.g. open-hole diameter or outer casing ID); inner_od is the OD of the
    pipe occupying the middle of that bore.
    """
    if outer_id_in <= inner_od_in:
        raise ValueError(
            f"outer_id_in ({outer_id_in}) must exceed inner_od_in ({inner_od_in})"
        )
    if inner_od_in <= 0:
        raise ValueError("inner_od_in must be positive")
    return math.pi * (outer_id_in**2 - inner_od_in**2) / 576.0


def cylinder_plug_volume(
    *,
    diameter_in: float,
    length_ft: float,
    excess_factor: float = 0.0,
    sack_yield_ft3: float = DEFAULT_SACK_YIELD_FT3,
) -> CementVolume:
    """Cement volume for a plug inside a single cylindrical bore.

    Use for plugs set inside a casing string (excess = 0) or in open hole
    (excess typically 0.25–0.50).
    """
    if length_ft <= 0:
        raise ValueError("length_ft must be positive")
    if excess_factor < 0:
        raise ValueError("excess_factor must be >= 0")

    base_ft3 = _cylinder_ft3_per_ft(diameter_in) * length_ft
    ft3 = base_ft3 * (1.0 + excess_factor)
    return CementVolume(
        ft3=ft3,
        bbl=ft3 / FT3_PER_BBL,
        sacks=ft3 / sack_yield_ft3,
        plug_length_ft=length_ft,
        placement="cylinder",
        excess_factor=excess_factor,
        sack_yield_ft3=sack_yield_ft3,
        inputs={"diameter_in": diameter_in, "length_ft": length_ft},
    )


def annular_plug_volume(
    *,
    outer_id_in: float,
    inner_od_in: float,
    length_ft: float,
    excess_factor: float = 0.0,
    sack_yield_ft3: float = DEFAULT_SACK_YIELD_FT3,
) -> CementVolume:
    """Cement volume for a plug in the annulus between two strings (or between
    open hole and a casing string).

    `outer_id_in` is the *bore* the cement sits inside — usually the previous
    casing's ID, or the open-hole bit size if cementing into open hole.
    `inner_od_in` is the OD of the pipe in the middle of that bore.
    """
    if length_ft <= 0:
        raise ValueError("length_ft must be positive")
    if excess_factor < 0:
        raise ValueError("excess_factor must be >= 0")

    base_ft3 = _annulus_ft3_per_ft(outer_id_in, inner_od_in) * length_ft
    ft3 = base_ft3 * (1.0 + excess_factor)
    return CementVolume(
        ft3=ft3,
        bbl=ft3 / FT3_PER_BBL,
        sacks=ft3 / sack_yield_ft3,
        plug_length_ft=length_ft,
        placement="annulus",
        excess_factor=excess_factor,
        sack_yield_ft3=sack_yield_ft3,
        inputs={
            "outer_id_in": outer_id_in,
            "inner_od_in": inner_od_in,
            "length_ft": length_ft,
        },
    )
