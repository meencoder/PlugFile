"""Tests for the slot extractor in wellplug.narrative."""

from __future__ import annotations

import pytest

from wellplug.narrative import (
    ExtractionWarning,
    extract_facts_from_transcript,
)
from tests.fixtures.voice_transcripts import ALL_TRANSCRIPTS


# ---- per-fixture extraction smoke tests ----------------------------------

@pytest.mark.parametrize("fx", ALL_TRANSCRIPTS, ids=lambda fx: fx.name)
def test_extracted_slots_match_expectation(fx) -> None:
    facts, _warnings = extract_facts_from_transcript(fx.transcript)
    filled = facts.filled_slots()
    missing = fx.expected_filled_slots - filled
    extra = filled - fx.expected_filled_slots
    assert not missing, (
        f"{fx.name}: extractor missed expected slots: {sorted(missing)}; "
        f"got {sorted(filled)}"
    )
    # Extras are okay; the regex layer is permitted to surface bonus slots.


# ---- targeted slot-by-slot tests -----------------------------------------

def test_casing_cut_depth_extraction_basic() -> None:
    facts, _ = extract_facts_from_transcript(
        "We cut the casing about 3 feet below ground level."
    )
    assert facts.casing_cut_depth_ft == 3.0


def test_casing_cut_depth_extraction_with_decimal() -> None:
    facts, _ = extract_facts_from_transcript(
        "Cut the surface casing 4.5 feet down."
    )
    assert facts.casing_cut_depth_ft == 4.5


def test_cap_extraction_with_dimensions() -> None:
    facts, _ = extract_facts_from_transcript(
        "Welded a 24 inch by 24 inch by 1/4 inch steel plate on top."
    )
    assert facts.cap_type == "steel plate"
    assert facts.cap_dimensions is not None
    assert "24" in facts.cap_dimensions


def test_cellar_extraction_with_material() -> None:
    facts, _ = extract_facts_from_transcript(
        "Filled the cellar with caliche."
    )
    assert facts.cellar_filled is True
    assert facts.cellar_fill_material == "caliche"


def test_cellar_extraction_without_material() -> None:
    """If material isn't named, cellar_filled is True but material is None."""
    facts, _ = extract_facts_from_transcript("Filled the cellar.")
    assert facts.cellar_filled is True
    assert facts.cellar_fill_material is None


def test_equipment_removal_canonicalizes_synonyms() -> None:
    facts, _ = extract_facts_from_transcript(
        "Removed the Christmas tree, the tubing, and the pumping unit."
    )
    assert "wellhead" in facts.equipment_removed
    assert "tubing string" in facts.equipment_removed
    assert "pumping unit" in facts.equipment_removed


def test_equipment_only_counted_under_remove_context() -> None:
    """Equipment names mentioned without a 'remove' context shouldn't count."""
    facts, _ = extract_facts_from_transcript(
        "The wellhead and tubing are still in place; we'll come back later."
    )
    # No "removed" verb anywhere -> no equipment removed
    assert facts.equipment_removed == []


def test_vegetation_extraction() -> None:
    facts, _ = extract_facts_from_transcript(
        "Re-seeded with native grass."
    )
    assert facts.vegetation_action is not None
    assert "seed" in facts.vegetation_action


def test_grading_extraction() -> None:
    facts, _ = extract_facts_from_transcript(
        "Re-graded the location and contoured to drain."
    )
    assert facts.grading_action is not None


def test_access_road_removed() -> None:
    facts, _ = extract_facts_from_transcript("Access road was removed.")
    assert facts.access_road_status == "removed"


def test_access_road_retained() -> None:
    facts, _ = extract_facts_from_transcript(
        "Access road was retained per the surface owner."
    )
    assert facts.access_road_status == "retained per surface owner"


def test_fencing_repaired() -> None:
    facts, _ = extract_facts_from_transcript(
        "Fence was repaired where the rig tore it up."
    )
    assert facts.fencing_status == "repaired"


def test_surface_owner_consent_phrasing() -> None:
    for phrase in (
        "surface owner consent on file",
        "surface owner permission granted",
        "Surface owner approval received",
    ):
        facts, _ = extract_facts_from_transcript(phrase)
        assert facts.surface_owner_consent is not None


def test_sensitive_surface_wetlands() -> None:
    facts, _ = extract_facts_from_transcript(
        "The location is adjacent to a wetlands area."
    )
    assert facts.sensitive_surface_notes == "wetlands"


def test_iso_date_extraction() -> None:
    facts, _ = extract_facts_from_transcript("Work performed on 2026-05-04.")
    assert facts.date_of_work == "2026-05-04"


def test_natural_date_with_year() -> None:
    facts, _ = extract_facts_from_transcript("Work was completed May 4th 2026.")
    assert facts.date_of_work == "2026-05-04"


def test_natural_date_without_year_warns() -> None:
    facts, warnings = extract_facts_from_transcript(
        "Work performed April 22nd, with the casing cut at 3 feet."
    )
    # No year in transcript, no fallback -> warning fires
    assert facts.date_of_work is None
    assert any(w.slot == "date_of_work" and w.severity == "warn"
               for w in warnings)


def test_natural_date_with_fallback_year() -> None:
    facts, _ = extract_facts_from_transcript(
        "Work performed April 22nd.", fallback_year=2026,
    )
    assert facts.date_of_work == "2026-04-22"


# ---- warning behavior ----------------------------------------------------


def test_required_slots_not_filled_emit_warnings() -> None:
    """If a required slot is missing, an extraction warning fires."""
    facts, warnings = extract_facts_from_transcript(
        "We did some stuff. It was great."
    )
    flagged = {w.slot for w in warnings if w.severity == "warn"}
    # All these are 'required' for narrative completeness
    assert {"casing_cut_depth_ft", "cap_type",
            "vegetation_action", "grading_action",
            "date_of_work"}.issubset(flagged)


def test_provenance_records_matched_text() -> None:
    facts, _ = extract_facts_from_transcript(
        "Cut the casing 3 feet down. Welded a steel plate."
    )
    assert "casing_cut_depth_ft" in facts.provenance
    assert "casing" in facts.provenance["casing_cut_depth_ft"].lower()


def test_extraction_warning_renders() -> None:
    w = ExtractionWarning(slot="cap_type", severity="warn", message="missing")
    rendered = w.render()
    assert "WARN" in rendered
    assert "cap_type" in rendered
    assert "missing" in rendered
