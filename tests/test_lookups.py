"""Tests for the MockFetcher: every fixture API resolves consistently."""

from __future__ import annotations

import pytest

from wellplug.lookups import (
    FetcherError,
    MockFetcher,
    RRCRoRQFetcher,
)
from tests.fixtures.sample_wellbores import ALL_FIXTURES


# Map fixture name -> API number (matches lookups._WELL_DATA keys)
_API_BY_FIXTURE = {
    "permian_deep_gas": "42-371-30001",
    "east_texas_shallow_oil": "42-401-12345",
    "buqw_uncovered_legacy": "42-103-77001",
    "no_surface_casing_legacy": "42-461-00042",
    "multi_zone_producer": "42-329-55555",
}


def test_mock_known_apis_match_fixtures() -> None:
    """MockFetcher should know exactly the 5 fixture APIs."""
    expected = set(_API_BY_FIXTURE.values())
    assert set(MockFetcher().known_api_numbers()) == expected


@pytest.mark.parametrize("fixture_name,api", list(_API_BY_FIXTURE.items()))
def test_well_lookup_consistent_with_fixture(fixture_name: str, api: str) -> None:
    """The lookup_well_by_api result must match what's in the corresponding
    Phase 1A fixture (lease, well, county)."""
    fetcher = MockFetcher()
    result = fetcher.lookup_well_by_api(api)
    fixture = ALL_FIXTURES[fixture_name]
    assert result["api_number"] == fixture.api_number
    assert result["lease_name"] == fixture.lease_name
    assert result["well_number"] == fixture.well_number
    assert result["county"] == fixture.county


@pytest.mark.parametrize("api", list(_API_BY_FIXTURE.values()))
def test_operator_lookup_resolves_via_p5(api: str) -> None:
    """operator_p5_for_api gives a P-5 number; lookup_operator returns a
    record matching that P-5."""
    fetcher = MockFetcher()
    p5 = fetcher.operator_p5_for_api(api)
    operator = fetcher.lookup_operator(p5)
    assert operator["operator_p5_number"] == p5
    assert operator["operator_name"]
    assert operator["operator_address"]


@pytest.mark.parametrize("fixture_name,api", list(_API_BY_FIXTURE.items()))
def test_gau_lookup_matches_fixture_buqw(fixture_name: str, api: str) -> None:
    fetcher = MockFetcher()
    gau = fetcher.lookup_gau(api)
    fixture = ALL_FIXTURES[fixture_name]
    assert gau["buqw_depth_ft"] == fixture.buqw.depth_ft


@pytest.mark.parametrize("fixture_name,api", list(_API_BY_FIXTURE.items()))
def test_completion_lookup_matches_fixture_geometry(
    fixture_name: str, api: str
) -> None:
    fetcher = MockFetcher()
    comp = fetcher.lookup_completion(api)
    fixture = ALL_FIXTURES[fixture_name]
    assert comp["total_depth_ft"] == fixture.total_depth_ft
    # Casing strings: same count, same set depths
    assert len(comp["casing_record"]) == len(fixture.casing)
    fixture_set_depths = sorted(c.set_depth_ft for c in fixture.casing)
    comp_set_depths = sorted(c["set_depth_ft"] for c in comp["casing_record"])
    assert comp_set_depths == fixture_set_depths
    # Perforations: same count, same intervals
    assert len(comp["perforations"]) == len(fixture.perforations)


def test_unknown_api_raises_fetcher_error() -> None:
    fetcher = MockFetcher()
    with pytest.raises(FetcherError):
        fetcher.lookup_well_by_api("42-999-99999")
    with pytest.raises(FetcherError):
        fetcher.lookup_gau("42-999-99999")
    with pytest.raises(FetcherError):
        fetcher.lookup_completion("42-999-99999")


def test_unknown_p5_raises_fetcher_error() -> None:
    with pytest.raises(FetcherError):
        MockFetcher().lookup_operator("999999")


def test_real_rrc_adapter_is_a_stub() -> None:
    """The Phase-2 adapter raises NotImplementedError on every method.
    This test pins the contract so we notice if someone adds a real
    implementation without updating dependent code."""
    rrc = RRCRoRQFetcher()
    with pytest.raises(NotImplementedError):
        rrc.lookup_well_by_api("42-371-30001")
    with pytest.raises(NotImplementedError):
        rrc.lookup_operator("112233")
    with pytest.raises(NotImplementedError):
        rrc.lookup_gau("42-371-30001")
    with pytest.raises(NotImplementedError):
        rrc.lookup_completion("42-371-30001")


def test_completion_record_returns_independent_copies() -> None:
    """Mutating a returned dict must not poison subsequent lookups."""
    fetcher = MockFetcher()
    a = fetcher.lookup_completion("42-371-30001")
    a["casing_record"][0]["od_in"] = 99.0
    b = fetcher.lookup_completion("42-371-30001")
    assert b["casing_record"][0]["od_in"] != 99.0
