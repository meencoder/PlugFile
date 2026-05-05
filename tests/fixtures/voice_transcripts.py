"""Eight golden voice transcripts for the surface-restoration drafter.

Each transcript represents a real-style operator dictation (filler words,
contractions, occasional self-correction). The fixture also lists the
phrases the drafted narrative MUST contain when the extractor is run, plus
which slots SHOULD have been filled by the regex layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GoldenTranscript:
    name: str
    api_number: str | None
    transcript: str
    expected_filled_slots: set[str] = field(default_factory=set)
    expected_narrative_contains: list[str] = field(default_factory=list)
    expected_warnings_for_slots: set[str] = field(default_factory=set)


PERMIAN_MODERN_FULL = GoldenTranscript(
    name="permian_modern_full",
    api_number="42-371-30001",
    transcript=(
        "Alright, this is the Heritage A number 1H, API 42-371-30001. "
        "We finished plugging operations and then on May 4th 2026 we cut "
        "the surface casing down about 3 feet below ground level, then we "
        "welded a 24 inch by 24 inch by 1/4 inch steel plate on top to "
        "cap the wellbore. We backfilled the cellar with native soil. "
        "Wellhead and tubing string were removed earlier in the week. "
        "Location was re-graded and the disturbed area was re-seeded with "
        "native grass. Access road was retained per the surface owner. "
        "Surface owner consent on file."
    ),
    expected_filled_slots={
        "casing_cut_depth_ft", "cap_type", "cap_dimensions",
        "cellar_filled", "cellar_fill_material",
        "equipment_removed", "vegetation_action", "grading_action",
        "access_road_status", "surface_owner_consent", "date_of_work",
    },
    expected_narrative_contains=[
        "API 42-371-30001",
        "Heritage A #1H",
        "3 feet below ground level",
        "steel plate",
        "native soil",
        "Wellhead",
        "Tubing string",
        "re seeded",
        "Access road: retained per surface owner.",
        "2026-05-04",
    ],
)


EAST_TEXAS_LEGACY_PARTIAL = GoldenTranscript(
    name="east_texas_legacy_partial",
    api_number="42-401-12345",
    transcript=(
        "OK so this is the Whitfield #3 in Rusk County. Plugged it on "
        "April 22nd 2026. Cut the casing off at 3 feet, welded on a "
        "1/4 inch steel cap. Filled the cellar with caliche we had on "
        "site. Wellhead came off, but per the surface owner we left the "
        "tank battery and the flowlines in place because they're using "
        "them on the next well. Location was leveled. Surface owner "
        "declined any vegetation work. Fence was repaired where the rig "
        "tore it up. Surface owner permission on file for leaving "
        "equipment."
    ),
    expected_filled_slots={
        "casing_cut_depth_ft", "cap_type",
        "cellar_filled", "cellar_fill_material",
        "equipment_removed", "grading_action",
        "fencing_status", "surface_owner_consent", "date_of_work",
    },
    expected_narrative_contains=[
        "Whitfield #3",
        "3 feet",
        "steel",
        "caliche",
        "Wellhead",
        "leveled",
        "Fencing: repaired",
        "2026-04-22",
    ],
    expected_warnings_for_slots={"vegetation_action"},
)


URBAN_PAVED = GoldenTranscript(
    name="urban_paved",
    api_number=None,
    transcript=(
        "We've got the orphan well downtown. Cut the casing 4 feet below "
        "the existing concrete pavement. Set a concrete cap on top. Did "
        "not fill any cellar - this thing's been paved over for decades. "
        "No equipment on the lot. No vegetation done because it's all "
        "asphalt. Restored grade to match the adjacent pavement. Date of "
        "work was 2026-03-18."
    ),
    expected_filled_slots={
        "casing_cut_depth_ft", "cap_type", "grading_action", "date_of_work",
    },
    expected_narrative_contains=[
        "4 feet",
        "concrete",
        "restored grade",
        "2026-03-18",
    ],
    expected_warnings_for_slots={"vegetation_action"},
)


MULTI_WELL_LEASE = GoldenTranscript(
    name="multi_well_lease",
    api_number="42-329-55555",
    transcript=(
        "Spraberry Ranch #7. The other wells on this lease are still "
        "producing so we kept the access road and the tank battery in "
        "place - they're shared. On 2026-05-01 we cut the production "
        "casing 3 feet below grade and welded a 24 by 24 by quarter inch "
        "steel plate. Cellar filled with caliche. Pulled the wellhead, "
        "tubing string, and rod string. Pumping unit was removed and "
        "hauled off to the yard. Re-seeded with native grass. Re-graded "
        "the disturbed pad. Access road was retained. Surface owner "
        "approval received."
    ),
    expected_filled_slots={
        "casing_cut_depth_ft", "cap_type", "cap_dimensions",
        "cellar_filled", "cellar_fill_material",
        "equipment_removed", "vegetation_action", "grading_action",
        "access_road_status", "surface_owner_consent", "date_of_work",
    },
    expected_narrative_contains=[
        "Spraberry Ranch #7",
        "3 feet",
        "steel plate",
        "caliche",
        "Wellhead",
        "Tubing string",
        "Rod string",
        "Pumping unit",
        "Access road: retained per surface owner.",
        "2026-05-01",
    ],
)


DRY_HOLE_MINIMAL = GoldenTranscript(
    name="dry_hole_minimal",
    api_number=None,
    transcript=(
        "Dry hole, P&A'd same day as TD reached on 2026-02-09. Never "
        "produced. Cut the casing 3 feet below ground, welded on a steel "
        "plate cap. No cellar - this was a single string completion. "
        "Re-graded the pad. Re-seeded the disturbed area with the "
        "wildflower mix per the surface owner request. Access road "
        "removed. Fence was removed."
    ),
    expected_filled_slots={
        "casing_cut_depth_ft", "cap_type",
        "vegetation_action", "grading_action",
        "access_road_status", "fencing_status", "date_of_work",
    },
    expected_narrative_contains=[
        "3 feet",
        "steel",
        "re graded",
        "Access road: removed.",
        "Fencing: removed.",
        "2026-02-09",
    ],
)


TANK_BATTERY_SCOPE = GoldenTranscript(
    name="tank_battery_scope",
    api_number=None,
    transcript=(
        "Big project on this one. We removed the wellhead, the tubing "
        "string, the rod string, the pumping unit, the separator, the "
        "heater treater, the entire tank battery, and all the flowlines. "
        "Hauled it all off. Cut the casing 3 feet below ground, welded on "
        "a 1/4 inch steel plate. Filled the cellar with native soil. "
        "Re-graded the pad. Re-seeded with native grass. Access road was "
        "removed. Fence retained per surface owner. Date 2026-04-15."
    ),
    expected_filled_slots={
        "casing_cut_depth_ft", "cap_type",
        "cellar_filled", "cellar_fill_material",
        "equipment_removed", "vegetation_action", "grading_action",
        "access_road_status", "fencing_status", "date_of_work",
    },
    expected_narrative_contains=[
        "Wellhead",
        "Tubing string",
        "Rod string",
        "Pumping unit",
        "Separator",
        "Heater treater",
        "Tank battery",
        "Flowlines",
        "2026-04-15",
    ],
)


SENSITIVE_SURFACE = GoldenTranscript(
    name="sensitive_surface",
    api_number=None,
    transcript=(
        "This well is adjacent to a wetlands area so we coordinated with "
        "Texas Parks and Wildlife. Did the work on 2026-04-30. Cut casing "
        "3 feet below grade, welded a steel plate cap on top. No cellar "
        "fill needed - it had already been graded out. Re-seeded with the "
        "approved native riparian seed mix. Access road removed. Fence "
        "retained. Surface owner consent granted with environmental "
        "conditions documented separately."
    ),
    expected_filled_slots={
        "casing_cut_depth_ft", "cap_type",
        "vegetation_action",
        "access_road_status", "fencing_status",
        "surface_owner_consent", "sensitive_surface_notes",
        "date_of_work",
    },
    expected_narrative_contains=[
        "wetlands",
        "3 feet",
        "steel",
        "Access road: removed.",
        "Fencing: retained.",
        "2026-04-30",
    ],
)


ESTATE_LEGACY_WELL = GoldenTranscript(
    name="estate_legacy_well",
    api_number="42-461-00042",
    transcript=(
        "Hardin Heirs A-1 in Throckmorton. This is one of the orphan "
        "wells we picked up. Plugged on 2026-03-25. Cut surface casing "
        "3 feet below ground level. Welded a 24 by 24 by quarter inch "
        "steel plate. Cellar was filled with native soil. Wellhead "
        "removed. No tank battery - it was scrapped years ago. Re-graded "
        "what we could. Re-seeded with native grass. Access road was "
        "abandoned, the surface owner moved away. Fence was removed - "
        "what little was left of it."
    ),
    expected_filled_slots={
        "casing_cut_depth_ft", "cap_type", "cap_dimensions",
        "cellar_filled", "cellar_fill_material",
        "equipment_removed", "vegetation_action", "grading_action",
        "access_road_status", "fencing_status", "date_of_work",
    },
    expected_narrative_contains=[
        "Hardin Heirs #A-1",
        "3 feet",
        "steel plate",
        "Wellhead",
        "Fencing: removed.",
        "2026-03-25",
    ],
)


ALL_TRANSCRIPTS: list[GoldenTranscript] = [
    PERMIAN_MODERN_FULL,
    EAST_TEXAS_LEGACY_PARTIAL,
    URBAN_PAVED,
    MULTI_WELL_LEASE,
    DRY_HOLE_MINIMAL,
    TANK_BATTERY_SCOPE,
    SENSITIVE_SURFACE,
    ESTATE_LEGACY_WELL,
]
