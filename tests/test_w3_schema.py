"""Tests for the W-3 schema, including JSON Schema export."""

from __future__ import annotations

import json
import re

import pytest

from plugfile.json_schema_export import export_w3_json_schema
from plugfile.w3_schema import (
    FieldSource,
    W3_SCHEMA,
    W3Form,
    schema_by_name,
    schema_by_section,
    schema_by_source,
)


# ---- registry invariants ---------------------------------------------------


def test_every_field_has_unique_name() -> None:
    names = [f.name for f in W3_SCHEMA]
    assert len(names) == len(set(names))


def test_every_field_has_a_source() -> None:
    for f in W3_SCHEMA:
        assert isinstance(f.source, FieldSource)


def test_every_field_has_an_rrc_section() -> None:
    valid = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
    for f in W3_SCHEMA:
        assert f.rrc_section in valid


def test_canonical_field_is_api_number() -> None:
    canonical = [f for f in W3_SCHEMA if f.canonical]
    assert len(canonical) == 1
    assert canonical[0].name == "api_number"


def test_api_number_pattern_validates_real_examples() -> None:
    api_field = schema_by_name()["api_number"]
    assert api_field.pattern is not None
    rx = re.compile(api_field.pattern)
    for good in ("42-371-30001", "42-401-12345", "42-329-55555"):
        assert rx.match(good), f"{good} should match"
    for bad in ("42-37-30001", "421-371-30001", "42_371_30001"):
        assert not rx.match(bad), f"{bad} should NOT match"


def test_computed_fields_only_in_section_vii_and_viii() -> None:
    for f in W3_SCHEMA:
        if f.source == FieldSource.COMPUTED:
            assert f.rrc_section in {"VII", "VIII"}


def test_section_grouping_is_complete() -> None:
    by_section = schema_by_section()
    for section in ("I", "II", "III", "IV", "VI", "VII", "VIII", "X"):
        assert section in by_section


def test_source_grouping_includes_all_sources() -> None:
    by_source = schema_by_source()
    expected = {
        FieldSource.RRC_WELL_LOOKUP,
        FieldSource.RRC_OPERATOR_DB,
        FieldSource.RRC_COMPLETION_RECORD,
        FieldSource.GAU_LETTER,
        FieldSource.OPERATOR_INPUT,
        FieldSource.OPERATOR_CERTIFICATION,
        FieldSource.COMPUTED,
    }
    assert expected.issubset(by_source.keys())


def test_array_fields_have_item_specs() -> None:
    for f in W3_SCHEMA:
        if f.json_type == "array":
            assert (f.item_schema is not None
                    or f.array_items is not None), (
                f"{f.name} is an array but has neither item_schema nor "
                f"array_items"
            )


def test_plug_record_item_schema_is_all_computed() -> None:
    plug_field = schema_by_name()["plug_record"]
    assert plug_field.item_schema is not None
    for sub in plug_field.item_schema:
        assert sub.source == FieldSource.COMPUTED


def test_json_schema_export_is_valid_json() -> None:
    doc = export_w3_json_schema()
    serialized = json.dumps(doc)
    roundtrip = json.loads(serialized)
    assert roundtrip == doc


def test_json_schema_uses_draft_2020_12() -> None:
    doc = export_w3_json_schema()
    assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_json_schema_lists_all_required_fields() -> None:
    doc = export_w3_json_schema()
    expected_required = {f.name for f in W3_SCHEMA if f.required}
    assert set(doc["required"]) == expected_required


def test_json_schema_carries_x_source_annotations() -> None:
    doc = export_w3_json_schema()
    for spec in W3_SCHEMA:
        assert spec.name in doc["properties"]
        prop = doc["properties"][spec.name]
        assert prop["x-source"] == spec.source.value
        assert prop["x-rrc-section"] == spec.rrc_section


def test_json_schema_marks_canonical_fields() -> None:
    doc = export_w3_json_schema()
    api = doc["properties"]["api_number"]
    assert api["x-canonical"] is True


def test_json_schema_array_items_inherit_metadata() -> None:
    doc = export_w3_json_schema()
    cas = doc["properties"]["casing_record"]
    assert cas["type"] == "array"
    assert cas["items"]["type"] == "object"
    assert "od_in" in cas["items"]["properties"]
    assert cas["items"]["properties"]["od_in"]["x-unit"] == "in"


def test_json_schema_string_array_has_enum_items() -> None:
    doc = export_w3_json_schema()
    rule_paths = doc["properties"]["plug_program_rule_paths"]
    assert rule_paths["type"] == "array"
    assert rule_paths["items"]["type"] == "string"
    assert set(rule_paths["items"]["enum"]) == {
        "general", "special_buqw_uncovered"
    }


def test_w3form_starts_empty() -> None:
    form = W3Form()
    assert form.filled_fields() == set()
    assert "api_number" in form.missing_required()


def test_w3form_filled_fields_tracks_assignments() -> None:
    form = W3Form()
    form.api_number = "42-371-30001"
    form.operator_name = "Apex"
    assert {"api_number", "operator_name"} <= form.filled_fields()


def test_w3form_to_dict_omits_unset_fields() -> None:
    form = W3Form()
    form.api_number = "42-401-12345"
    d = form.to_dict()
    assert d == {"api_number": "42-401-12345"}


def test_w3form_to_dict_includes_arrays_when_populated() -> None:
    form = W3Form()
    form.api_number = "42-401-12345"
    form.casing_record = [{"kind": "surface", "od_in": 8.625}]
    d = form.to_dict()
    assert "casing_record" in d
    assert d["casing_record"][0]["kind"] == "surface"


def test_w3form_to_dict_skips_empty_arrays() -> None:
    form = W3Form()
    form.api_number = "42-401-12345"
    assert "casing_record" not in form.to_dict()


@pytest.mark.parametrize("required_field", [
    f.name for f in W3_SCHEMA if f.required and f.json_type != "array"
])
def test_w3form_missing_required_includes_each_required_scalar(
    required_field: str,
) -> None:
    form = W3Form()
    assert required_field in form.missing_required()
