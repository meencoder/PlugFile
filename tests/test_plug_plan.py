"""Tests for the Plug-Placement Generator (plug_plan.py).

Validates that build_plug_plan() returns a coherent, complete plug program
for each seeded mock wellbore, and that the output model is correctly
populated from the §3.14 engine.
"""

from __future__ import annotations

import pytest

from plugfile.plug_plan import PlugItem, PlugPlan, build_plug_plan_with_mock

API = "42-371-30001"   # Apex Permian / Pecos / D08 / Heritage A 1H


# ── basic structure ───────────────────────────────────────────────────────────

def test_returns_plug_plan_and_conflicts():
    plan, conflicts = build_plug_plan_with_mock(API)
    assert isinstance(plan, PlugPlan)
    assert isinstance(conflicts, list)


def test_plan_has_correct_api_number():
    plan, _ = build_plug_plan_with_mock(API)
    assert plan.api_number == API


def test_plan_has_well_identity():
    plan, _ = build_plug_plan_with_mock(API)
    assert plan.operator_name == "Apex Permian Operating LLC"
    assert plan.lease_name == "Heritage A"
    assert plan.county == "Pecos"


def test_plan_has_positive_depth():
    plan, _ = build_plug_plan_with_mock(API)
    assert plan.total_depth_ft > 0
    assert plan.buqw_depth_ft > 0
    assert plan.buqw_depth_ft < plan.total_depth_ft


def test_plan_plug_count_positive():
    plan, _ = build_plug_plan_with_mock(API)
    assert plan.plug_count > 0
    assert len(plan.plugs) == plan.plug_count


# ── per-plug correctness ──────────────────────────────────────────────────────

def test_every_plug_has_required_fields():
    plan, _ = build_plug_plan_with_mock(API)
    for plug in plan.plugs:
        assert isinstance(plug, PlugItem)
        assert plug.rank >= 1
        assert plug.top_ft >= 0
        assert plug.bottom_ft > plug.top_ft
        assert plug.length_ft == pytest.approx(plug.bottom_ft - plug.top_ft, abs=0.01)
        assert plug.cite          # TAC citation present
        assert plug.rule_path     # rule path present
        assert plug.rationale     # human explanation present
        assert plug.bore in ("inside_casing", "open_hole", "annulus")
        assert plug.bore_diameter_in > 0


def test_plugs_sorted_shallowest_first():
    plan, _ = build_plug_plan_with_mock(API)
    tops = [p.top_ft for p in plan.plugs]
    assert tops == sorted(tops)


def test_plugs_have_ranks_1_to_n():
    plan, _ = build_plug_plan_with_mock(API)
    assert [p.rank for p in plan.plugs] == list(range(1, plan.plug_count + 1))


def test_every_plug_has_volume():
    plan, _ = build_plug_plan_with_mock(API)
    for plug in plan.plugs:
        # At least one volume unit must be populated
        assert plug.volume_sacks is not None or plug.volume_bbl is not None


def test_every_plug_has_kind():
    plan, _ = build_plug_plan_with_mock(API)
    valid_kinds = {"CIBP+cement", "portland-neat", "portland-neat (continuous)", "cement-plug"}
    for plug in plan.plugs:
        assert plug.kind in valid_kinds, f"Unexpected kind: {plug.kind!r}"


# ── aggregates ────────────────────────────────────────────────────────────────

def test_total_cement_sacks_positive():
    plan, _ = build_plug_plan_with_mock(API)
    assert plan.total_cement_sacks is not None
    assert plan.total_cement_sacks > 0


def test_rule_paths_nonempty():
    plan, _ = build_plug_plan_with_mock(API)
    assert plan.rule_paths
    for rp in plan.rule_paths:
        assert rp in ("general", "special_buqw_uncovered")


def test_to_dict_is_json_serializable():
    plan, conflicts = build_plug_plan_with_mock(API)
    import json
    d = plan.to_dict()
    # Should not raise
    json.dumps(d)
    assert d["api_number"] == API
    assert d["plug_count"] == plan.plug_count
    assert len(d["plugs"]) == plan.plug_count


# ── all five mock wellbores ───────────────────────────────────────────────────

@pytest.mark.parametrize("api", [
    "42-371-30001",
    "42-401-12345",
    "42-103-77001",
    "42-461-00042",
    "42-329-55555",
])
def test_all_mock_apis_produce_plug_plan(api):
    plan, _ = build_plug_plan_with_mock(api)
    assert plan.api_number == api
    assert plan.plug_count > 0
    assert plan.total_cement_sacks is not None and plan.total_cement_sacks > 0
    for plug in plan.plugs:
        assert plug.rationale  # every plug must explain itself
