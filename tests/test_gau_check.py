"""Tests for the GW-2 / H-15 "acceptable for plugging" check (gau_check.py).

Verifies the verdict logic over parsed GAU letters: plugging-purpose
detection, wrong-letter detection (Form GW-2 issued for a new well),
API cross-checking, GAU-2 special-requirement surfacing, and confidence.
"""

from __future__ import annotations

import json

import pytest

from plugfile.gau_check import (
    GauAcceptabilityResult,
    check_gau_acceptability,
    check_gau_text,
)
from plugfile.gau_parser import parse_gau_text

from tests.fixtures.gau_letters.letter_texts import (
    GAU1_COMMA_DEPTH,
    GAU1_EXPLICIT_FIELD,
    GAU1_STANDARD,
    GAU2_TAC_CITATION,
    GAU2_UNCOVERED,
    GAU_GW2_FORMAT,
)

# A minimal letter with explicit plugging language but no API number.
_NO_API_PLUGGING = """\
RAILROAD COMMISSION OF TEXAS — Groundwater Advisory Unit
Reference: GAU-2024-07-01-Ward-12345
Date: July 1, 2024
The base of usable quality water has been determined to be at 1,400 feet
below the surface. This determination is acceptable for plugging the well.
"""


# ── clean pass ──────────────────────────────────────────────────────────────

def test_standard_letter_is_acceptable():
    v = check_gau_text(GAU1_STANDARD)
    assert isinstance(v, GauAcceptabilityResult)
    assert v.acceptable_for_plugging
    assert v.blocking_issues == []
    purpose = next(c for c in v.checks if c.name == "plugging_purpose")
    assert purpose.status == "pass"


def test_standard_letter_high_confidence():
    v = check_gau_text(GAU1_STANDARD)
    assert v.confidence == "high"
    assert v.letter_type == "GAU-1"
    assert not v.has_special_requirements


# ── wrong letter: Form GW-2 for a NEW production well ─────────────────────────

def test_new_production_well_letter_is_blocked():
    v = check_gau_text(GAU_GW2_FORMAT)
    assert not v.acceptable_for_plugging
    assert v.blocking_issues
    purpose = next(c for c in v.checks if c.name == "plugging_purpose")
    assert purpose.status == "fail"
    assert any("new-well" in b or "New Production" in b for b in v.blocking_issues)


def test_blocked_letter_high_confidence():
    # We are confident it's the WRONG letter, so confidence is high.
    v = check_gau_text(GAU_GW2_FORMAT)
    assert v.confidence == "high"


# ── GAU-2 special requirements surfaced ───────────────────────────────────────

def test_gau2_letter_acceptable_but_flags_special():
    v = check_gau_text(GAU2_UNCOVERED)
    assert v.acceptable_for_plugging          # still usable for plugging
    assert v.letter_type == "GAU-2"
    assert v.has_special_requirements
    assert v.special_requirements
    special = next(c for c in v.checks if c.name == "special_requirements")
    assert special.status == "warn"
    assert v.confidence == "medium"


def test_gau2_tac_citation_acceptable():
    v = check_gau_text(GAU2_TAC_CITATION)
    assert v.acceptable_for_plugging
    assert v.has_special_requirements


# ── API cross-check ───────────────────────────────────────────────────────────

def test_api_match_passes():
    v = check_gau_text(GAU1_STANDARD, expected_api="42-371-30001")
    assert v.api_match is True
    api_chk = next(c for c in v.checks if c.name == "api_match")
    assert api_chk.status == "pass"
    assert v.acceptable_for_plugging


def test_api_mismatch_blocks():
    v = check_gau_text(GAU1_STANDARD, expected_api="42-999-99999")
    assert v.api_match is False
    assert not v.acceptable_for_plugging
    assert any("42-999-99999" in b for b in v.blocking_issues)


def test_api_match_ignores_dash_formatting():
    v = check_gau_text(GAU1_STANDARD, expected_api="4237130001")
    assert v.api_match is True


def test_api_not_in_letter_warns_only():
    v = check_gau_text(_NO_API_PLUGGING, expected_api="42-475-00001")
    assert v.api_match is None
    api_chk = next(c for c in v.checks if c.name == "api_match")
    assert api_chk.status == "warn"
    # Missing API to cross-check is advisory, not blocking.
    assert v.acceptable_for_plugging


def test_no_expected_api_skips_check():
    v = check_gau_text(GAU1_STANDARD)
    assert v.api_match is None
    assert not any(c.name == "api_match" for c in v.checks)


# ── ambiguous (no explicit plugging language) ─────────────────────────────────

def test_ambiguous_letter_passes_low_confidence():
    # GAU1_EXPLICIT_FIELD has no "plugging operations"/H-15 phrase.
    v = check_gau_text(GAU1_EXPLICIT_FIELD)
    assert v.acceptable_for_plugging          # not blocked
    assert v.confidence == "low"
    purpose = next(c for c in v.checks if c.name == "plugging_purpose")
    assert purpose.status == "warn"
    assert v.warnings


# ── BUQW depth checks ─────────────────────────────────────────────────────────

def test_buqw_depth_present_passes():
    v = check_gau_text(GAU1_STANDARD)
    depth_chk = next(c for c in v.checks if c.name == "buqw_depth")
    assert depth_chk.status == "pass"
    assert v.buqw_depth_ft == 1500.0


# ── structure / serialization ─────────────────────────────────────────────────

def test_check_accepts_parse_result_directly():
    result = parse_gau_text(GAU1_STANDARD)
    v = check_gau_acceptability(result, expected_api="42-371-30001")
    assert v.acceptable_for_plugging


def test_to_dict_json_serializable():
    v = check_gau_text(GAU2_UNCOVERED, expected_api="42-401-12345")
    d = v.to_dict()
    json.dumps(d)   # must not raise
    assert "acceptable_for_plugging" in d
    assert "confidence" in d
    assert "checks" in d
    assert all({"name", "status", "detail"} <= set(c) for c in d["checks"])


def test_every_check_has_valid_status():
    v = check_gau_text(GAU2_UNCOVERED, expected_api="42-401-12345")
    for c in v.checks:
        assert c.status in ("pass", "warn", "fail")
        assert c.detail


# ── all standard fixtures are acceptable ──────────────────────────────────────

@pytest.mark.parametrize("text", [
    GAU1_STANDARD,
    GAU2_UNCOVERED,
    GAU1_COMMA_DEPTH,
    GAU1_EXPLICIT_FIELD,
    GAU2_TAC_CITATION,
])
def test_all_real_gau_letters_acceptable(text):
    v = check_gau_text(text)
    assert v.acceptable_for_plugging, v.blocking_issues
