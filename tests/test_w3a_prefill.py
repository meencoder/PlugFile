"""Tests for the W-3A (Notice of Intention to Plug) prefill engine.

Mirrors the W-3 prefill tests but exercises `prefill_w3a` / `W3AForm`. Uses the
in-memory MockFetcher (5 seeded Texas wellbores). The key behaviours under test:

  * authoritative fields populate from the well / operator / GAU / completion
    lookups (Boxes 1-16 + casing/perforations)
  * the *proposed* plug program is computed by the §3.14 engine
  * operator-sourced fields (well/completion type, AOR, certification) come
    from overrides
  * warn-and-flag conflict detection matches the W-3 policy
"""

from __future__ import annotations

import pytest

from plugfile.prefill_w3a import prefill_w3a, prefill_w3a_with_mock
from plugfile.w3a_schema import W3A_SCHEMA, W3AForm, w3a_schema_by_name
from plugfile.w3_schema import FieldSource

API = "42-371-30001"  # Apex Permian / Pecos / D08 / Heritage A 1H


# ---- authoritative population ----------------------------------------------

def test_prefill_populates_identity():
    form, _ = prefill_w3a_with_mock(API)
    assert form.api_number == API
    assert form.operator_name == "Apex Permian Operating LLC"
    assert form.operator_p5_number == "112233"
    assert form.county == "Pecos"
    assert form.rrc_district == "08"
    assert form.lease_name == "Heritage A"
    assert form.well_number == "1H"


def test_prefill_sets_gau_box16():
    form, _ = prefill_w3a_with_mock(API)
    assert form.buqw_depth_ft == 1500.0
    assert form.gau_letter_reference == "GAU-2024-03-12-Pecos-21874"


def test_prefill_sets_completion_box15_and_casing():
    form, _ = prefill_w3a_with_mock(API)
    assert form.total_depth_ft == 10500.0
    assert len(form.casing_record) == 3
    assert len(form.perforations) == 1
    assert {c["kind"] for c in form.casing_record} == {
        "surface", "intermediate", "production"
    }


# ---- the proposal (computed) -----------------------------------------------

def test_prefill_computes_proposed_plug_program():
    form, _ = prefill_w3a_with_mock(API)
    assert form.proposed_plug_record, "expected a non-empty proposed plug program"
    # every proposed plug carries a TAC citation + computed volume
    for plug in form.proposed_plug_record:
        assert plug["cite"]
        assert plug["volume_sacks"] is not None
    assert form.plug_program_rule_paths  # at least one rule path exercised
    assert isinstance(form.buqw_protected_by_surface_casing, bool)


# ---- operator overrides ----------------------------------------------------

def test_prefill_applies_type_and_cementer_overrides():
    form, _ = prefill_w3a_with_mock(API, {
        "well_type": "oil",
        "completion_type": "single",
        "cementing_company": "Permian Cementing Services",
        "cementer_p5_specialty_code": "CEMENT",
    })
    assert form.well_type == "oil"
    assert form.completion_type == "single"
    assert form.cementing_company == "Permian Cementing Services"
    assert form.cementer_p5_specialty_code == "CEMENT"


def test_prefill_applies_aor_findings():
    aor = [{
        "well_id": "42-371-30099",
        "zone_name": "San Andres",
        "depth_ft": 4200.0,
        "distance_mi": 0.3,
        "direction": "NE",
        "requires_isolation": True,
    }]
    form, _ = prefill_w3a_with_mock(API, {"aor_findings": aor})
    assert len(form.aor_findings) == 1
    assert form.aor_findings[0]["zone_name"] == "San Andres"


def test_prefill_applies_historic_plugs():
    hist = [{"top_ft": 5000.0, "bottom_ft": 5100.0,
             "kind": "CIBP+cement", "previously_reported": False}]
    form, _ = prefill_w3a_with_mock(API, {"historic_plugs": hist})
    assert len(form.historic_plugs) == 1
    assert form.historic_plugs[0]["kind"] == "CIBP+cement"


# ---- conflict detection ----------------------------------------------------

def test_authoritative_override_conflict_is_warned_and_value_retained():
    form, conflicts = prefill_w3a_with_mock(API, {"county": "Wrongville"})
    # authoritative value wins
    assert form.county == "Pecos"
    # a warn-severity conflict is recorded against the RRC-sourced field
    county_conflicts = [c for c in conflicts if c.field_name == "county"]
    assert len(county_conflicts) == 1
    assert county_conflicts[0].severity == "warn"
    assert county_conflicts[0].source == FieldSource.RRC_WELL_LOOKUP


def test_operator_field_override_is_info_only():
    # operator_title is an operator-certification field; supplying it is normal
    form, conflicts = prefill_w3a_with_mock(API, {"operator_title": "Agent"})
    assert form.operator_title == "Agent"
    assert all(c.severity != "error" for c in conflicts)


# ---- required-field accounting ---------------------------------------------

def test_missing_required_before_operator_input():
    form, _ = prefill_w3a_with_mock(API)
    missing = form.missing_required()
    # everything authoritative is filled; only operator-input fields remain
    assert missing == {
        "well_type", "completion_type",
        "operator_signature_name", "operator_title", "certification_date",
    }


def test_no_missing_required_after_full_operator_input():
    form, _ = prefill_w3a_with_mock(API, {
        "well_type": "oil",
        "completion_type": "single",
        "operator_signature_name": "Sharmeen Q.",
        "operator_title": "Operator Representative",
        "certification_date": "2026-05-21",
    })
    assert form.missing_required() == set()


# ---- all seeded wellbores prefill cleanly ----------------------------------

@pytest.mark.parametrize("api", [
    "42-371-30001", "42-401-12345", "42-103-77001",
    "42-461-00042", "42-329-55555",
])
def test_all_mock_apis_prefill(api):
    form, _ = prefill_w3a_with_mock(api)
    assert form.api_number == api
    assert form.total_depth_ft and form.total_depth_ft > 0
    assert form.proposed_plug_record  # proposal computed for every well


# ---- schema sanity ---------------------------------------------------------

def test_schema_field_names_match_form_attributes():
    form = W3AForm()
    for spec in W3A_SCHEMA:
        assert hasattr(form, spec.name), f"W3AForm missing attr {spec.name!r}"


def test_w3a_specific_fields_present_in_schema():
    names = set(w3a_schema_by_name())
    for new_field in ("drilling_permit_no", "rule_37_case_no", "well_type",
                      "completion_type", "aor_findings", "cementer_p5_specialty_code",
                      "w3a_expiration_date", "proposed_plug_record"):
        assert new_field in names
