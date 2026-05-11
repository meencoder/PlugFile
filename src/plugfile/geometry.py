"""Wellbore geometry data models.

All depths are *measured depth* in **feet from KB/RT** unless explicitly
labeled TVD. All diameters are in **inches**. Oil-field conventions throughout.

Stdlib only — no Pydantic, no third-party deps. Keeps the deterministic core
auditable and import-light for the LLM tool layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class CasingKind(str, Enum):
    """Standard string types in a Texas oil/gas well."""
    CONDUCTOR = "conductor"
    SURFACE = "surface"
    INTERMEDIATE = "intermediate"
    PRODUCTION = "production"
    LINER = "liner"


@dataclass(frozen=True)
class CasingString:
    """A single string of casing, cemented to some top."""
    kind: CasingKind
    od_in: float                      # outside diameter, inches
    id_in: float                      # inside diameter, inches
    set_depth_ft: float               # shoe depth, MD ft
    top_of_cement_ft: float           # MD ft (0 = surface)
    weight_lb_per_ft: float | None = None   # informational
    grade: str | None = None                # informational, e.g. "J-55"

    def __post_init__(self) -> None:
        if self.id_in >= self.od_in:
            raise ValueError(f"id_in ({self.id_in}) must be < od_in ({self.od_in})")
        if self.top_of_cement_ft > self.set_depth_ft:
            raise ValueError("top_of_cement_ft cannot be deeper than set_depth_ft")


@dataclass(frozen=True)
class OpenHoleSection:
    """An open-hole interval below the deepest casing shoe (or between strings)."""
    top_ft: float
    bottom_ft: float
    bit_size_in: float                # nominal bit/hole diameter

    def __post_init__(self) -> None:
        if self.bottom_ft <= self.top_ft:
            raise ValueError("bottom_ft must be > top_ft")


@dataclass(frozen=True)
class Perforation:
    """A perforated interval (producing or injection zone)."""
    top_ft: float
    bottom_ft: float
    zone_name: str
    status: Literal["producing", "injection", "abandoned", "squeezed"] = "producing"

    def __post_init__(self) -> None:
        if self.bottom_ft <= self.top_ft:
            raise ValueError("bottom_ft must be > top_ft")


@dataclass(frozen=True)
class BUQW:
    """Base of Usable-Quality Water.

    In Texas this is determined by the Groundwater Advisory Unit (GAU) on
    RRC Form GAU-1 / GAU-2. The depth here is the GAU-letter value. TAC §3.14
    requires that BUQW be protected by either through-pipe cement or a
    dedicated plug across it.
    """
    depth_ft: float
    source: str = "GAU letter"        # citation/source string


@dataclass(frozen=True)
class Wellbore:
    """The complete geometric description used by the rule engine."""
    api_number: str                   # 14-digit Texas API, may include dashes
    operator: str
    lease_name: str
    well_number: str
    county: str
    total_depth_ft: float
    buqw: BUQW
    casing: tuple[CasingString, ...] = field(default_factory=tuple)
    perforations: tuple[Perforation, ...] = field(default_factory=tuple)
    open_hole: tuple[OpenHoleSection, ...] = field(default_factory=tuple)
    notes: str = ""

    # ---- helpers used by the rule engine -------------------------------------

    def deepest_casing(self) -> CasingString | None:
        if not self.casing:
            return None
        return max(self.casing, key=lambda c: c.set_depth_ft)

    def casing_covering(self, depth_ft: float) -> CasingString | None:
        """Return the *innermost* (smallest ID) casing string whose pipe
        physically reaches `depth_ft`. Returns None if depth is below every
        casing shoe (i.e. in open hole or rat hole).

        This is a *geometry* lookup — what bore does the cement plug sit
        inside? It does NOT consider top-of-cement (that's a separate
        question about hydraulic isolation, handled by
        `buqw_protected_by_surface_casing`).
        """
        candidates = [c for c in self.casing if c.set_depth_ft >= depth_ft]
        if not candidates:
            return None
        return min(candidates, key=lambda c: c.id_in)

    def surface_casing(self) -> CasingString | None:
        for c in self.casing:
            if c.kind == CasingKind.SURFACE:
                return c
        return None

    def buqw_protected_by_surface_casing(self) -> bool:
        """True iff a surface-casing string is set deeper than BUQW *and* its
        top-of-cement reaches surface (or close enough — within 100 ft of GL).
        This is the trigger for the §3.14 *general* BUQW rule vs the
        *special-case* rule.
        """
        sc = self.surface_casing()
        if sc is None:
            return False
        return sc.set_depth_ft >= self.buqw.depth_ft and sc.top_of_cement_ft <= 100.0
