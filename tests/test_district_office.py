"""Tests for auto district-office routing (district_office.py)."""

from __future__ import annotations

import json

import pytest

from plugfile.district_office import (
    RRC_DISTRICT_OFFICES,
    DistrictRouting,
    district_office_for,
    normalize_district_code,
    route_by_api_with_mock,
    route_filing,
)


# ── code normalization ────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("8", "08"),
    ("08", "08"),
    (" 8 ", "08"),
    ("10", "10"),
    ("7c", "7C"),
    ("7C", "7C"),
    ("6e", "6E"),
    ("8a", "8A"),
    ("07B", "7B"),
    ("", None),
    (None, None),
])
def test_normalize_district_code(raw, expected):
    assert normalize_district_code(raw) == expected


# ── code → office ─────────────────────────────────────────────────────────────

def test_district_08_is_midland():
    o = district_office_for("08")
    assert o is not None
    assert o.name == "Midland"
    assert o.phone == "432-684-5581"
    assert o.email == "midland@rrc.texas.gov"


def test_single_digit_district_resolves():
    assert district_office_for("8").name == "Midland"


def test_districts_01_02_share_san_antonio():
    assert district_office_for("01").key == "san_antonio"
    assert district_office_for("02").key == "san_antonio"


def test_districts_05_06_6e_share_kilgore():
    assert district_office_for("05").key == "kilgore"
    assert district_office_for("06").key == "kilgore"
    assert district_office_for("6E").key == "kilgore"


def test_kilgore_has_no_fax():
    assert district_office_for("06").fax is None


def test_alpha_districts():
    assert district_office_for("7B").name == "Abilene"
    assert district_office_for("7C").name == "San Angelo"
    assert district_office_for("8A").name == "Lubbock"


def test_unknown_district_returns_none():
    assert district_office_for("99") is None
    assert district_office_for(None) is None


# ── every office well-formed + districts unique ───────────────────────────────

def test_all_offices_well_formed():
    for o in RRC_DISTRICT_OFFICES:
        assert o.name and o.address_line1 and o.city_state_zip
        assert o.phone and o.email.endswith("@rrc.texas.gov")
        assert o.districts


def test_no_district_mapped_twice():
    seen: set[str] = set()
    for o in RRC_DISTRICT_OFFICES:
        for code in o.districts:
            assert code not in seen, f"District {code} mapped to two offices"
            seen.add(code)


# ── route_filing (pure) ───────────────────────────────────────────────────────

def test_route_filing_matches():
    r = route_filing(rrc_district="08", county="Midland", api_number="42-329-1")
    assert isinstance(r, DistrictRouting)
    assert r.matched
    assert r.office.name == "Midland"
    assert r.filing_note
    assert r.warnings == []


def test_route_filing_no_district_warns():
    r = route_filing(rrc_district=None)
    assert not r.matched
    assert r.office is None
    assert r.warnings


def test_route_filing_unknown_district_warns():
    r = route_filing(rrc_district="42")
    assert not r.matched
    assert any("did not match" in w for w in r.warnings)


# ── route_by_api (mock lookup) ────────────────────────────────────────────────

def test_route_by_api_resolves_office():
    r = route_by_api_with_mock("42-371-30001")   # Pecos, district 08
    assert r.matched
    assert r.office.name == "Midland"
    assert r.rrc_district == "08"
    assert r.county == "Pecos"


@pytest.mark.parametrize("api,office_name", [
    ("42-371-30001", "Midland"),     # district 08
    ("42-401-12345", "Kilgore"),     # district 06
    ("42-103-77001", "San Angelo"),  # district 7C
    ("42-461-00042", "Abilene"),     # district 7B
    ("42-329-55555", "Midland"),     # district 08
])
def test_all_mock_wells_route(api, office_name):
    r = route_by_api_with_mock(api)
    assert r.matched
    assert r.office.name == office_name


# ── serialization ─────────────────────────────────────────────────────────────

def test_to_dict_json_serializable():
    r = route_by_api_with_mock("42-371-30001")
    d = r.to_dict()
    json.dumps(d)
    assert d["office"]["name"] == "Midland"
    assert d["rrc_district"] == "08"
    assert "source" in d
