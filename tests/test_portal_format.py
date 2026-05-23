"""Tests for the Portal Field-Format Validator (portal_format.py).

Validates that internal Plugfile values are converted to the exact string
formats required by the RRC Online System web portal.
"""

from __future__ import annotations

import json
import pytest

from plugfile.portal_format import (
    PortalFormatResult,
    date_to_portal,
    depth_to_portal,
    format_for_portal_with_mock,
    od_to_fraction,
    sacks_to_portal,
    validate_api_number,
)

API = "42-371-30001"   # Apex Permian mock wellbore


# ── od_to_fraction ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (4.5,    "4 1/2"),
    (7.0,    "7"),
    (8.625,  "8 5/8"),
    (9.625,  "9 5/8"),
    (13.375, "13 3/8"),
    (16.0,   "16"),
    (5.5,    "5 1/2"),
    (2.875,  "2 7/8"),
])
def test_od_to_fraction(value, expected):
    assert od_to_fraction(value) == expected


def test_od_whole_number_no_fraction():
    assert od_to_fraction(7.0) == "7"
    assert od_to_fraction(16.0) == "16"


# ── depth_to_portal ───────────────────────────────────────────────────────────

def test_depth_integer_string():
    assert depth_to_portal(1500.0) == "1500"


def test_depth_zero_is_zero_not_decimal():
    assert depth_to_portal(0.0) == "0"


def test_depth_rounds_to_nearest_int():
    assert depth_to_portal(1500.4) == "1500"
    assert depth_to_portal(1500.6) == "1501"


def test_depth_none_passthrough():
    assert depth_to_portal(None) is None


# ── date_to_portal ────────────────────────────────────────────────────────────

def test_date_iso_to_mmddyyyy():
    assert date_to_portal("2026-05-21") == "05/21/2026"


def test_date_leading_zeros_preserved():
    assert date_to_portal("2026-01-04") == "01/04/2026"


def test_date_none_passthrough():
    assert date_to_portal(None) is None


def test_date_empty_string_passthrough():
    assert date_to_portal("") is None


def test_date_bad_format_raises():
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        date_to_portal("21/05/2026")


# ── sacks_to_portal ───────────────────────────────────────────────────────────

def test_sacks_rounds_to_int():
    assert sacks_to_portal(47.8) == "48"
    assert sacks_to_portal(47.2) == "47"


def test_sacks_none_passthrough():
    assert sacks_to_portal(None) is None


# ── validate_api_number ───────────────────────────────────────────────────────

def test_valid_api_number():
    ok, msg = validate_api_number("42-371-30001")
    assert ok
    assert msg is None


def test_invalid_api_number_no_dashes():
    ok, msg = validate_api_number("4237130001")
    assert not ok
    assert msg is not None


def test_invalid_api_number_wrong_segment_length():
    ok, msg = validate_api_number("42-3710-3001")
    assert not ok


# ── format_for_portal_with_mock (integration) ─────────────────────────────────

def test_returns_portal_format_result():
    result, conflicts = format_for_portal_with_mock(API)
    assert isinstance(result, PortalFormatResult)
    assert isinstance(conflicts, list)


def test_api_number_echoed():
    result, _ = format_for_portal_with_mock(API)
    assert result.api_number == API


def test_ready_to_copy_is_bool():
    result, _ = format_for_portal_with_mock(API)
    assert isinstance(result.ready_to_copy, bool)


def test_depths_are_integer_strings():
    result, _ = format_for_portal_with_mock(API)
    for key, val in result.depths.items():
        if val is not None and key.endswith("_ft"):
            assert re.match(r"^\d+$", val), f"{key}={val!r} is not an integer string"


def test_casing_od_is_fraction_string():
    result, _ = format_for_portal_with_mock(API)
    for row in result.casing:
        od = row["od_in"]
        if od is not None:
            # Should be a fraction string like "9 5/8" or a whole number like "7"
            assert "/" in od or od.isdigit() or od.replace(" ", "").replace("/", "").isdigit()


def test_proposed_plugs_nonempty():
    result, _ = format_for_portal_with_mock(API)
    assert len(result.proposed_plugs) > 0


def test_proposed_plug_depths_are_integer_strings():
    result, _ = format_for_portal_with_mock(API)
    for plug in result.proposed_plugs:
        for key in ("top_ft", "bottom_ft"):
            val = plug[key]
            if val is not None:
                assert val.isdigit() or (val.lstrip("-").isdigit()), \
                    f"plug[{key!r}]={val!r} is not an integer string"


def test_proposed_plug_has_rank_and_cite():
    result, _ = format_for_portal_with_mock(API)
    for plug in result.proposed_plugs:
        assert plug["rank"]
        assert plug["cite"]
        assert plug["rationale"]


def test_to_dict_is_json_serializable():
    result, _ = format_for_portal_with_mock(API)
    d = result.to_dict()
    json.dumps(d)   # must not raise
    assert d["api_number"] == API
    assert "ready_to_copy" in d
    assert "warnings" in d
    assert "casing" in d
    assert "proposed_plugs" in d


def test_well_identity_populated():
    result, _ = format_for_portal_with_mock(API)
    ident = result.well_identity
    assert ident["operator_name"]
    assert ident["county"]


def test_all_five_mock_apis():
    apis = [
        "42-371-30001",
        "42-401-12345",
        "42-103-77001",
        "42-461-00042",
        "42-329-55555",
    ]
    for api in apis:
        result, _ = format_for_portal_with_mock(api)
        assert result.api_number == api
        assert len(result.proposed_plugs) > 0


import re   # noqa: E402  (imported at bottom to avoid moving test body)
