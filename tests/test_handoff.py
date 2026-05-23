"""Tests for the operator ↔ plugging-company handoff state machine (handoff.py)."""

from __future__ import annotations

import json

import pytest

from plugfile.handoff import (
    ROLE_OPERATOR,
    ROLE_PLUGGING,
    ROLE_RRC,
    VALID_STAGES,
    WORKFLOW,
    HandoffStage,
    HandoffState,
    build_handoff_with_mock,
    evaluate_handoff,
)

API = "42-371-30001"

# All four required docs present (w3 needs gau + l1 + p13; w15 not required).
_ALL_DOCS = dict(
    has_gau_letter=True,
    has_l1_well_log=True,
    has_p13_affidavit=True,
    has_w15_plugging_permit=True,
)


# ── workflow shape ────────────────────────────────────────────────────────────

def test_workflow_has_five_ordered_stages():
    assert len(WORKFLOW) == 5
    assert [s.stage for s in WORKFLOW] == list(VALID_STAGES)


def test_workflow_roles_follow_rrc_pattern():
    roles = [s.holder_role for s in WORKFLOW]
    assert roles == [
        ROLE_OPERATOR, ROLE_PLUGGING, ROLE_OPERATOR, ROLE_RRC, ROLE_RRC,
    ]


def test_unknown_stage_raises():
    with pytest.raises(ValueError, match="Unknown handoff stage"):
        evaluate_handoff("bogus")


# ── draft stage ───────────────────────────────────────────────────────────────

def test_draft_held_by_operator_and_can_advance():
    s = evaluate_handoff(HandoffStage.DRAFT.value)
    assert isinstance(s, HandoffState)
    assert s.holder_role == ROLE_OPERATOR
    assert s.can_advance            # a draft can always go to the plugging co.
    assert s.next_action == "Send to plugging company"
    assert s.next_holder_role == ROLE_PLUGGING
    assert s.blocking == []


# ── plugging-company review gating ────────────────────────────────────────────

def test_plugging_review_blocked_without_details():
    s = evaluate_handoff(
        HandoffStage.PLUGGING_REVIEW.value, **_ALL_DOCS,
        has_plugging_details=False,
    )
    assert not s.can_advance
    assert any("plug placements" in b for b in s.blocking)


def test_plugging_review_blocked_without_attachments():
    s = evaluate_handoff(
        HandoffStage.PLUGGING_REVIEW.value,
        has_plugging_details=True,
        has_gau_letter=False, has_l1_well_log=False, has_p13_affidavit=False,
    )
    assert not s.can_advance
    assert not s.attachments_ready
    assert any("attachments" in b for b in s.blocking)


def test_plugging_review_advances_when_ready():
    s = evaluate_handoff(
        HandoffStage.PLUGGING_REVIEW.value, **_ALL_DOCS,
        has_plugging_details=True,
    )
    assert s.attachments_ready
    assert s.can_advance
    assert s.next_action == "Return to operator"
    assert s.next_holder_role == ROLE_OPERATOR


# ── operator review gating ────────────────────────────────────────────────────

def test_operator_review_blocked_without_certification():
    s = evaluate_handoff(
        HandoffStage.OPERATOR_REVIEW.value, **_ALL_DOCS,
        has_plugging_details=True, operator_certified=False,
    )
    assert not s.can_advance
    assert any("certify" in b.lower() for b in s.blocking)


def test_operator_review_submits_when_certified_and_ready():
    s = evaluate_handoff(
        HandoffStage.OPERATOR_REVIEW.value, **_ALL_DOCS,
        has_plugging_details=True, operator_certified=True,
    )
    assert s.can_advance
    assert s.next_action == "Submit to District"
    assert s.next_holder_role == ROLE_RRC


# ── form_type differences (w3 vs w3a) ─────────────────────────────────────────

def test_w3_does_not_require_w15_for_operator_submit():
    # W-3 only needs gau + l1 + p13; missing W-15 must not block.
    s = evaluate_handoff(
        HandoffStage.OPERATOR_REVIEW.value, form_type="w3",
        has_gau_letter=True, has_l1_well_log=True, has_p13_affidavit=True,
        has_w15_plugging_permit=False,
        has_plugging_details=True, operator_certified=True,
    )
    assert s.attachments_ready
    assert s.can_advance


def test_w3a_requires_w15():
    s = evaluate_handoff(
        HandoffStage.OPERATOR_REVIEW.value, form_type="w3a",
        has_gau_letter=True, has_l1_well_log=True, has_p13_affidavit=True,
        has_w15_plugging_permit=False,
        has_plugging_details=True, operator_certified=True,
    )
    assert not s.attachments_ready
    assert not s.can_advance


# ── terminal stages ───────────────────────────────────────────────────────────

def test_submitted_is_waiting_on_rrc():
    s = evaluate_handoff(HandoffStage.SUBMITTED.value)
    assert s.holder_role == ROLE_RRC
    assert not s.can_advance
    assert s.next_action is None


def test_accepted_is_terminal():
    s = evaluate_handoff(HandoffStage.ACCEPTED.value)
    assert not s.can_advance
    assert s.next_stage is None
    assert s.next_holder_role is None


# ── enriched build_handoff (mock) ─────────────────────────────────────────────

def test_build_handoff_resolves_operator_name():
    s = build_handoff_with_mock(API, stage=HandoffStage.DRAFT.value)
    assert s.api_number == API
    assert s.operator_name      # resolved via prefill chain
    assert s.holder_role == ROLE_OPERATOR


def test_build_handoff_passes_plugging_company():
    s = build_handoff_with_mock(
        API, stage=HandoffStage.PLUGGING_REVIEW.value,
        plugging_company="Permian Plugging Services LLC",
        has_plugging_details=True, **_ALL_DOCS,
    )
    assert s.plugging_company == "Permian Plugging Services LLC"
    assert s.can_advance


# ── serialization ─────────────────────────────────────────────────────────────

def test_to_dict_json_serializable():
    s = evaluate_handoff(
        HandoffStage.OPERATOR_REVIEW.value, **_ALL_DOCS,
        has_plugging_details=True, operator_certified=True,
    )
    d = s.to_dict()
    json.dumps(d)
    assert d["current_stage"] == "operator_review"
    assert d["holder_label"] == "Operator"
    assert len(d["workflow"]) == 5
    assert all("holder_label" in w for w in d["workflow"])
