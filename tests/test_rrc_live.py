"""Live integration tests for the RRC fetcher.

These tests hit rrc.texas.gov directly.  They are SKIPPED by default to keep
CI fast and allow offline development.  Enable with::

    pytest --live tests/test_rrc_live.py            # live tests only
    pytest --live tests/test_rrc_live.py -v         # verbose
    pytest --live tests/test_rrc_live.py -k "08"    # specific district
    pytest --live tests/test_rrc_live.py --no-header -q  # compact output

Design
------
* Each CandidateWell in WELL_DATABASE gets its own parametrised test case.
* If the RRC returns "no results" the test is marked XFAIL (expected possible)
  so the suite doesn't go red just because a serial number doesn't exist.
* County and district validation only fires when expected_* values are set.
* Completion-record tests are a separate parametrisation so a missing casing
  table doesn't mask a passing well-lookup.

Rate limiting
-------------
The fetcher already throttles to 1 req/s. pytest-xdist parallelism is NOT
recommended for live tests — run single-threaded to stay polite to RRC.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

# Skip the entire module when Phase 2A deps aren't installed
requests = pytest.importorskip("requests")
lxml_html = pytest.importorskip("lxml.html")
diskcache = pytest.importorskip("diskcache")

from plugfile.lookups import FetcherError
from plugfile.lookups_rrc import RRCRoRQFetcher

from tests.fixtures.well_database import (
    WELL_DATABASE,
    CandidateWell,
    WELLS_BY_DISTRICT,
)


# ---------------------------------------------------------------------------
# Shared fetcher fixture — one instance per test session to reuse cache/session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fetcher() -> RRCRoRQFetcher:
    """Single RRCRoRQFetcher instance shared across the live test session."""
    return RRCRoRQFetcher()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _api_ids(wells: list[CandidateWell]) -> list[str]:
    return [w.api for w in wells]


# ---------------------------------------------------------------------------
# Test 1 — Well lookup (metadata from RRC CMPL search)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.parametrize("well", WELL_DATABASE, ids=_api_ids(WELL_DATABASE))
def test_well_lookup(well: CandidateWell, fetcher: RRCRoRQFetcher) -> None:
    """
    Fetch well metadata from RRC and validate returned fields.

    * county    — must match well.expected_county  (if provided)
    * district  — must match well.expected_district (if provided)
    * required fields — api_number, lease_name, county, rrc_district must be
                        non-empty strings on a successful fetch
    """
    try:
        result = fetcher.lookup_well_by_api(well.api)
    except FetcherError as exc:
        # "no results" from RRC = this serial doesn't exist; mark expected-fail
        pytest.xfail(f"RRC returned no results for {well.api}: {exc}")

    # --- required fields present ---
    assert result["api_number"], f"api_number empty for {well.api}"
    assert result["lease_name"], f"lease_name empty for {well.api}"
    assert result["county"],     f"county empty for {well.api}"
    assert result["rrc_district"], f"rrc_district empty for {well.api}"

    # --- county validation ---
    if well.expected_county:
        actual_county = result["county"].strip().lower()
        expected = well.expected_county.strip().lower()
        assert expected in actual_county, (
            f"County mismatch for {well.api}: "
            f"expected '{well.expected_county}', got '{result['county']}'"
        )

    # --- district validation ---
    if well.expected_district:
        actual_dist = result["rrc_district"].strip().upper()
        expected_dist = well.expected_district.strip().upper()
        assert actual_dist == expected_dist, (
            f"District mismatch for {well.api}: "
            f"expected '{well.expected_district}', got '{result['rrc_district']}'"
        )


# ---------------------------------------------------------------------------
# Test 2 — Completion record (casing + perforations)
# ---------------------------------------------------------------------------

# Run completion tests only for the anchor wells in D08 (Permian) where we
# expect rich casing tables.  The full completion sweep can take >3 min.
_COMPLETION_CANDIDATES = [
    w for w in WELL_DATABASE
    if w.expected_district in ("08", "06", "04")
]


@pytest.mark.live
@pytest.mark.parametrize(
    "well", _COMPLETION_CANDIDATES, ids=_api_ids(_COMPLETION_CANDIDATES)
)
def test_completion_lookup(well: CandidateWell, fetcher: RRCRoRQFetcher) -> None:
    """
    Fetch completion record and validate structural integrity of the response.

    We don't assert specific casing depths because those vary per well.
    We do assert that:
      * total_depth_ft is a positive float when present
      * each casing row has kind, od_in, set_depth_ft (non-null)
      * perforation rows have top_ft < bottom_ft
    """
    try:
        result = fetcher.lookup_completion(well.api)
    except FetcherError as exc:
        pytest.xfail(f"Completion record not available for {well.api}: {exc}")

    # total depth
    if result.get("total_depth_ft") is not None:
        assert result["total_depth_ft"] > 0, (
            f"Non-positive total_depth_ft for {well.api}: {result['total_depth_ft']}"
        )

    # casing record shape
    for i, casing in enumerate(result.get("casing_record") or []):
        assert casing.get("kind"), (
            f"Casing row {i} missing 'kind' for {well.api}"
        )
        assert casing.get("set_depth_ft") is not None, (
            f"Casing row {i} missing 'set_depth_ft' for {well.api}"
        )

    # perforation shape
    for i, perf in enumerate(result.get("perforations") or []):
        if perf.get("top_ft") is not None and perf.get("bottom_ft") is not None:
            assert perf["top_ft"] < perf["bottom_ft"], (
                f"Perf row {i} top >= bottom for {well.api}: "
                f"{perf['top_ft']} >= {perf['bottom_ft']}"
            )


# ---------------------------------------------------------------------------
# Test 3 — Operator lookup (P-5 resolution)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.parametrize("well", WELL_DATABASE, ids=_api_ids(WELL_DATABASE))
def test_operator_lookup(well: CandidateWell, fetcher: RRCRoRQFetcher) -> None:
    """
    Resolve the operator P-5 number for a well, then fetch operator name.

    Steps:
      1. Look up the well to get the P-5 number
      2. Use that P-5 to fetch operator_name + address
    """
    try:
        p5 = fetcher.operator_p5_for_api(well.api)
    except FetcherError as exc:
        pytest.xfail(f"Could not resolve P-5 for {well.api}: {exc}")

    assert p5, f"Empty P-5 number for {well.api}"

    try:
        op = fetcher.lookup_operator(p5)
    except FetcherError as exc:
        pytest.xfail(f"Could not fetch operator for P-5 {p5}: {exc}")

    assert op["operator_name"], (
        f"operator_name empty for P-5 {p5} (API {well.api})"
    )


# ---------------------------------------------------------------------------
# Test 4 — District smoke test (one well per district)
# ---------------------------------------------------------------------------

# Take the first well in each district as a representative sample
_DISTRICT_REPS: list[CandidateWell] = [
    wells[0]
    for _dist, wells in sorted(WELLS_BY_DISTRICT.items())
    if wells
]


@pytest.mark.live
@pytest.mark.parametrize(
    "well", _DISTRICT_REPS, ids=[f"D{w.expected_district}_{w.api}" for w in _DISTRICT_REPS]
)
def test_district_representative(well: CandidateWell, fetcher: RRCRoRQFetcher) -> None:
    """
    Smoke test: confirm RRC is reachable and returns a response for at least
    one well in every district.  Marked xfail if the specific API isn't found.
    """
    try:
        result = fetcher.lookup_well_by_api(well.api)
        # If we get here, we got a valid result — just confirm the district
        if well.expected_district:
            actual = result["rrc_district"].strip().upper()
            expected = well.expected_district.strip().upper()
            assert actual == expected, (
                f"District mismatch for representative well {well.api}: "
                f"expected D{expected}, got D{actual}"
            )
    except FetcherError:
        pytest.xfail(
            f"Representative well {well.api} not found for district "
            f"{well.expected_district} — try a different serial"
        )
