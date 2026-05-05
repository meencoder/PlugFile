"""Tests for the narrative drafter and end-to-end transcript pipeline."""

from __future__ import annotations

import pytest

from wellplug.narrative import (
    SurfaceRestorationFacts,
    draft_narrative,
    transcript_to_narrative,
)
from tests.fixtures.voice_transcripts import ALL_TRANSCRIPTS


# Pull MockFetcher-style well context so the narrative opener has API +
# lease. Avoids depending on the real fetcher in narrative tests.
_WELL_CONTEXTS = {
    "42-371-30001": {"api_number": "42-371-30001", "lease_name": "Heritage A",
                     "well_number": "1H", "county": "Pecos"},
    "42-401-12345": {"api_number": "42-401-12345", "lease_name": "Whitfield",
                     "well_number": "3", "county": "Rusk"},
    "42-329-55555": {"api_number": "42-329-55555", "lease_name": "Spraberry Ranch",
                     "well_number": "7", "county": "Midland"},
    "42-461-00042": {"api_number": "42-461-00042", "lease_name": "Hardin Heirs",
                     "well_number": "A-1", "county": "Throckmorton"},
}


# ---- golden-phrase verification -----------------------------------------

@pytest.mark.parametrize("fx", ALL_TRANSCRIPTS, ids=lambda fx: fx.name)
def test_drafted_narrative_contains_expected_phrases(fx) -> None:
    ctx = _WELL_CONTEXTS.get(fx.api_number) if fx.api_number else None
    narrative, _facts, _warnings = transcript_to_narrative(
        fx.transcript, well_context=ctx,
    )
    for phrase in fx.expected_narrative_contains:
        assert phrase in narrative, (
            f"{fx.name}: expected phrase {phrase!r} not in narrative:\n"
            f"{narrative}"
        )


# ---- warning expectations ------------------------------------------------

@pytest.mark.parametrize("fx", ALL_TRANSCRIPTS, ids=lambda fx: fx.name)
def test_expected_warnings_fire(fx) -> None:
    if not fx.expected_warnings_for_slots:
        return
    _narrative, _facts, warnings = transcript_to_narrative(fx.transcript)
    flagged_slots = {w.slot for w in warnings}
    for slot in fx.expected_warnings_for_slots:
        assert slot in flagged_slots, (
            f"{fx.name}: expected a warning on slot {slot!r}; got "
            f"{sorted(flagged_slots)}"
        )


# ---- drafter behavior on raw facts --------------------------------------


def test_drafter_uses_full_well_context_in_opener() -> None:
    facts = SurfaceRestorationFacts(
        casing_cut_depth_ft=3.0, cap_type="steel plate",
        date_of_work="2026-05-04",
    )
    ctx = {"api_number": "42-371-30001", "lease_name": "Heritage A",
           "well_number": "1H", "county": "Pecos"}
    narrative, _ = draft_narrative(facts, well_context=ctx)
    assert "API 42-371-30001" in narrative
    assert "Heritage A #1H" in narrative
    assert "Pecos County" in narrative


def test_drafter_handles_no_well_context() -> None:
    facts = SurfaceRestorationFacts(
        casing_cut_depth_ft=3.0, cap_type="steel plate",
        date_of_work="2026-05-04",
    )
    narrative, _ = draft_narrative(facts)
    assert "Surface casing was cut" in narrative
    assert "2026-05-04" in narrative


def test_drafter_inserts_placeholders_for_missing_slots() -> None:
    facts = SurfaceRestorationFacts()  # nothing filled
    narrative, warnings = draft_narrative(facts)
    assert "[" in narrative and "not stated]" in narrative
    flagged = {w.slot for w in warnings}
    assert "casing_cut_depth_ft" in flagged
    assert "cap_type" in flagged
    assert "date_of_work" in flagged


def test_drafter_omits_optional_sections_when_empty() -> None:
    """If equipment_removed / cellar_filled / fencing aren't set, those
    sentences should NOT appear in the narrative."""
    facts = SurfaceRestorationFacts(
        casing_cut_depth_ft=3.0, cap_type="steel plate",
        grading_action="leveled", vegetation_action="re seeded",
        date_of_work="2026-05-04",
    )
    narrative, _ = draft_narrative(facts)
    assert "cellar" not in narrative.lower()
    assert "removed" not in narrative.lower()  # no equipment phrase
    assert "Fencing" not in narrative


def test_equipment_phrase_grammar_for_one_two_many() -> None:
    """Joiner words shift correctly between 1 / 2 / 3+ items."""
    one = SurfaceRestorationFacts(equipment_removed=["wellhead"])
    n1, _ = draft_narrative(one)
    assert "Wellhead" in n1 and "and" not in n1.split("Wellhead")[1].split(".")[0]

    two = SurfaceRestorationFacts(equipment_removed=["wellhead", "tubing string"])
    n2, _ = draft_narrative(two)
    assert "Wellhead and Tubing string" in n2

    three = SurfaceRestorationFacts(
        equipment_removed=["wellhead", "tubing string", "pumping unit"],
    )
    n3, _ = draft_narrative(three)
    assert "Wellhead, Tubing string, and Pumping unit" in n3


def test_sensitive_surface_appears_in_narrative() -> None:
    facts = SurfaceRestorationFacts(
        casing_cut_depth_ft=3.0, cap_type="steel plate",
        date_of_work="2026-05-04",
        sensitive_surface_notes="wetlands",
    )
    narrative, _ = draft_narrative(facts)
    assert "wetlands" in narrative
    assert "regulatory restrictions" in narrative


def test_pipeline_returns_warnings_union() -> None:
    """transcript_to_narrative returns warnings from BOTH the extractor
    and the drafter, deduped."""
    transcript = "Some words about casing 3 feet."  # very sparse
    _narrative, _facts, warnings = transcript_to_narrative(transcript)
    assert any(w.slot == "cap_type" for w in warnings)
    assert any(w.slot == "date_of_work" for w in warnings)


def test_pipeline_is_deterministic() -> None:
    fx = ALL_TRANSCRIPTS[0]
    a = transcript_to_narrative(fx.transcript)
    b = transcript_to_narrative(fx.transcript)
    assert a[0] == b[0]
    assert a[1] == b[1]
    # Warning order may differ but content must match
    assert {(w.slot, w.severity, w.message) for w in a[2]} == \
           {(w.slot, w.severity, w.message) for w in b[2]}
