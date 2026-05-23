"""Tests for the Required-Attachments Checker (attachments.py).

Validates readiness logic, missing-doc detection, per-form-type rules,
and the to_dict() output shape used by the API endpoint.
"""

from __future__ import annotations

import pytest

from plugfile.attachments import (
    AttachmentChecklist,
    AttachmentStatus,
    check_attachments,
)

API = "42-371-30001"


# ── readiness logic ───────────────────────────────────────────────────────────

def test_all_missing_is_not_ready():
    result = check_attachments(API, form_type="w3a")
    assert not result.ready
    assert result.present_count == 0


def test_all_present_w3a_is_ready():
    result = check_attachments(
        API,
        form_type="w3a",
        has_gau_letter=True,
        has_w15_plugging_permit=True,
        has_l1_well_log=True,
        has_p13_affidavit=True,
    )
    assert result.ready
    assert result.missing == []
    assert result.present_count == result.required_count


def test_gau_only_is_not_ready():
    result = check_attachments(API, form_type="w3a", has_gau_letter=True)
    assert not result.ready
    assert result.present_count == 1
    # Three docs still missing
    assert len(result.missing) == 3


def test_one_missing_blocks_ready():
    result = check_attachments(
        API,
        form_type="w3a",
        has_gau_letter=True,
        has_w15_plugging_permit=True,
        has_l1_well_log=True,
        has_p13_affidavit=False,   # one missing
    )
    assert not result.ready
    assert len(result.missing) == 1
    assert "P-13" in result.missing[0]


# ── form-type differences ─────────────────────────────────────────────────────

def test_w3_does_not_require_w15():
    # W-3 (plugging record) does not re-require the permit (already granted via W-3A)
    result = check_attachments(
        API,
        form_type="w3",
        has_gau_letter=True,
        has_w15_plugging_permit=False,  # absent but not required for W-3
        has_l1_well_log=True,
        has_p13_affidavit=True,
    )
    assert result.ready


def test_w3a_requires_w15():
    result = check_attachments(
        API,
        form_type="w3a",
        has_gau_letter=True,
        has_w15_plugging_permit=False,
        has_l1_well_log=True,
        has_p13_affidavit=True,
    )
    assert not result.ready
    assert any("W-15" in m for m in result.missing)


def test_w3_required_count_is_3():
    result = check_attachments(API, form_type="w3")
    assert result.required_count == 3


def test_w3a_required_count_is_4():
    result = check_attachments(API, form_type="w3a")
    assert result.required_count == 4


# ── output structure ──────────────────────────────────────────────────────────

def test_result_type():
    result = check_attachments(API)
    assert isinstance(result, AttachmentChecklist)


def test_items_length_always_4():
    # All four attachment types always appear in the checklist
    for form_type in ("w3a", "w3"):
        result = check_attachments(API, form_type=form_type)
        assert len(result.items) == 4


def test_items_are_attachment_status():
    result = check_attachments(API)
    for item in result.items:
        assert isinstance(item, AttachmentStatus)
        assert item.display_name
        assert item.description
        assert item.rrc_ref
        assert item.tip


def test_missing_shows_display_names():
    result = check_attachments(API, form_type="w3a")
    # Every missing entry should be a human-readable name, not a key
    for m in result.missing:
        assert "_" not in m   # keys have underscores, display names don't


def test_gau_reference_echoed_back():
    ref = "GAU-2024-03-12-Pecos-21874"
    result = check_attachments(
        API, form_type="w3a", has_gau_letter=True, gau_reference=ref
    )
    gau_item = next(i for i in result.items if i.key == "gau_letter")
    assert gau_item.reference == ref


def test_gau_reference_absent_when_not_supplied():
    result = check_attachments(API, form_type="w3a")
    gau_item = next(i for i in result.items if i.key == "gau_letter")
    assert gau_item.reference is None


def test_api_number_in_result():
    result = check_attachments(API, form_type="w3a")
    assert result.api_number == API


def test_to_dict_json_serializable():
    import json
    result = check_attachments(API, form_type="w3a")
    d = result.to_dict()
    json.dumps(d)   # must not raise
    assert d["api_number"] == API
    assert d["form_type"] == "w3a"
    assert "ready" in d
    assert "missing" in d
    assert len(d["items"]) == 4


def test_present_count_matches_flags():
    result = check_attachments(
        API,
        form_type="w3a",
        has_gau_letter=True,
        has_w15_plugging_permit=True,
        has_l1_well_log=False,
        has_p13_affidavit=False,
    )
    assert result.present_count == 2
