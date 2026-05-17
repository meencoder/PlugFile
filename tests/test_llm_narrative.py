"""Tests for Phase 2D — LLM fallback slot extractor.

All tests mock the Anthropic client so no real API calls are made.

Coverage:
  - Missing slots get filled from LLM tool response
  - Regex-filled slots are never overwritten by LLM
  - PLUGFILE_LLM_FALLBACK env var gates the LLM call in transcript_to_narrative
  - use_llm_fallback=True / False explicit param overrides the env var
  - Provenance is marked as "llm:<model_id>" for LLM-filled slots
  - equipment_removed is a union (no duplicates) not a replacement
  - RuntimeError raised and propagated when Anthropic API fails
  - ImportError raised when anthropic package not installed
  - No API call made when all slots are already filled
  - PLUGFILE_LLM_MODEL env var overrides the default model
"""

from __future__ import annotations

import copy
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from plugfile.narrative import (
    ExtractionWarning,
    SurfaceRestorationFacts,
    llm_fill_missing_slots,
    transcript_to_narrative,
    _LLM_SLOT_TOOL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool_response(slots: dict) -> MagicMock:
    """Build a minimal mock of an Anthropic Messages response with one
    tool_use content block.
    """
    tool_block = SimpleNamespace(
        type="tool_use",
        name="record_surface_restoration_slots",
        input=slots,
    )
    response = MagicMock()
    response.content = [tool_block]
    response.stop_reason = "tool_use"
    return response


def _base_facts(**kwargs) -> SurfaceRestorationFacts:
    """Return a mostly-empty facts object, optionally pre-filling some slots."""
    f = SurfaceRestorationFacts(**kwargs)
    return f


SIMPLE_TRANSCRIPT = (
    "We cut the casing at three feet below ground level and welded on "
    "a 24 inch by 24 inch by quarter inch steel plate. We filled the cellar "
    "with caliche. We removed the wellhead and pumping unit. "
    "We re-seeded native grass and graded the location. "
    "Work was completed on 2026-05-10."
)


# ---------------------------------------------------------------------------
# llm_fill_missing_slots — core behaviour
# ---------------------------------------------------------------------------

class TestLlmFillMissingSlots:

    def _call_with_mock(self, facts: SurfaceRestorationFacts,
                        transcript: str, llm_slots: dict,
                        model: str = "claude-haiku-3-5-20241022") -> SurfaceRestorationFacts:
        """Patch anthropic.Anthropic and invoke llm_fill_missing_slots."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response(llm_slots)
        with patch("anthropic.Anthropic", return_value=mock_client):
            return llm_fill_missing_slots(facts, transcript, model=model)

    def test_missing_slots_filled_from_llm(self):
        """LLM provides casing_cut_depth_ft and vegetation_action — both land."""
        facts = _base_facts()
        llm_slots = {
            "casing_cut_depth_ft": 3.0,
            "cap_type": None,
            "cap_dimensions": None,
            "cellar_filled": None,
            "cellar_fill_material": None,
            "equipment_removed": None,
            "vegetation_action": "re-seeded native grass",
            "grading_action": None,
            "access_road_status": None,
            "fencing_status": None,
            "date_of_work": None,
            "surface_owner_consent": None,
            "sensitive_surface_notes": None,
        }
        result = self._call_with_mock(facts, "cut at 3 ft, re-seeded", llm_slots)
        assert result.casing_cut_depth_ft == 3.0
        assert result.vegetation_action == "re-seeded native grass"

    def test_regex_filled_slots_not_overwritten(self):
        """Regex already set cap_type; LLM provides a different value — ignored."""
        facts = _base_facts(cap_type="steel plate")
        facts.provenance["cap_type"] = "welded on a steel plate"  # regex provenance

        llm_slots = {
            "casing_cut_depth_ft": None,
            "cap_type": "concrete cap",   # LLM disagrees — should be ignored
            "cap_dimensions": None,
            "cellar_filled": None,
            "cellar_fill_material": None,
            "equipment_removed": None,
            "vegetation_action": None,
            "grading_action": None,
            "access_road_status": None,
            "fencing_status": None,
            "date_of_work": "2026-05-10",
            "surface_owner_consent": None,
            "sensitive_surface_notes": None,
        }
        result = self._call_with_mock(facts, "welded on a steel plate", llm_slots)
        # cap_type must be the regex value, not LLM value
        assert result.cap_type == "steel plate"
        assert result.provenance["cap_type"] == "welded on a steel plate"
        # date_of_work was missing — LLM should have filled it
        assert result.date_of_work == "2026-05-10"

    def test_provenance_marked_as_llm_model_id(self):
        """Slots filled by LLM have provenance string 'llm:<model_id>'."""
        facts = _base_facts()
        model = "claude-haiku-3-5-20241022"
        llm_slots = {
            "casing_cut_depth_ft": 3.0,
            **{k: None for k in [
                "cap_type", "cap_dimensions", "cellar_filled",
                "cellar_fill_material", "equipment_removed",
                "vegetation_action", "grading_action", "access_road_status",
                "fencing_status", "date_of_work", "surface_owner_consent",
                "sensitive_surface_notes",
            ]},
        }
        result = self._call_with_mock(facts, "cut at 3 ft", llm_slots, model=model)
        assert result.provenance["casing_cut_depth_ft"] == f"llm:{model}"

    def test_equipment_removed_filled_by_llm_when_regex_found_nothing(self):
        """Regex found no equipment; LLM provides items — they are added (sorted, deduped)."""
        facts = _base_facts()  # equipment_removed = []

        llm_slots = {
            **{k: None for k in [
                "casing_cut_depth_ft", "cap_type", "cap_dimensions",
                "cellar_filled", "cellar_fill_material",
                "vegetation_action", "grading_action", "access_road_status",
                "fencing_status", "date_of_work", "surface_owner_consent",
                "sensitive_surface_notes",
            ]},
            "equipment_removed": ["wellhead", "pumping unit", "wellhead"],  # dupes
        }
        result = self._call_with_mock(facts, "removed wellhead and pumping unit", llm_slots)
        # Sorted and deduplicated
        assert result.equipment_removed == ["pumping unit", "wellhead"]
        assert result.provenance.get("equipment_removed", "").startswith("llm:")

    def test_equipment_not_overwritten_when_regex_found_items(self):
        """Regex already found equipment — LLM items should NOT be added."""
        facts = _base_facts(equipment_removed=["separator"])
        facts.provenance["equipment_removed"] = "separator"

        llm_slots = {
            **{k: None for k in [
                "casing_cut_depth_ft", "cap_type", "cap_dimensions",
                "cellar_filled", "cellar_fill_material",
                "vegetation_action", "grading_action", "access_road_status",
                "fencing_status", "date_of_work", "surface_owner_consent",
                "sensitive_surface_notes",
            ]},
            "equipment_removed": ["compressor"],
        }
        result = self._call_with_mock(facts, "removed separator", llm_slots)
        # equipment_removed was already filled by regex → no LLM merge
        assert result.equipment_removed == ["separator"]

    def test_no_api_call_when_all_slots_filled(self):
        """When every slot is already filled, no Anthropic call should be made."""
        facts = SurfaceRestorationFacts(
            casing_cut_depth_ft=3.0,
            cap_type="steel plate",
            cap_dimensions="24 x 24 x 0.25 inch",
            cellar_filled=True,
            cellar_fill_material="caliche",
            equipment_removed=["wellhead"],
            vegetation_action="re-seeded",
            grading_action="graded",
            access_road_status="removed",
            fencing_status="removed",
            date_of_work="2026-05-10",
            surface_owner_consent="granted",
            sensitive_surface_notes="none noted",  # must be non-None to be "filled"
        )
        for slot in facts.filled_slots():
            facts.provenance[slot] = "regex"

        mock_client = MagicMock()
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = llm_fill_missing_slots(facts, "transcript text")

        mock_client.messages.create.assert_not_called()
        # Result is the same object returned early
        assert result is facts

    def test_model_override_via_env_var(self):
        """PLUGFILE_LLM_MODEL env var overrides the default model."""
        facts = _base_facts()
        custom_model = "claude-3-opus-20240229"
        llm_slots = {k: None for k in [
            "casing_cut_depth_ft", "cap_type", "cap_dimensions",
            "cellar_filled", "cellar_fill_material", "equipment_removed",
            "vegetation_action", "grading_action", "access_road_status",
            "fencing_status", "date_of_work", "surface_owner_consent",
            "sensitive_surface_notes",
        ]}
        llm_slots["date_of_work"] = "2026-05-10"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response(llm_slots)
        with patch("anthropic.Anthropic", return_value=mock_client), \
             patch.dict(os.environ, {"PLUGFILE_LLM_MODEL": custom_model}):
            result = llm_fill_missing_slots(facts, "transcript text")

        # Verify the model used in the API call
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == custom_model
        # Provenance should use the env-var model
        assert result.provenance.get("date_of_work") == f"llm:{custom_model}"

    def test_api_failure_raises_runtime_error(self):
        """If Anthropic API raises, a RuntimeError is propagated."""
        facts = _base_facts()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("network error")
        with patch("anthropic.Anthropic", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Anthropic API call failed"):
                llm_fill_missing_slots(facts, "some transcript")

    def test_import_error_when_anthropic_not_installed(self):
        """ImportError is raised if anthropic package is absent."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("No module named 'anthropic'")
            return real_import(name, *args, **kwargs)

        facts = _base_facts()
        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError, match="anthropic package is required"):
                llm_fill_missing_slots(facts, "some transcript")

    def test_missing_tool_use_block_raises_runtime_error(self):
        """If the LLM response contains no tool_use block, RuntimeError is raised."""
        facts = _base_facts()
        # Response with only a text block
        text_block = SimpleNamespace(type="text", text="Sorry, I cannot help.")
        response = MagicMock()
        response.content = [text_block]
        response.stop_reason = "end_turn"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = response
        with patch("anthropic.Anthropic", return_value=mock_client):
            with pytest.raises(RuntimeError, match="did not call the expected tool"):
                llm_fill_missing_slots(facts, "some transcript")

    def test_original_facts_not_mutated(self):
        """llm_fill_missing_slots must return a new object — never mutate input."""
        facts = _base_facts(cap_type="steel plate")
        facts.provenance["cap_type"] = "regex"
        original_id = id(facts)

        llm_slots = {
            "casing_cut_depth_ft": 3.0,
            **{k: None for k in [
                "cap_type", "cap_dimensions", "cellar_filled",
                "cellar_fill_material", "equipment_removed",
                "vegetation_action", "grading_action", "access_road_status",
                "fencing_status", "date_of_work", "surface_owner_consent",
                "sensitive_surface_notes",
            ]},
        }
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response(llm_slots)
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = llm_fill_missing_slots(facts, "cut at 3 ft")

        assert id(result) != original_id
        assert facts.casing_cut_depth_ft is None  # original unchanged


# ---------------------------------------------------------------------------
# transcript_to_narrative — env var and param flag wiring
# ---------------------------------------------------------------------------

class TestTranscriptToNarrativeFlag:

    def _patched_narrative(self, transcript: str, env: dict | None = None, **kwargs):
        """Run transcript_to_narrative with a mocked LLM that fills date_of_work."""
        llm_slots = {
            "casing_cut_depth_ft": None,
            "cap_type": None,
            "cap_dimensions": None,
            "cellar_filled": None,
            "cellar_fill_material": None,
            "equipment_removed": None,
            "vegetation_action": None,
            "grading_action": None,
            "access_road_status": None,
            "fencing_status": None,
            "date_of_work": "2026-05-10",
            "surface_owner_consent": None,
            "sensitive_surface_notes": None,
        }
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response(llm_slots)

        environ_patch = env or {}
        with patch("anthropic.Anthropic", return_value=mock_client), \
             patch.dict(os.environ, environ_patch, clear=False):
            result = transcript_to_narrative(transcript, **kwargs)
        return result, mock_client

    def test_env_var_disabled_by_default_no_api_call(self):
        """With no env var set and no explicit flag, LLM is never called."""
        env = {k: "" for k in ["PLUGFILE_LLM_FALLBACK"]}  # ensure unset
        _, mock_client = self._patched_narrative(
            "cut casing at 3 ft", env=env
        )
        mock_client.messages.create.assert_not_called()

    def test_env_var_true_triggers_api_call(self):
        """PLUGFILE_LLM_FALLBACK=true → LLM is called."""
        _, mock_client = self._patched_narrative(
            "cut casing at 3 ft",
            env={"PLUGFILE_LLM_FALLBACK": "true"},
        )
        mock_client.messages.create.assert_called_once()

    def test_env_var_1_triggers_api_call(self):
        """PLUGFILE_LLM_FALLBACK=1 → LLM is called."""
        _, mock_client = self._patched_narrative(
            "cut casing at 3 ft",
            env={"PLUGFILE_LLM_FALLBACK": "1"},
        )
        mock_client.messages.create.assert_called_once()

    def test_env_var_yes_triggers_api_call(self):
        """PLUGFILE_LLM_FALLBACK=yes → LLM is called."""
        _, mock_client = self._patched_narrative(
            "cut casing at 3 ft",
            env={"PLUGFILE_LLM_FALLBACK": "yes"},
        )
        mock_client.messages.create.assert_called_once()

    def test_explicit_true_overrides_missing_env_var(self):
        """use_llm_fallback=True → LLM called even without env var."""
        env = {"PLUGFILE_LLM_FALLBACK": ""}
        _, mock_client = self._patched_narrative(
            "cut casing at 3 ft",
            env=env,
            use_llm_fallback=True,
        )
        mock_client.messages.create.assert_called_once()

    def test_explicit_false_overrides_set_env_var(self):
        """use_llm_fallback=False → LLM NOT called even if env var is true."""
        _, mock_client = self._patched_narrative(
            "cut casing at 3 ft",
            env={"PLUGFILE_LLM_FALLBACK": "true"},
            use_llm_fallback=False,
        )
        mock_client.messages.create.assert_not_called()

    def test_llm_filled_slots_appear_in_returned_facts(self):
        """Slots that the LLM fills end up in the returned facts object."""
        (narrative, facts, warnings), _ = self._patched_narrative(
            "cut casing at 3 ft",
            use_llm_fallback=True,
        )
        # The mock fills date_of_work = "2026-05-10"
        assert facts.date_of_work == "2026-05-10"
        assert facts.provenance.get("date_of_work", "").startswith("llm:")

    def test_narrative_reflects_llm_date(self):
        """LLM-supplied date_of_work appears in the final narrative string."""
        (narrative, facts, _), _ = self._patched_narrative(
            "cut casing at 3 ft",
            use_llm_fallback=True,
        )
        assert "2026-05-10" in narrative

    def test_env_var_case_insensitive(self):
        """PLUGFILE_LLM_FALLBACK=TRUE (upper-case) also triggers LLM."""
        _, mock_client = self._patched_narrative(
            "cut casing at 3 ft",
            env={"PLUGFILE_LLM_FALLBACK": "TRUE"},
        )
        mock_client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# _LLM_SLOT_TOOL schema integrity
# ---------------------------------------------------------------------------

class TestLlmSlotToolSchema:

    def test_tool_name_matches_expected(self):
        assert _LLM_SLOT_TOOL["name"] == "record_surface_restoration_slots"

    def test_all_fact_slots_present_in_schema(self):
        """Every field of SurfaceRestorationFacts (except provenance) is in the schema."""
        expected_slots = {
            "casing_cut_depth_ft", "cap_type", "cap_dimensions",
            "cellar_filled", "cellar_fill_material", "equipment_removed",
            "vegetation_action", "grading_action", "access_road_status",
            "fencing_status", "date_of_work", "surface_owner_consent",
            "sensitive_surface_notes",
        }
        schema_props = set(_LLM_SLOT_TOOL["input_schema"]["properties"].keys())
        assert expected_slots == schema_props

    def test_no_required_fields_in_schema(self):
        """All fields are optional so Claude can return null for anything."""
        assert _LLM_SLOT_TOOL["input_schema"].get("required", []) == []

    def test_equipment_removed_is_array_type(self):
        ep = _LLM_SLOT_TOOL["input_schema"]["properties"]["equipment_removed"]
        assert "array" in ep["type"]
        assert ep["items"]["type"] == "string"
