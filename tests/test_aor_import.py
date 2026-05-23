"""Tests for the GIS 'Download Wells' export importer (aor_import.py)."""

from __future__ import annotations

import io

import pytest

from plugfile.aor_import import (
    WellImportResult,
    bearing,
    haversine_mi,
    parse_download_wells,
)

# Subject well: Apex Permian / Pecos (mock 42-371-30001), TD 10,500.
SUBJ_LAT, SUBJ_LON, SUBJ_TD = 31.0184, -102.01, 10500.0

# A nearby well ~0.3 mi NE; one plugged well; one >0.5 mi away.
CSV_EXPORT = """API Number,Surface Latitude,Surface Longitude,Well Type,Total Depth,Plugging Date,Lease Name,Well No,Field Name,Operator Name
42-371-99887,31.0210,-102.0075,Oil,4200,,Nearby A,1,San Andres,Acme Oil
42-371-55512,31.0190,-102.0102,Oil,3000,2019-06-01,Old Plugged,2,Grayburg,Beta LLC
42-371-44400,31.0500,-102.0600,Injection,2000,,Far Well,3,Yates,Gamma Inc
"""


def _result(**kw):
    return parse_download_wells(
        CSV_EXPORT, filename="wells.csv",
        subject_lat=SUBJ_LAT, subject_lon=SUBJ_LON, subject_td_ft=SUBJ_TD,
        subject_api="42-371-30001", **kw,
    )


# ── geo helpers ───────────────────────────────────────────────────────────────

def test_haversine_known_distance():
    # ~0.69 mi per 0.01 deg latitude
    d = haversine_mi(31.0, -102.0, 31.01, -102.0)
    assert d == pytest.approx(0.69, abs=0.05)


def test_haversine_zero():
    assert haversine_mi(31.0, -102.0, 31.0, -102.0) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("dlat,dlon,expected", [
    (0.01, 0.0, "N"),
    (-0.01, 0.0, "S"),
    (0.0, 0.01, "E"),
    (0.0, -0.01, "W"),
])
def test_bearing_cardinals(dlat, dlon, expected):
    assert bearing(31.0, -102.0, 31.0 + dlat, -102.0 + dlon) == expected


# ── parsing + classification ──────────────────────────────────────────────────

def test_returns_result():
    r = _result()
    assert isinstance(r, WellImportResult)


def test_total_rows_counted():
    r = _result()
    assert r.summary.total_rows == 3
    assert r.summary.unique_wells == 3


def test_plugged_well_skipped():
    r = _result()
    assert r.summary.plugged_skipped == 1
    assert not any("55512" in f["well_id"] for f in r.findings)


def test_far_well_dropped():
    r = _result()
    # 42-371-44400 is ~3 mi away -> out of the 0.5-mi radius
    assert r.summary.out_of_radius == 1
    assert not any("44400" in f["well_id"] for f in r.findings)


def test_nearby_well_becomes_finding():
    r = _result()
    assert r.summary.of_concern == 1
    assert len(r.findings) == 1
    f = r.findings[0]
    assert "99887" in f["well_id"]
    assert f["zone_name"] == "San Andres"
    assert f["depth_ft"] == 4200.0
    assert f["distance_mi"] is not None and f["distance_mi"] <= 0.5
    assert f["direction"] in ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def test_finding_label_includes_lease():
    r = _result()
    assert "Nearby A" in r.findings[0]["well_id"]


def test_requires_isolation_left_unset():
    # The importer defers isolation logic to assess_aor().
    r = _result()
    assert "requires_isolation" not in r.findings[0]


# ── radius override ─────────────────────────────────────────────────────────────

def test_wider_radius_keeps_more():
    r = parse_download_wells(
        CSV_EXPORT, filename="wells.csv",
        subject_lat=SUBJ_LAT, subject_lon=SUBJ_LON, radius_mi=5.0,
        subject_api="42-371-30001",
    )
    # the far injection well now falls inside 5 mi
    assert any("44400" in f["well_id"] for f in r.findings)


# ── header tolerance ─────────────────────────────────────────────────────────────

def test_alternate_headers():
    alt = ("API,Latitude,Longitude,Filing Purpose,Completion Depth,Date Plugged,Lease,Well,Reservoir,Operator\n"
           "42-371-99887,31.0210,-102.0075,Oil,4200,,Nearby A,1,San Andres,Acme\n")
    r = parse_download_wells(alt, filename="x.csv", subject_lat=SUBJ_LAT,
                             subject_lon=SUBJ_LON, subject_api="42-371-30001")
    assert r.summary.of_concern == 1
    assert r.findings[0]["depth_ft"] == 4200.0


def test_missing_api_column_warns():
    bad = "Foo,Bar\n1,2\n"
    r = parse_download_wells(bad, filename="x.csv")
    assert r.findings == []
    assert any("API" in w for w in r.warnings)


def test_no_subject_coords_keeps_all_unplugged():
    r = parse_download_wells(CSV_EXPORT, filename="wells.csv",
                             subject_api="42-371-30001")
    # no distance filter -> both unplugged wells kept (plugged still skipped)
    assert not r.summary.distances_computed
    assert r.summary.of_concern == 2
    assert any("distances could not be computed" in w for w in r.warnings)


# ── dedupe multi-completion rows ──────────────────────────────────────────────

def test_multi_completion_dedupes_to_shallowest():
    multi = ("API Number,Surface Latitude,Surface Longitude,Total Depth,Field Name\n"
             "42-371-99887,31.0210,-102.0075,4200,San Andres\n"
             "42-371-99887,31.0210,-102.0075,3100,Grayburg\n")
    r = parse_download_wells(multi, filename="x.csv", subject_lat=SUBJ_LAT,
                             subject_lon=SUBJ_LON, subject_api="42-371-30001")
    assert r.summary.unique_wells == 1
    assert len(r.findings) == 1
    assert r.findings[0]["depth_ft"] == 3100.0   # shallowest kept


def test_to_dict_json_serializable():
    import json
    r = _result()
    d = r.to_dict()
    json.dumps(d)
    assert d["summary"]["of_concern"] == 1
    assert len(d["findings"]) == 1
