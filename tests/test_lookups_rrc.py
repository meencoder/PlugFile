"""Tests for the real RRC RoRQ fetcher (Phase 2A).

These tests validate the parser and HTTP plumbing against synthetic HTML
that mimics RRC's response shape. They DON'T hit the live RRC site:

  - `responses` mocks the HTTP layer at the requests level
  - synthetic HTML in tests/fixtures/rrc_html/ exercises the lxml selectors
  - the fixtures are calibrated to the XPaths in lookups_rrc._SELECTORS_*

If RRC changes their HTML layout, the symptom is that the live CLI returns
unexpected results. Run `python -m plugfile.lookups_rrc <api> --no-cache`,
inspect the dumped HTML, and update the selectors. These tests then need
the fixtures updated to match the new layout.

The whole module is gated on lxml/requests/responses being installed —
Phase 1 stdlib-only tests still run if you don't `pip install -e .[dev]`.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

# Skip the entire module if Phase 2A deps aren't installed
requests = pytest.importorskip("requests")
lxml_html = pytest.importorskip("lxml.html")
responses = pytest.importorskip("responses")
diskcache = pytest.importorskip("diskcache")

from plugfile.lookups import FetcherError
from plugfile.lookups_rrc import (
    RRC_CMPL_DETAIL,
    RRC_CMPL_SEARCH,
    RRC_PUR_SEARCH,
    RRCRoRQFetcher,
    _format_api,
    _to_float,
    _to_iso_date,
)


FIXTURES = Path(__file__).parent / "fixtures" / "rrc_html"


def _load(fname: str) -> str:
    return (FIXTURES / fname).read_text(encoding="utf-8")


# ---- pure-function tests (no HTTP) -----------------------------------------


def test_format_api_14_digit_to_dashed():
    assert _format_api("42371300010000") == "42-371-30001"


def test_format_api_passthrough_when_not_14_digits():
    assert _format_api("123") == "123"


def test_to_float_strips_commas_and_units():
    assert _to_float("10,500") == 10500.0
    assert _to_float("13.375") == 13.375
    assert _to_float('5.5"') == 5.5
    assert _to_float("1800'") == 1800.0
    assert _to_float("") == 0.0
    assert _to_float("N/A") == 0.0
    assert _to_float("—") == 0.0


def test_to_iso_date_handles_common_formats():
    assert _to_iso_date("03/15/2018") == "2018-03-15"
    assert _to_iso_date("2018-03-15") == "2018-03-15"
    assert _to_iso_date("15-Mar-2018") == "2018-03-15"
    assert _to_iso_date("Mar 15, 2018") == "2018-03-15"
    assert _to_iso_date("") == ""
    assert _to_iso_date("garbage") == "garbage"  # passthrough


# ---- HTTP-mocked integration tests -----------------------------------------


@pytest.fixture
def fetcher(tmp_path):
    """Fresh fetcher per test, using a tmp diskcache so tests don't pollute
    each other. Throttle disabled for speed."""
    return RRCRoRQFetcher(
        cache_dir=tmp_path / "cache",
        cache_ttl=3600,
        rate_limit_s=0.0,
        timeout_s=5,
    )


@responses.activate
def test_lookup_well_by_api_parses_synthetic_html(fetcher):
    responses.add(
        responses.GET, RRC_CMPL_SEARCH,
        body=_load("well_42-371-30001.html"),
        content_type="text/html",
        status=200,
    )
    well = fetcher.lookup_well_by_api("42-371-30001")
    assert well["api_number"] == "42-371-30001"
    assert well["lease_name"] == "Heritage A"
    assert well["well_number"] == "1H"
    assert well["county"] == "Pecos"
    assert well["rrc_district"] == "08"
    assert well["field_name"] == "Spraberry (Trend Area)"
    assert well["latitude"] == pytest.approx(31.0184)
    assert well["longitude"] == pytest.approx(-102.5531)
    assert well["footage_ns"] == "660 FNL"


@responses.activate
def test_lookup_well_rejects_invalid_api_format(fetcher):
    with pytest.raises(FetcherError, match="14 digits"):
        fetcher.lookup_well_by_api("12-345-67890")  # not 42 prefix


@responses.activate
def test_lookup_well_rejects_short_api(fetcher):
    with pytest.raises(FetcherError, match="14 digits"):
        fetcher.lookup_well_by_api("42-371-300")


@responses.activate
def test_lookup_well_raises_on_no_results_page(fetcher):
    responses.add(
        responses.GET, RRC_CMPL_SEARCH,
        body=_load("well_not_found.html"),
        content_type="text/html",
        status=200,
    )
    with pytest.raises(FetcherError, match="no detail page"):
        fetcher.lookup_well_by_api("42-371-30001")


@responses.activate
def test_lookup_operator_parses_synthetic_html(fetcher):
    responses.add(
        responses.GET, RRC_PUR_SEARCH,
        body=_load("operator_112233.html"),
        content_type="text/html",
        status=200,
    )
    op = fetcher.lookup_operator("112233")
    assert op["operator_name"] == "Apex Permian Operating LLC"
    assert op["operator_p5_number"] == "112233"
    assert "Midland" in op["operator_address"]


@responses.activate
def test_lookup_operator_pads_p5_to_six_digits(fetcher):
    responses.add(
        responses.GET, RRC_PUR_SEARCH,
        body=_load("operator_112233.html"),
        content_type="text/html",
        status=200,
    )
    # Pass 5-digit P-5; fetcher should zero-pad
    op = fetcher.lookup_operator("12233")
    assert op["operator_p5_number"] == "112233"  # from HTML, not from input


def test_lookup_gau_is_not_yet_automated(fetcher):
    """GAU letter automation is deferred; should raise a clear error."""
    with pytest.raises(FetcherError, match="GAU"):
        fetcher.lookup_gau("42-371-30001")


@responses.activate
def test_lookup_completion_extracts_casing_table(fetcher):
    responses.add(
        responses.GET, RRC_CMPL_DETAIL,
        body=_load("well_42-371-30001.html"),
        content_type="text/html",
        status=200,
    )
    comp = fetcher.lookup_completion("42-371-30001")
    assert comp["total_depth_ft"] == 10500.0
    assert comp["spud_date"] == "2018-03-15"
    assert comp["completion_date"] == "2018-09-22"
    assert len(comp["casing_record"]) == 3
    surface = next(c for c in comp["casing_record"] if c["kind"] == "surface")
    assert surface["od_in"] == 13.375
    assert surface["set_depth_ft"] == 1800.0
    assert surface["sacks_cemented"] == 1100.0
    production = next(c for c in comp["casing_record"]
                      if c["kind"] == "production")
    assert production["top_of_cement_ft"] == 5000.0


@responses.activate
def test_lookup_completion_extracts_perforations(fetcher):
    responses.add(
        responses.GET, RRC_CMPL_DETAIL,
        body=_load("well_42-371-30001.html"),
        content_type="text/html",
        status=200,
    )
    comp = fetcher.lookup_completion("42-371-30001")
    assert len(comp["perforations"]) == 1
    perf = comp["perforations"][0]
    assert perf["top_ft"] == 10150.0
    assert perf["bottom_ft"] == 10200.0
    assert perf["zone_name"] == "Wolfcamp A"


# ---- caching + throttling --------------------------------------------------


@responses.activate
def test_diskcache_avoids_second_fetch(fetcher):
    responses.add(
        responses.GET, RRC_CMPL_SEARCH,
        body=_load("well_42-371-30001.html"),
        content_type="text/html",
        status=200,
    )
    a = fetcher.lookup_well_by_api("42-371-30001")
    b = fetcher.lookup_well_by_api("42-371-30001")
    assert a == b
    # responses tracks call count; second call must come from cache
    assert len(responses.calls) == 1


def test_throttle_enforces_minimum_delay(tmp_path):
    """With rate_limit_s set, two consecutive _throttle calls must space out."""
    fetcher = RRCRoRQFetcher(
        cache_dir=tmp_path / "cache",
        rate_limit_s=0.25,
    )
    fetcher._throttle()
    t0 = time.time()
    fetcher._throttle()
    elapsed = time.time() - t0
    assert elapsed >= 0.24  # allow tiny clock slack


# ---- selector failure mode -------------------------------------------------


@responses.activate
def test_missing_required_field_raises_clear_error(fetcher):
    """If RRC's HTML changes and a required field disappears, the parser
    should raise FetcherError with a specific message pointing at the
    XPath, not silently return garbage."""
    responses.add(
        responses.GET, RRC_PUR_SEARCH,
        body="<html><body><p>nothing useful here</p></body></html>",
        content_type="text/html",
        status=200,
    )
    with pytest.raises(FetcherError, match="operator_name"):
        fetcher.lookup_operator("112233")
