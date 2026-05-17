"""Tests for Phase 2C — GAU letter PDF parser.

Coverage:
  - All five fixture API numbers (GAU-1 and GAU-2 formats)
  - Comma-formatted depths ("1,500 feet")
  - Explicit "BUQW Depth:" field label
  - TAC §3.14(d) special-case detection
  - Reference number extraction (all three pattern variants)
  - Synthesised reference fallback when ref not found
  - GauParseError on scanned / too-short text
  - Out-of-range depth warning
  - as_lookup_result() compatibility with GAULookupResult TypedDict
  - Round-trip: parse_gau_text -> prefill_w3 via operator_overrides
"""

from __future__ import annotations

import io
import pytest

from plugfile.gau_parser import (
    GauParseError,
    GauParseResult,
    parse_gau_text,
    parse_gau_pdf,
)
from plugfile.lookups import GAULookupResult
from tests.fixtures.gau_letters.letter_texts import (
    GAU1_STANDARD,
    GAU1_COMMA_DEPTH,
    GAU1_EXPLICIT_FIELD,
    GAU2_UNCOVERED,
    GAU2_TAC_CITATION,
    GAU_SCAN_STUB,
    GAU_WEIRD_DEPTH,
    LETTER_BY_API,
    EXPECTED_BUQW_BY_API,
    EXPECTED_REF_BY_API,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(text: str) -> bytes:
    """Wrap plain text in a minimal valid PDF using reportlab."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    # Write text line-by-line onto the page
    y = 750
    for line in text.splitlines():
        if y < 50:
            c.showPage()
            y = 750
        c.drawString(40, y, line[:110])  # clip long lines
        y -= 14
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# parse_gau_text — all five fixtures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("api_number", list(LETTER_BY_API.keys()))
def test_buqw_depth_extracted_for_all_fixtures(api_number):
    text = LETTER_BY_API[api_number]
    result = parse_gau_text(text)
    assert result.buqw_depth_ft == EXPECTED_BUQW_BY_API[api_number], (
        f"API {api_number}: expected {EXPECTED_BUQW_BY_API[api_number]} ft, "
        f"got {result.buqw_depth_ft} ft"
    )


@pytest.mark.parametrize("api_number", list(LETTER_BY_API.keys()))
def test_reference_extracted_for_all_fixtures(api_number):
    text = LETTER_BY_API[api_number]
    result = parse_gau_text(text)
    assert result.gau_letter_reference == EXPECTED_REF_BY_API[api_number], (
        f"API {api_number}: expected ref {EXPECTED_REF_BY_API[api_number]!r}, "
        f"got {result.gau_letter_reference!r}"
    )


# ---------------------------------------------------------------------------
# GAU-1 standard letter
# ---------------------------------------------------------------------------

def test_gau1_standard_letter_type():
    result = parse_gau_text(GAU1_STANDARD)
    assert result.letter_type == "GAU-1"
    assert result.special_requirements == []


def test_gau1_standard_metadata():
    result = parse_gau_text(GAU1_STANDARD)
    assert result.api_number == "42-371-30001"
    assert result.county == "Pecos"
    assert "2024" in (result.letter_date or "")


# ---------------------------------------------------------------------------
# GAU-2 special-case letters
# ---------------------------------------------------------------------------

def test_gau2_uncovered_is_special_case():
    result = parse_gau_text(GAU2_UNCOVERED)
    assert result.letter_type == "GAU-2"
    assert len(result.special_requirements) >= 1
    # Must call out that surface casing doesn't cover BUQW
    combined = " ".join(result.special_requirements).lower()
    assert "surface" in combined or "uncover" in combined


def test_gau2_tac_citation_detected():
    result = parse_gau_text(GAU2_TAC_CITATION)
    assert result.letter_type == "GAU-2"
    assert any("3.14" in r or "bridge" in r.lower()
               for r in result.special_requirements)


# ---------------------------------------------------------------------------
# Depth format variants
# ---------------------------------------------------------------------------

def test_comma_formatted_depth():
    """'1,500 feet' must parse to 1500.0, not 500.0."""
    result = parse_gau_text(GAU1_STANDARD)  # contains "1,500 feet"
    assert result.buqw_depth_ft == 1500.0


def test_explicit_buqw_field_label():
    """'BUQW Depth: 600 feet' explicit field."""
    result = parse_gau_text(GAU1_EXPLICIT_FIELD)
    assert result.buqw_depth_ft == 600.0


# ---------------------------------------------------------------------------
# Reference pattern variants
# ---------------------------------------------------------------------------

def test_reference_with_letter_no_label():
    """'Letter No.: GAU-...' pattern."""
    result = parse_gau_text(GAU1_EXPLICIT_FIELD)
    assert result.gau_letter_reference == "GAU-2024-09-22-Throck-00301"


def test_reference_bare_pattern():
    """Bare 'GAU-YYYY-MM-DD-County-NNN' in body text."""
    result = parse_gau_text(GAU1_COMMA_DEPTH)
    assert result.gau_letter_reference == "GAU-2024-05-19-Crane-08812"


def test_reference_synthesized_when_missing():
    """When no reference found, a synthetic one is generated and warned."""
    text = """\
RAILROAD COMMISSION OF TEXAS
Groundwater Advisory Unit

Date: June 1, 2025

The base of usable quality water is 900 feet below the surface.
General plugging requirements apply.
"""
    result = parse_gau_text(text)
    assert result.buqw_depth_ft == 900.0
    assert "GAU" in result.gau_letter_reference
    assert any("synthesized" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_scan_stub_raises_parse_error():
    """Too-short text raises GauParseError."""
    with pytest.raises(GauParseError, match="usable|BUQW|depth"):
        parse_gau_text(GAU_SCAN_STUB)


def test_no_depth_in_text_raises_parse_error():
    with pytest.raises(GauParseError):
        parse_gau_text("This letter contains no depth information whatsoever.")


# ---------------------------------------------------------------------------
# Warning cases
# ---------------------------------------------------------------------------

def test_out_of_range_depth_generates_warning():
    result = parse_gau_text(GAU_WEIRD_DEPTH)
    assert result.buqw_depth_ft == 15.0
    assert any("range" in w.lower() or "15" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# as_lookup_result() TypedDict compatibility
# ---------------------------------------------------------------------------

def test_as_lookup_result_keys():
    result = parse_gau_text(GAU1_STANDARD)
    lookup = result.as_lookup_result()
    # Must satisfy GAULookupResult TypedDict keys
    assert set(lookup.keys()) == {"buqw_depth_ft", "gau_letter_reference"}
    assert isinstance(lookup["buqw_depth_ft"], float)
    assert isinstance(lookup["gau_letter_reference"], str)


# ---------------------------------------------------------------------------
# parse_gau_pdf — round-trip through reportlab PDF
# ---------------------------------------------------------------------------

def test_parse_gau_pdf_standard_letter():
    """Full round-trip: text -> PDF bytes -> parse_gau_pdf."""
    pdf_bytes = _make_pdf(GAU1_STANDARD)
    result = parse_gau_pdf(pdf_bytes)
    assert result.buqw_depth_ft == 1500.0
    assert "Pecos" in result.gau_letter_reference


def test_parse_gau_pdf_special_case():
    pdf_bytes = _make_pdf(GAU2_UNCOVERED)
    result = parse_gau_pdf(pdf_bytes)
    assert result.buqw_depth_ft == 800.0
    assert result.letter_type == "GAU-2"


def test_parse_gau_pdf_too_short_raises():
    """A near-empty PDF raises GauParseError."""
    pdf_bytes = _make_pdf("   ")
    with pytest.raises(GauParseError, match="characters"):
        parse_gau_pdf(pdf_bytes)


# ---------------------------------------------------------------------------
# prefill integration: parse result -> operator_overrides
# ---------------------------------------------------------------------------

def test_gau_parse_result_flows_into_prefill():
    """GauParseResult.as_lookup_result() can be passed as operator_overrides."""
    from plugfile.lookups import MockFetcher
    from plugfile.prefill import prefill_w3

    result = parse_gau_text(GAU1_STANDARD)
    lookup = result.as_lookup_result()

    form, _ = prefill_w3(
        "42-371-30001",
        MockFetcher(),
        operator_overrides={
            "buqw_depth_ft": lookup["buqw_depth_ft"],
            "gau_letter_reference": lookup["gau_letter_reference"],
            "operator_signature_name": "Test Operator",
            "certification_date": "2026-05-16",
        },
        plugging_date="2026-05-16",
    )
    assert form.buqw_depth_ft == 1500.0
    assert form.gau_letter_reference == "GAU-2024-03-12-Pecos-21874"
