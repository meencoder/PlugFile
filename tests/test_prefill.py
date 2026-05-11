"""Tests for the prefill engine + conflict detector."""

from __future__ import annotations

import pytest

from plugfile.lookups import MockFetcher
from plugfile.prefill import (
    FieldConflict,
    prefill_w3,
    prefill_w3_with_mock,
)
from plugfile.w3_schema import FieldSource


_API_BY_FIXTURE = {
    "permian_deep_gas": "42-371-30001",
    "east_texas_shallow_oil": "42-401-12345",
    "buqw_uncovered_legacy": "42-103-77001",
    "no_surface_casing_legacy": "42-461-00042",
    "multi_zone_producer": "42-329-55555",
}


@pytest.mark.parametrize("api", list(_API_BY_FIXTURE.values()))
def test_prefill_populates_section_i(api):
    form, _ = prefill_w3_with_mock(api)
    assert form.api_number == api
    assert form.operator_name
    assert form.operator_p5_number
    assert form.operator_address
    assert form.lease_name
    assert form.well_number
    assert form.county
    assert form.rrc_district


@pytest.mark.parametrize("api", list(_API_BY_FIXTURE.values()))
def test_prefill_populates_section_iii_iv_vi(api):
    form, _ = prefill_w3_with_mock(api)
    assert form.total_depth_ft is not None
    assert form.spud_date
    assert form.completion_date
    assert form.casing_record
    assert form.perforations
    for p in form.perforations:
        assert p["status"] in {"producing", "injection", "abandoned", "squeezed"}


@pytest.mark.parametrize("api", list(_API_BY_FIXTURE.values()))
def test_prefill_populates_section_vii_buqw(api):
    form, _ = prefill_w3_with_mock(api)
    assert form.buqw_depth_ft is not None
    assert form.gau_letter_reference
    assert isinstance(form.buqw_protected_by_surface_casing, bool)


@pytest.mark.parametrize("api", list(_API_BY_FIXTURE.values()))
def test_prefill_populates_section_viii_plug_record(api):
    form, _ = prefill_w3_with_mock(api)
    assert form.plug_record
    for plug in form.plug_record:
        assert plug["volume_sacks"] > 0
        assert plug["volume_ft3"] > 0
        assert "TAC" in plug["cite"]
        assert plug["rule_path"] in {"general", "special_buqw_uncovered"}


def test_prefill_buqw_uncovered_triggers_special_case():
    for api in ("42-103-77001", "42-461-00042"):
        form, _ = prefill_w3_with_mock(api)
        assert "special_buqw_uncovered" in form.plug_program_rule_paths
        assert form.buqw_protected_by_surface_casing is False


def test_prefill_protected_buqw_uses_general_only():
    for api in ("42-371-30001", "42-401-12345", "42-329-55555"):
        form, _ = prefill_w3_with_mock(api)
        assert form.plug_program_rule_paths == ["general"]
        assert form.buqw_protected_by_surface_casing is True


def test_operator_overrides_set_certification_fields():
    overrides = {
        "operator_signature_name": "Jane Doe",
        "operator_title": "Sr. Production Engineer",
        "certification_date": "2026-05-04",
        "cementing_company": "Halliburton",
    }
    form, _ = prefill_w3_with_mock("42-371-30001", overrides)
    assert form.operator_signature_name == "Jane Doe"
    assert form.operator_title == "Sr. Production Engineer"
    assert form.certification_date == "2026-05-04"
    assert form.cementing_company == "Halliburton"


def test_plugging_date_kwarg_is_applied():
    form, _ = prefill_w3_with_mock("42-371-30001", plugging_date="2026-06-15")
    assert form.plugging_date == "2026-06-15"


def test_perforation_status_override_is_merged():
    overrides = {
        "perforations": [
            {"top_ft": 10150.0, "zone_name": "Wolfcamp A", "status": "abandoned"},
        ],
    }
    form, _ = prefill_w3_with_mock("42-371-30001", overrides)
    perf = form.perforations[0]
    assert perf["zone_name"] == "Wolfcamp A"
    assert perf["status"] == "abandoned"
    assert perf["top_ft"] == 10150.0
    assert perf["bottom_ft"] == 10200.0


def test_conflict_warns_when_operator_overrides_authoritative_field():
    overrides = {"operator_name": "Wrong Name LLC"}
    form, conflicts = prefill_w3_with_mock("42-371-30001", overrides)
    assert form.operator_name == "Apex Permian Operating LLC"
    assert any(
        c.field_name == "operator_name" and c.severity == "warn"
        for c in conflicts
    )


def test_no_conflict_when_overrides_match_authoritative():
    fetcher = MockFetcher()
    well = fetcher.lookup_well_by_api("42-371-30001")
    overrides = {"county": well["county"], "lease_name": well["lease_name"]}
    _, conflicts = prefill_w3("42-371-30001", fetcher, overrides)
    for c in conflicts:
        assert c.field_name not in {"county", "lease_name"}


def test_unknown_override_field_is_silently_ignored():
    overrides = {"this_is_not_a_w3_field": "garbage"}
    form, conflicts = prefill_w3_with_mock("42-371-30001", overrides)
    assert form.api_number == "42-371-30001"
    assert all(c.field_name != "this_is_not_a_w3_field" for c in conflicts)


@pytest.mark.parametrize("api", list(_API_BY_FIXTURE.values()))
def test_prefilled_form_has_no_required_field_gaps_for_known_data(api):
    overrides = {
        "operator_signature_name": "Jane Doe",
        "operator_title": "Engineer",
        "certification_date": "2026-05-04",
    }
    form, _ = prefill_w3_with_mock(api, overrides, plugging_date="2026-05-04")
    missing = form.missing_required()
    assert not missing, f"{api}: prefill left required fields empty: {missing}"


def test_prefill_is_deterministic():
    a, _ = prefill_w3_with_mock("42-371-30001")
    b, _ = prefill_w3_with_mock("42-371-30001")
    assert a.to_dict() == b.to_dict()


def test_field_conflict_renders_human_readable():
    c = FieldConflict(
        field_name="county",
        operator_value="Foo",
        authoritative_value="Pecos",
        source=FieldSource.RRC_WELL_LOOKUP,
        severity="warn",
        message="test",
    )
    rendered = c.render()
    assert "WARN" in rendered
    assert "county" in rendered
    assert "Pecos" in rendered
