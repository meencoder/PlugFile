"""W-3A (Notice of Intention to Plug and Abandon) form-field schema.

The W-3A is the *forward-looking* sibling of the W-3 Plugging Record: it is
filed BEFORE plugging to declare intent, where the W-3 records what was
actually done.  Crucially, the deterministic §3.14 plug-program engine
(`compute_plug_program`) produces the **proposed** plug program that the W-3A
needs — so most of this form is already computable from the same wellbore data
the W-3 prefill fetches.

This module mirrors `w3_schema` and deliberately *reuses* its shared building
blocks (`FieldSpec`, `FieldSource`, and the `CASING_RECORD_ITEM` /
`PERFORATION_ITEM` / `PLUG_RECORD_ITEM` item-schemas) so the two forms cannot
drift apart.  Field/box numbering follows the official Form W-3A
(`docs/w-3ap.pdf`, Rev 1/1/83).

W-3A-specific additions vs. the W-3:
  * Box 6  Drilling Permit No.
  * Box 7  Rule 37 Case No.
  * Box 12 Abstract No. + free-text location ("distance & direction from town")
  * Box 13 Type of well (oil / gas / disposal / injection / other)
  * Box 14 Type of completion (single / multiple)
  * Box 17 Area of Review (AOR) findings — shallower-zone wells nearby
  * GAU letter date (Box 16 area)
  * Approved cementer P-5 specialty code  (training deck p19)
  * W-3A issue / expiration dates          (training deck p20)
  * Historic plug info                      (training deck p14)

Dropped vs. the W-3: Section IX surface-restoration narrative and the
as-plugged actuals (those belong on the after-the-fact W-3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .w3_schema import (
    CASING_RECORD_ITEM,
    PERFORATION_ITEM,
    PLUG_RECORD_ITEM,
    FieldSource,
    FieldSpec,
)


# ---- W-3A-specific nested item schemas -------------------------------------

AOR_FINDING_ITEM: tuple[FieldSpec, ...] = (
    FieldSpec("well_id", "API or lease/well id of the nearby well", "string",
              FieldSource.OPERATOR_INPUT, "17"),
    FieldSpec("zone_name", "Shallower zone the nearby well produces/produced from",
              "string", FieldSource.OPERATOR_INPUT, "17"),
    FieldSpec("depth_ft", "Approx. depth of that zone", "number",
              FieldSource.OPERATOR_INPUT, "17", unit="ft", required=False),
    FieldSpec("distance_mi", "Distance from the subject well", "number",
              FieldSource.OPERATOR_INPUT, "17", unit="mi", required=False),
    FieldSpec("direction", "Direction from the subject well (e.g. NE)", "string",
              FieldSource.OPERATOR_INPUT, "17", required=False),
    FieldSpec("requires_isolation",
              "True if this zone must be isolated by a cement plug",
              "boolean", FieldSource.OPERATOR_INPUT, "17", required=False),
)

HISTORIC_PLUG_ITEM: tuple[FieldSpec, ...] = (
    FieldSpec("top_ft", "Top of previously-set isolation interval, MD", "number",
              FieldSource.OPERATOR_OBSERVED, "hist", unit="ft"),
    FieldSpec("bottom_ft", "Bottom of previously-set isolation interval, MD",
              "number", FieldSource.OPERATOR_OBSERVED, "hist", unit="ft"),
    FieldSpec("kind", "Nature of the historic plug (e.g. 'CIBP+cement')", "string",
              FieldSource.OPERATOR_OBSERVED, "hist"),
    FieldSpec("previously_reported",
              "Whether this was reported to the RRC before (attach W-15 if not)",
              "boolean", FieldSource.OPERATOR_OBSERVED, "hist", required=False),
)


# ---- the W-3A field registry ------------------------------------------------

W3A_SCHEMA: tuple[FieldSpec, ...] = (
    # Box 1 / 2 — operator
    FieldSpec("api_number", "14-digit Texas API number (with dashes)", "string",
              FieldSource.RRC_WELL_LOOKUP, "5",
              pattern=r"^42-\d{3}-\d{5}$", canonical=True),
    FieldSpec("operator_name", "Operator legal name as on Form P-5", "string",
              FieldSource.RRC_OPERATOR_DB, "1"),
    FieldSpec("operator_address", "Operator mailing address", "string",
              FieldSource.RRC_OPERATOR_DB, "1"),
    FieldSpec("operator_p5_number", "RRC P-5 organization number", "string",
              FieldSource.RRC_OPERATOR_DB, "2", pattern=r"^\d{6}$"),
    FieldSpec("rrc_district", "RRC district 01-10 (or 6E, 7B, 7C, 8A)", "string",
              FieldSource.RRC_WELL_LOOKUP, "3"),
    FieldSpec("county", "Texas county of the well site", "string",
              FieldSource.RRC_WELL_LOOKUP, "4"),
    FieldSpec("drilling_permit_no", "RRC drilling permit number", "string",
              FieldSource.RRC_WELL_LOOKUP, "6", required=False),
    FieldSpec("rule_37_case_no", "Rule 37 exception case number, if any", "string",
              FieldSource.RRC_WELL_LOOKUP, "7", required=False),
    FieldSpec("lease_number", "Oil Lease No. or Gas Well ID No.", "string",
              FieldSource.RRC_WELL_LOOKUP, "8", required=False),
    FieldSpec("well_number", "Well number on the lease", "string",
              FieldSource.RRC_WELL_LOOKUP, "9"),
    FieldSpec("field_name", "RRC-recognized field name", "string",
              FieldSource.RRC_WELL_LOOKUP, "10", required=False),
    FieldSpec("lease_name", "RRC-registered lease name", "string",
              FieldSource.RRC_WELL_LOOKUP, "11"),

    # Box 12 — location
    FieldSpec("footage_ns", "Feet from N/S section/survey line", "string",
              FieldSource.RRC_WELL_LOOKUP, "12", required=False),
    FieldSpec("footage_ew", "Feet from E/W section/survey line", "string",
              FieldSource.RRC_WELL_LOOKUP, "12", required=False),
    FieldSpec("section_block_survey", "Section / Block / Survey designation",
              "string", FieldSource.RRC_WELL_LOOKUP, "12", required=False),
    FieldSpec("abstract_no", "Abstract number (A-####)", "string",
              FieldSource.RRC_WELL_LOOKUP, "12", required=False),
    FieldSpec("location_description",
              "Distance (mi) and direction from a nearby named town", "string",
              FieldSource.OPERATOR_INPUT, "12", required=False),

    # Box 13 / 14 — type
    FieldSpec("well_type", "Type of well", "string", FieldSource.OPERATOR_INPUT,
              "13", enum=("oil", "gas", "disposal", "injection", "other")),
    FieldSpec("completion_type", "Type of completion", "string",
              FieldSource.OPERATOR_INPUT, "14", enum=("single", "multiple")),

    # Box 15 — depth
    FieldSpec("total_depth_ft", "Total measured depth", "number",
              FieldSource.RRC_COMPLETION_RECORD, "15", unit="ft"),

    # Casing + perforations (pre-populate per the online guide)
    FieldSpec("casing_record", "All casing strings in the wellbore", "array",
              FieldSource.RRC_COMPLETION_RECORD, "casing",
              item_schema=CASING_RECORD_ITEM),
    FieldSpec("perforations", "All perforated intervals", "array",
              FieldSource.RRC_COMPLETION_RECORD, "perf",
              item_schema=PERFORATION_ITEM),

    # Box 16 — usable-quality water (GAU). Required for the W-3A to be reviewed.
    FieldSpec("buqw_depth_ft", "Base of usable-quality water depth", "number",
              FieldSource.GAU_LETTER, "16", unit="ft"),
    FieldSpec("gau_letter_reference", "GAU letter identifier", "string",
              FieldSource.GAU_LETTER, "16"),
    FieldSpec("gau_letter_date", "GAU determination letter issue date", "string",
              FieldSource.GAU_LETTER, "16", required=False),

    # Box 17 — Area of Review
    FieldSpec("aor_findings",
              "Shallower-zone wells within the area of review needing isolation",
              "array", FieldSource.OPERATOR_INPUT, "17",
              item_schema=AOR_FINDING_ITEM, required=False),

    # Historic plug information (training deck p14)
    FieldSpec("historic_plugs",
              "Previously-set isolation intervals (CIBP w/ cement, etc.)",
              "array", FieldSource.OPERATOR_OBSERVED, "hist",
              item_schema=HISTORIC_PLUG_ITEM, required=False),

    # Proposed plug program — THE proposal, from the §3.14 engine
    FieldSpec("proposed_plug_record",
              "Proposed plug program computed by the tac_3_14 engine", "array",
              FieldSource.COMPUTED, "proposal", item_schema=PLUG_RECORD_ITEM),
    FieldSpec("plug_program_rule_paths",
              "Distinct rule paths exercised (general / special_buqw_uncovered)",
              "array", FieldSource.COMPUTED, "proposal", required=False,
              array_items={"type": "string",
                           "enum": ["general", "special_buqw_uncovered"]}),
    FieldSpec("buqw_protected_by_surface_casing",
              "True iff surface casing covers BUQW with cement to surface",
              "boolean", FieldSource.COMPUTED, "proposal", required=False),

    # Cementer (training deck p19)
    FieldSpec("cementing_company", "Name of cementing service company", "string",
              FieldSource.OPERATOR_INPUT, "cementer", required=False),
    FieldSpec("cementer_p5_specialty_code",
              "Approved cementer's P-5 specialty code", "string",
              FieldSource.OPERATOR_INPUT, "cementer", required=False),

    # W-3A approval window (training deck p20)
    FieldSpec("w3a_issue_date", "Date the W-3A was issued/approved", "string",
              FieldSource.OPERATOR_INPUT, "approval", required=False,
              pattern=r"^\d{4}-\d{2}-\d{2}$"),
    FieldSpec("w3a_expiration_date", "Date the W-3A approval expires", "string",
              FieldSource.OPERATOR_INPUT, "approval", required=False,
              pattern=r"^\d{4}-\d{2}-\d{2}$"),

    # Certification of intent
    FieldSpec("operator_signature_name", "Name of operator representative",
              "string", FieldSource.OPERATOR_CERTIFICATION, "cert"),
    FieldSpec("operator_title", "Title of signing representative", "string",
              FieldSource.OPERATOR_CERTIFICATION, "cert"),
    FieldSpec("certification_date", "Date of operator certification", "string",
              FieldSource.OPERATOR_CERTIFICATION, "cert",
              pattern=r"^\d{4}-\d{2}-\d{2}$"),
)


def w3a_schema_by_name() -> dict[str, FieldSpec]:
    return {f.name: f for f in W3A_SCHEMA}


def w3a_schema_by_section() -> dict[str, list[FieldSpec]]:
    out: dict[str, list[FieldSpec]] = {}
    for f in W3A_SCHEMA:
        out.setdefault(f.rrc_section, []).append(f)
    return out


@dataclass
class W3AForm:
    """A populated (or partially populated) W-3A form."""
    # Box 1-11 — identity
    api_number: str | None = None
    operator_name: str | None = None
    operator_address: str | None = None
    operator_p5_number: str | None = None
    rrc_district: str | None = None
    county: str | None = None
    drilling_permit_no: str | None = None
    rule_37_case_no: str | None = None
    lease_number: str | None = None
    well_number: str | None = None
    field_name: str | None = None
    lease_name: str | None = None

    # Box 12 — location
    footage_ns: str | None = None
    footage_ew: str | None = None
    section_block_survey: str | None = None
    abstract_no: str | None = None
    location_description: str | None = None

    # Box 13/14 — type
    well_type: str | None = None
    completion_type: str | None = None

    # Box 15 — depth
    total_depth_ft: float | None = None

    # casing + perfs
    casing_record: list[dict[str, Any]] = field(default_factory=list)
    perforations: list[dict[str, Any]] = field(default_factory=list)

    # Box 16 — GAU
    buqw_depth_ft: float | None = None
    gau_letter_reference: str | None = None
    gau_letter_date: str | None = None

    # Box 17 — AOR
    aor_findings: list[dict[str, Any]] = field(default_factory=list)

    # historic plugs
    historic_plugs: list[dict[str, Any]] = field(default_factory=list)

    # proposed plug program (computed)
    proposed_plug_record: list[dict[str, Any]] = field(default_factory=list)
    plug_program_rule_paths: list[str] = field(default_factory=list)
    buqw_protected_by_surface_casing: bool | None = None

    # cementer
    cementing_company: str | None = None
    cementer_p5_specialty_code: str | None = None

    # approval window
    w3a_issue_date: str | None = None
    w3a_expiration_date: str | None = None

    # certification
    operator_signature_name: str | None = None
    operator_title: str | None = None
    certification_date: str | None = None

    def filled_fields(self) -> set[str]:
        out: set[str] = set()
        for spec in W3A_SCHEMA:
            v = getattr(self, spec.name, None)
            if v is None:
                continue
            if isinstance(v, list) and not v:
                continue
            out.add(spec.name)
        return out

    def missing_required(self) -> set[str]:
        filled = self.filled_fields()
        return {f.name for f in W3A_SCHEMA if f.required and f.name not in filled}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for spec in W3A_SCHEMA:
            v = getattr(self, spec.name)
            if v is None:
                continue
            if isinstance(v, list) and not v:
                continue
            out[spec.name] = v
        return out
