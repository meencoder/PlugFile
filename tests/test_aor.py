"""Tests for the Area-of-Review (AOR) Helper (aor.py).

Covers the manual GIS-Viewer review checklist and the isolation-plug
evaluator that turns operator-entered nearby-well findings into the
required §3.14(d)(1) straddle plugs.
"""

from __future__ import annotations

import json

import pytest

from plugfile.aor import (
    AOR_RADIUS_MI,
    AORAssessment,
    AORReviewStep,
    assess_aor_with_mock,
    build_review_guidance,
)

API = "42-371-30001"   # Apex Permian / Pecos — TD 10,500 ft, BUQW 1,500 ft
TD = 10500.0


def _finding(**kw):
    """Build an aor_findings entry with sensible defaults."""
    base = {
        "well_id": "42-371-99887",
        "zone_name": "San Andres",
        "depth_ft": 4200.0,
        "distance_mi": 0.3,
        "direction": "NE",
    }
    base.update(kw)
    return base


def _assess(findings):
    return assess_aor_with_mock(
        API, operator_overrides={"aor_findings": findings}
    )


# ── review guidance ─────────────────────────────────────────────────────────

def test_guidance_has_seven_ordered_steps():
    steps = build_review_guidance(
        api_number=API, operator_name="Apex", county="Pecos", rrc_district="08"
    )
    assert len(steps) == 7
    assert [s.order for s in steps] == list(range(1, 8))


def test_guidance_steps_have_content():
    steps = build_review_guidance(
        api_number=API, operator_name="Apex", county="Pecos", rrc_district="08"
    )
    for s in steps:
        assert isinstance(s, AORReviewStep)
        assert s.title
        assert s.detail


def test_guidance_mentions_gis_viewer_and_radius():
    steps = build_review_guidance(
        api_number=API, operator_name="Apex", county="Pecos", rrc_district="08"
    )
    joined = " ".join(s.detail for s in steps)
    assert "gis.rrc.texas.gov" in joined
    assert "0.5" in joined or "½" in joined


def test_guidance_interpolates_api():
    steps = build_review_guidance(
        api_number=API, operator_name="Apex", county="Pecos", rrc_district="08"
    )
    joined = " ".join(s.detail for s in steps)
    assert API in joined


# ── empty findings ──────────────────────────────────────────────────────────

def test_no_findings_still_returns_guidance():
    a, _ = assess_aor_with_mock(API)
    assert a.finding_count == 0
    assert a.findings == []
    assert len(a.review_guidance) == 7
    # a "no findings yet" warning is surfaced
    assert any("No AOR findings" in w for w in a.warnings)


def test_returns_assessment_and_conflicts():
    a, conflicts = assess_aor_with_mock(API)
    assert isinstance(a, AORAssessment)
    assert isinstance(conflicts, list)
    assert a.api_number == API
    assert a.radius_mi == AOR_RADIUS_MI


# ── isolation logic ─────────────────────────────────────────────────────────

def test_inside_radius_with_depth_requires_isolation():
    a, _ = _assess([_finding(depth_ft=4200.0, distance_mi=0.3)])
    f = a.findings[0]
    assert f.in_aor
    assert f.requires_isolation
    assert f.isolation_top_ft == pytest.approx(4150.0)
    assert f.isolation_bottom_ft == pytest.approx(4250.0)
    assert f.isolation_volume_sacks is not None and f.isolation_volume_sacks > 0
    assert f.cite == "16 TAC §3.14(d)(1)"


def test_outside_radius_not_in_aor():
    a, _ = _assess([_finding(distance_mi=0.9)])
    f = a.findings[0]
    assert not f.in_aor
    assert not f.requires_isolation
    assert f.isolation_top_ft is None
    assert "Outside" in f.note


def test_explicit_requires_isolation_false_overrides_inference():
    a, _ = _assess([_finding(depth_ft=4200.0, requires_isolation=False)])
    f = a.findings[0]
    assert not f.requires_isolation
    assert f.isolation_volume_sacks is None


def test_explicit_requires_isolation_true_honored():
    a, _ = _assess([_finding(depth_ft=3000.0, requires_isolation=True)])
    f = a.findings[0]
    assert f.requires_isolation
    assert f.isolation_volume_sacks is not None


def test_isolation_marked_but_no_depth_warns():
    a, _ = _assess([_finding(depth_ft=None, requires_isolation=True)])
    f = a.findings[0]
    assert not f.requires_isolation
    assert f.isolation_top_ft is None
    assert any("depth" in w.lower() for w in a.warnings)


def test_zone_below_td_not_penetrated():
    a, _ = _assess([_finding(depth_ft=TD + 500, requires_isolation=True)])
    f = a.findings[0]
    assert not f.requires_isolation
    assert "TD" in f.note or "below" in f.note.lower()


def test_missing_distance_assumed_in_aor_with_warning():
    a, _ = _assess([_finding(distance_mi=None, depth_ft=4200.0)])
    f = a.findings[0]
    assert f.in_aor
    assert any("distance" in w.lower() for w in a.warnings)


# ── straddle clamping ───────────────────────────────────────────────────────

def test_shallow_zone_clamps_top_to_zero():
    a, _ = _assess([_finding(depth_ft=30.0, distance_mi=0.1)])
    f = a.findings[0]
    assert f.requires_isolation
    assert f.isolation_top_ft == pytest.approx(0.0)
    assert f.isolation_bottom_ft == pytest.approx(80.0)


def test_deep_zone_clamps_bottom_to_td():
    a, _ = _assess([_finding(depth_ft=TD - 20, distance_mi=0.1)])
    f = a.findings[0]
    assert f.requires_isolation
    assert f.isolation_bottom_ft == pytest.approx(TD)


# ── aggregates ──────────────────────────────────────────────────────────────

def test_counts_and_total_sacks():
    a, _ = _assess([
        _finding(well_id="A", depth_ft=4200.0, distance_mi=0.2),   # isolate
        _finding(well_id="B", depth_ft=3000.0, distance_mi=0.4),   # isolate
        _finding(well_id="C", depth_ft=2000.0, distance_mi=0.8),   # out of AOR
    ])
    assert a.finding_count == 3
    assert a.in_aor_count == 2
    assert a.isolation_required_count == 2
    assert a.total_isolation_sacks is not None and a.total_isolation_sacks > 0
    # total equals the sum of the two isolated findings
    iso_sum = sum(
        f.isolation_volume_sacks or 0 for f in a.findings if f.requires_isolation
    )
    assert a.total_isolation_sacks == pytest.approx(round(iso_sum, 2))


# ── serialization ───────────────────────────────────────────────────────────

def test_to_dict_json_serializable():
    a, _ = _assess([_finding(depth_ft=4200.0)])
    d = a.to_dict()
    json.dumps(d)   # must not raise
    assert d["api_number"] == API
    assert d["radius_mi"] == AOR_RADIUS_MI
    assert len(d["review_guidance"]) == 7
    assert len(d["findings"]) == 1
    assert "gis_viewer_url" in d


# ── all five mock wellbores ─────────────────────────────────────────────────

@pytest.mark.parametrize("api", [
    "42-371-30001",
    "42-401-12345",
    "42-103-77001",
    "42-461-00042",
    "42-329-55555",
])
def test_all_mock_apis_produce_guidance(api):
    a, _ = assess_aor_with_mock(api)
    assert a.api_number == api
    assert len(a.review_guidance) == 7
    assert a.total_depth_ft > 0
