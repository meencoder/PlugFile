"""Plug-Placement Generator — standalone access to the §3.14 engine.

Wraps compute_plug_program() with a richer output model suitable for the
/api/plug-program endpoint and the PWA wizard's "plug preview" step.

The engine logic all lives in tac_3_14.py; this module is a thin adapter:

    api_number + fetcher
        → prefill_w3a()          (well / GAU / completion lookups)
        → _wellbore_from_form()  (Wellbore data model)
        → compute_plug_program() (§3.14 rule engine)
        → PlugPlan               (enriched output — rationale, aggregates)

No new regulatory logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .lookups import Fetcher, MockFetcher
from .prefill import FieldConflict, _plug_to_dict, _wellbore_from_form
from .prefill_w3a import prefill_w3a
from .tac_3_14 import PlugRequirement, compute_plug_program


# ── output model ─────────────────────────────────────────────────────────────

@dataclass
class PlugItem:
    """One plug in the program — enriched shape."""
    rank: int                    # 1-based, sorted shallowest-first (top_ft ASC)
    name: str                    # internal label, e.g. "surface_casing_shoe"
    top_ft: float                # MD ft from surface (0 = ground level)
    bottom_ft: float
    length_ft: float             # bottom_ft − top_ft
    bore: str                    # "inside_casing" | "open_hole" | "annulus"
    bore_diameter_in: float
    kind: str                    # W-3A column value: CIBP+cement, portland-neat …
    volume_sacks: float | None
    volume_bbl: float | None
    volume_ft3: float | None
    cite: str                    # TAC paragraph reference
    rule_path: str               # "general" | "special_buqw_uncovered"
    rationale: str               # human explanation of why this plug is required


@dataclass
class PlugPlan:
    """Complete plug program for one wellbore."""
    api_number: str
    operator_name: str | None
    lease_name: str | None
    county: str | None
    total_depth_ft: float
    buqw_depth_ft: float
    buqw_protected_by_surface_casing: bool
    plug_count: int
    total_cement_sacks: float | None   # sum across all plugs
    total_cement_bbl: float | None
    rule_paths: list[str]              # distinct rule paths exercised
    plugs: list[PlugItem]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict (used by the API endpoint)."""
        return {
            "api_number": self.api_number,
            "operator_name": self.operator_name,
            "lease_name": self.lease_name,
            "county": self.county,
            "total_depth_ft": self.total_depth_ft,
            "buqw_depth_ft": self.buqw_depth_ft,
            "buqw_protected_by_surface_casing": self.buqw_protected_by_surface_casing,
            "plug_count": self.plug_count,
            "total_cement_sacks": self.total_cement_sacks,
            "total_cement_bbl": self.total_cement_bbl,
            "rule_paths": self.rule_paths,
            "warnings": self.warnings,
            "plugs": [
                {
                    "rank": p.rank,
                    "name": p.name,
                    "top_ft": p.top_ft,
                    "bottom_ft": p.bottom_ft,
                    "length_ft": p.length_ft,
                    "bore": p.bore,
                    "bore_diameter_in": p.bore_diameter_in,
                    "kind": p.kind,
                    "volume_sacks": p.volume_sacks,
                    "volume_bbl": p.volume_bbl,
                    "volume_ft3": p.volume_ft3,
                    "cite": p.cite,
                    "rule_path": p.rule_path,
                    "rationale": p.rationale,
                }
                for p in self.plugs
            ],
        }


# ── helpers ───────────────────────────────────────────────────────────────────

def _infer_kind(plug: PlugRequirement) -> str:
    """Map a PlugRequirement name to the plug-kind string used on the W-3A."""
    n = plug.name.lower()
    if "perforation" in n:
        return "CIBP+cement"
    if "surface_plug" in n:
        return "portland-neat"
    if "buqw_continuous" in n:
        return "portland-neat (continuous)"
    if "buqw" in n:
        return "portland-neat"
    if "shoe" in n:
        return "cement-plug"
    return "cement-plug"


# ── public API ────────────────────────────────────────────────────────────────

def build_plug_plan(
    api_number: str,
    fetcher: Fetcher,
    operator_overrides: dict[str, Any] | None = None,
) -> tuple[PlugPlan, list[FieldConflict]]:
    """Compute the required plug program for a wellbore.

    Uses prefill_w3a() to gather well/GAU/completion data, then runs the
    §3.14 engine. Returns (PlugPlan, conflicts). Conflicts are advisory —
    they indicate mismatches between operator overrides and RRC data.
    """
    form, conflicts = prefill_w3a(
        api_number, fetcher, operator_overrides=operator_overrides
    )

    wellbore = _wellbore_from_form(form)
    plug_reqs = compute_plug_program(wellbore)

    total_sacks = 0.0
    total_bbl = 0.0
    items: list[PlugItem] = []

    for i, p in enumerate(plug_reqs, start=1):
        d = _plug_to_dict(p)
        sacks = d.get("volume_sacks")
        bbl   = d.get("volume_bbl")
        ft3   = d.get("volume_ft3")
        if sacks is not None:
            total_sacks += sacks
        if bbl is not None:
            total_bbl += bbl

        items.append(PlugItem(
            rank=i,
            name=p.name,
            top_ft=p.top_ft,
            bottom_ft=p.bottom_ft,
            length_ft=round(p.bottom_ft - p.top_ft, 2),
            bore=p.bore,
            bore_diameter_in=p.bore_diameter_in,
            kind=_infer_kind(p),
            volume_sacks=round(sacks, 2) if sacks is not None else None,
            volume_bbl=round(bbl, 3)   if bbl   is not None else None,
            volume_ft3=round(ft3, 3)   if ft3   is not None else None,
            cite=p.cite,
            rule_path=p.rule_path,
            rationale=p.rationale,
        ))

    plan = PlugPlan(
        api_number=api_number,
        operator_name=form.operator_name,
        lease_name=form.lease_name,
        county=form.county,
        total_depth_ft=form.total_depth_ft or 0.0,
        buqw_depth_ft=form.buqw_depth_ft or 0.0,
        buqw_protected_by_surface_casing=form.buqw_protected_by_surface_casing or False,
        plug_count=len(items),
        total_cement_sacks=round(total_sacks, 2) if total_sacks else None,
        total_cement_bbl=round(total_bbl, 3)   if total_bbl   else None,
        rule_paths=sorted({p.rule_path for p in plug_reqs}),
        plugs=items,
    )
    return plan, conflicts


def build_plug_plan_with_mock(
    api_number: str,
    operator_overrides: dict[str, Any] | None = None,
) -> tuple[PlugPlan, list[FieldConflict]]:
    """Shortcut for tests / demos using the in-memory MockFetcher."""
    return build_plug_plan(api_number, MockFetcher(), operator_overrides)
