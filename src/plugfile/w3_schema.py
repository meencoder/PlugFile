"""W-3 form-field schema with source-of-truth metadata.

The Texas RRC Form W-3 (Plugging Record) has ~50 scalar fields plus several
nested arrays (casing strings, tubing, perforations, plugs). This module
defines:

  1. FieldSource - enumeration of authoritative data sources every field
     must trace back to.
  2. FieldSpec - per-field metadata: source, RRC section, validation,
     required-ness.
  3. W3_SCHEMA - the complete W-3 field registry, organized by RRC section.
  4. W3Form - a typed in-memory representation that the prefill engine
     populates and the validator/exporter operate on.

Stdlib only. Schema metadata lives next to the fields it describes so the
JSON Schema exporter can walk the registry and emit a Draft 2020-12 doc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FieldSource(str, Enum):
    """Where each W-3 field's canonical value originates."""
    RRC_WELL_LOOKUP = "rrc_well_lookup"
    RRC_COMPLETION_RECORD = "rrc_completion_record"
    RRC_OPERATOR_DB = "rrc_operator_db"
    GAU_LETTER = "gau_letter"
    OPERATOR_INPUT = "operator_input"
    OPERATOR_OBSERVED = "operator_observed"
    OPERATOR_CERTIFICATION = "operator_certification"
    COMPUTED = "computed"


@dataclass(frozen=True)
class FieldSpec:
    """Metadata for one W-3 form field."""
    name: str
    description: str
    json_type: str
    source: FieldSource
    rrc_section: str
    required: bool = True
    pattern: str | None = None
    enum: tuple[str, ...] | None = None
    item_schema: tuple[FieldSpec, ...] | None = None
    array_items: dict[str, Any] | None = None
    unit: str | None = None
    canonical: bool = False

    def to_json_schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": self.json_type,
            "description": self.description,
            "x-source": self.source.value,
            "x-rrc-section": self.rrc_section,
            "x-canonical": self.canonical,
        }
        if self.pattern:
            out["pattern"] = self.pattern
        if self.enum:
            out["enum"] = list(self.enum)
        if self.unit:
            out["x-unit"] = self.unit
        if self.json_type == "array":
            if self.item_schema is not None:
                out["items"] = {
                    "type": "object",
                    "properties": {f.name: f.to_json_schema() for f in self.item_schema},
                    "required": [f.name for f in self.item_schema if f.required],
                }
            elif self.array_items is not None:
                out["items"] = dict(self.array_items)
        return out


CASING_RECORD_ITEM: tuple[FieldSpec, ...] = (
    FieldSpec("kind", "Surface / intermediate / production / liner / conductor",
              "string", FieldSource.RRC_COMPLETION_RECORD, "IV",
              enum=("conductor", "surface", "intermediate", "production", "liner")),
    FieldSpec("od_in", "Casing outer diameter", "number",
              FieldSource.RRC_COMPLETION_RECORD, "IV", unit="in"),
    FieldSpec("weight_lb_per_ft", "Casing weight per foot", "number",
              FieldSource.RRC_COMPLETION_RECORD, "IV", unit="lb/ft", required=False),
    FieldSpec("grade", "API casing grade (J-55, N-80, P-110, etc.)", "string",
              FieldSource.RRC_COMPLETION_RECORD, "IV", required=False),
    FieldSpec("set_depth_ft", "Shoe / set depth, MD", "number",
              FieldSource.RRC_COMPLETION_RECORD, "IV", unit="ft"),
    FieldSpec("top_of_cement_ft", "Top of cement in annulus, MD", "number",
              FieldSource.RRC_COMPLETION_RECORD, "IV", unit="ft"),
    FieldSpec("sacks_cemented", "Sacks of cement pumped at completion",
              "number", FieldSource.RRC_COMPLETION_RECORD, "IV", unit="sacks",
              required=False),
)

TUBING_RECORD_ITEM: tuple[FieldSpec, ...] = (
    FieldSpec("od_in", "Tubing outer diameter", "number",
              FieldSource.OPERATOR_OBSERVED, "V", unit="in"),
    FieldSpec("weight_lb_per_ft", "Tubing weight per foot", "number",
              FieldSource.OPERATOR_OBSERVED, "V", unit="lb/ft", required=False),
    FieldSpec("set_depth_ft", "Tubing set depth (or 'pulled' = 0)", "number",
              FieldSource.OPERATOR_OBSERVED, "V", unit="ft"),
)

PERFORATION_ITEM: tuple[FieldSpec, ...] = (
    FieldSpec("top_ft", "Top of perforated interval, MD", "number",
              FieldSource.RRC_COMPLETION_RECORD, "VI", unit="ft"),
    FieldSpec("bottom_ft", "Bottom of perforated interval, MD", "number",
              FieldSource.RRC_COMPLETION_RECORD, "VI", unit="ft"),
    FieldSpec("zone_name", "Geological zone name", "string",
              FieldSource.RRC_COMPLETION_RECORD, "VI"),
    FieldSpec("status", "producing / injection / abandoned / squeezed", "string",
              FieldSource.OPERATOR_INPUT, "VI",
              enum=("producing", "injection", "abandoned", "squeezed")),
)

PLUG_RECORD_ITEM: tuple[FieldSpec, ...] = (
    FieldSpec("name", "Plug identifier (e.g. surface_plug, perforation_X)",
              "string", FieldSource.COMPUTED, "VIII"),
    FieldSpec("top_ft", "Top of plug, MD", "number",
              FieldSource.COMPUTED, "VIII", unit="ft"),
    FieldSpec("bottom_ft", "Bottom of plug, MD", "number",
              FieldSource.COMPUTED, "VIII", unit="ft"),
    FieldSpec("bore", "Bore the plug sits inside", "string",
              FieldSource.COMPUTED, "VIII",
              enum=("inside_casing", "open_hole", "annulus")),
    FieldSpec("bore_diameter_in", "Bore diameter", "number",
              FieldSource.COMPUTED, "VIII", unit="in"),
    FieldSpec("volume_ft3", "Cement volume", "number",
              FieldSource.COMPUTED, "VIII", unit="ft^3"),
    FieldSpec("volume_bbl", "Cement volume in barrels", "number",
              FieldSource.COMPUTED, "VIII", unit="bbl"),
    FieldSpec("volume_sacks", "Cement volume in sacks", "number",
              FieldSource.COMPUTED, "VIII", unit="sacks"),
    FieldSpec("excess_factor", "Excess cement factor (0 = cased, 0.25 default OH)",
              "number", FieldSource.COMPUTED, "VIII"),
    FieldSpec("cite", "TAC paragraph authorizing the plug", "string",
              FieldSource.COMPUTED, "VIII"),
    FieldSpec("rule_path", "general | special_buqw_uncovered", "string",
              FieldSource.COMPUTED, "VIII",
              enum=("general", "special_buqw_uncovered")),
)


W3_SCHEMA: tuple[FieldSpec, ...] = (
    # Section I
    FieldSpec("api_number", "14-digit Texas API number (with dashes)",
              "string", FieldSource.RRC_WELL_LOOKUP, "I",
              pattern=r"^42-\d{3}-\d{5}$", canonical=True),
    FieldSpec("operator_name", "Operator legal name as on file with RRC",
              "string", FieldSource.RRC_OPERATOR_DB, "I"),
    FieldSpec("operator_p5_number", "RRC P-5 organization number",
              "string", FieldSource.RRC_OPERATOR_DB, "I",
              pattern=r"^\d{6}$"),
    FieldSpec("operator_address", "Operator mailing address",
              "string", FieldSource.RRC_OPERATOR_DB, "I"),
    FieldSpec("lease_name", "RRC-registered lease name",
              "string", FieldSource.RRC_WELL_LOOKUP, "I"),
    FieldSpec("lease_number", "RRC lease number (varies by district)",
              "string", FieldSource.RRC_WELL_LOOKUP, "I", required=False),
    FieldSpec("well_number", "Well number on the lease",
              "string", FieldSource.RRC_WELL_LOOKUP, "I"),
    FieldSpec("county", "Texas county name",
              "string", FieldSource.RRC_WELL_LOOKUP, "I"),
    FieldSpec("rrc_district", "RRC district 01-10 (or 6E, 7B, 7C, 8A)",
              "string", FieldSource.RRC_WELL_LOOKUP, "I"),
    FieldSpec("field_name", "RRC-recognized field name",
              "string", FieldSource.RRC_WELL_LOOKUP, "I", required=False),

    # Section II
    FieldSpec("latitude", "Surface lat, decimal degrees NAD27",
              "number", FieldSource.RRC_WELL_LOOKUP, "II", unit="deg"),
    FieldSpec("longitude", "Surface long, decimal degrees NAD27",
              "number", FieldSource.RRC_WELL_LOOKUP, "II", unit="deg"),
    FieldSpec("footage_ns", "Feet from N/S section/survey line",
              "string", FieldSource.RRC_WELL_LOOKUP, "II", required=False),
    FieldSpec("footage_ew", "Feet from E/W section/survey line",
              "string", FieldSource.RRC_WELL_LOOKUP, "II", required=False),
    FieldSpec("section_block_survey", "Section / Block / Survey designation",
              "string", FieldSource.RRC_WELL_LOOKUP, "II", required=False),

    # Section III
    FieldSpec("total_depth_ft", "Total measured depth at completion",
              "number", FieldSource.RRC_COMPLETION_RECORD, "III", unit="ft"),
    FieldSpec("plug_back_total_depth_ft", "Plug-back TD measured pre-plugging",
              "number", FieldSource.OPERATOR_OBSERVED, "III", unit="ft",
              required=False),
    FieldSpec("spud_date", "Date drilling commenced (ISO YYYY-MM-DD)",
              "string", FieldSource.RRC_COMPLETION_RECORD, "III",
              pattern=r"^\d{4}-\d{2}-\d{2}$", required=False),
    FieldSpec("completion_date", "Date well completed (ISO YYYY-MM-DD)",
              "string", FieldSource.RRC_COMPLETION_RECORD, "III",
              pattern=r"^\d{4}-\d{2}-\d{2}$", required=False),
    FieldSpec("plugging_date", "Date plugging operations performed",
              "string", FieldSource.OPERATOR_INPUT, "III",
              pattern=r"^\d{4}-\d{2}-\d{2}$"),

    # Section IV
    FieldSpec("casing_record", "All casing strings in the wellbore",
              "array", FieldSource.RRC_COMPLETION_RECORD, "IV",
              item_schema=CASING_RECORD_ITEM),

    # Section V
    FieldSpec("tubing_record", "Tubing strings present pre-plugging",
              "array", FieldSource.OPERATOR_OBSERVED, "V",
              item_schema=TUBING_RECORD_ITEM, required=False),

    # Section VI
    FieldSpec("perforations", "All perforated intervals + status",
              "array", FieldSource.RRC_COMPLETION_RECORD, "VI",
              item_schema=PERFORATION_ITEM),

    # Section VII
    FieldSpec("buqw_depth_ft", "Base of usable-quality water depth",
              "number", FieldSource.GAU_LETTER, "VII", unit="ft"),
    FieldSpec("gau_letter_reference", "GAU letter date / identifier",
              "string", FieldSource.GAU_LETTER, "VII"),
    FieldSpec("buqw_protected_by_surface_casing",
              "True iff surface casing covers BUQW with cement to surface",
              "boolean", FieldSource.COMPUTED, "VII"),

    # Section VIII
    FieldSpec("plug_record", "Ordered plug program from tac_3_14 engine",
              "array", FieldSource.COMPUTED, "VIII",
              item_schema=PLUG_RECORD_ITEM),
    FieldSpec("plug_program_rule_paths",
              "Distinct rule paths exercised (general / special_buqw_uncovered)",
              "array", FieldSource.COMPUTED, "VIII", required=False,
              array_items={"type": "string",
                           "enum": ["general", "special_buqw_uncovered"]}),

    # Section IX
    FieldSpec("surface_restoration_narrative",
              "Narrative of surface restoration work (Phase 1C drafter)",
              "string", FieldSource.OPERATOR_INPUT, "IX", required=False),

    # Section X
    FieldSpec("operator_signature_name", "Name of operator representative",
              "string", FieldSource.OPERATOR_CERTIFICATION, "X"),
    FieldSpec("operator_title", "Title of signing representative",
              "string", FieldSource.OPERATOR_CERTIFICATION, "X"),
    FieldSpec("certification_date", "Date of operator certification",
              "string", FieldSource.OPERATOR_CERTIFICATION, "X",
              pattern=r"^\d{4}-\d{2}-\d{2}$"),
    FieldSpec("cementing_company", "Name of cementing service company",
              "string", FieldSource.OPERATOR_CERTIFICATION, "X",
              required=False),
)


def schema_by_name() -> dict[str, FieldSpec]:
    return {f.name: f for f in W3_SCHEMA}


def schema_by_section() -> dict[str, list[FieldSpec]]:
    out: dict[str, list[FieldSpec]] = {}
    for f in W3_SCHEMA:
        out.setdefault(f.rrc_section, []).append(f)
    return out


def schema_by_source() -> dict[FieldSource, list[FieldSpec]]:
    out: dict[FieldSource, list[FieldSpec]] = {}
    for f in W3_SCHEMA:
        out.setdefault(f.source, []).append(f)
    return out


@dataclass
class W3Form:
    """A populated (or partially populated) W-3 form."""
    # Section I
    api_number: str | None = None
    operator_name: str | None = None
    operator_p5_number: str | None = None
    operator_address: str | None = None
    lease_name: str | None = None
    lease_number: str | None = None
    well_number: str | None = None
    county: str | None = None
    rrc_district: str | None = None
    field_name: str | None = None

    # Section II
    latitude: float | None = None
    longitude: float | None = None
    footage_ns: str | None = None
    footage_ew: str | None = None
    section_block_survey: str | None = None

    # Section III
    total_depth_ft: float | None = None
    plug_back_total_depth_ft: float | None = None
    spud_date: str | None = None
    completion_date: str | None = None
    plugging_date: str | None = None

    # Section IV-VI
    casing_record: list[dict[str, Any]] = field(default_factory=list)
    tubing_record: list[dict[str, Any]] = field(default_factory=list)
    perforations: list[dict[str, Any]] = field(default_factory=list)

    # Section VII
    buqw_depth_ft: float | None = None
    gau_letter_reference: str | None = None
    buqw_protected_by_surface_casing: bool | None = None

    # Section VIII
    plug_record: list[dict[str, Any]] = field(default_factory=list)
    plug_program_rule_paths: list[str] = field(default_factory=list)

    # Section IX
    surface_restoration_narrative: str | None = None

    # Section X
    operator_signature_name: str | None = None
    operator_title: str | None = None
    certification_date: str | None = None
    cementing_company: str | None = None

    def filled_fields(self) -> set[str]:
        out: set[str] = set()
        for spec in W3_SCHEMA:
            v = getattr(self, spec.name, None)
            if v is None:
                continue
            if isinstance(v, list) and not v:
                continue
            out.add(spec.name)
        return out

    def missing_required(self) -> set[str]:
        filled = self.filled_fields()
        return {f.name for f in W3_SCHEMA if f.required and f.name not in filled}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for spec in W3_SCHEMA:
            v = getattr(self, spec.name)
            if v is None:
                continue
            if isinstance(v, list) and not v:
                continue
            out[spec.name] = v
        return out
