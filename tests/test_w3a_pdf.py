"""Tests for the W-3A PDF overlay (render_w3a_pdf).

Validates: valid PDF bytes, page counts per tier, DRAFT watermark on the free
tier, an appended audit page on the paid tier, and that key field values land
in the rendered text layer. Coordinates are a first-pass calibration, so these
tests assert *presence* of values, not pixel positions.
"""

from __future__ import annotations

from io import BytesIO

import pytest

from pypdf import PdfReader

from plugfile.pdf_export import (
    render_w3a_pdf,
    render_w3a_calibration_overlay,
    _resolve_w3a_template,
)
from plugfile.prefill_w3a import prefill_w3a_with_mock

API = "42-371-30001"

FULL_OVERRIDES = {
    "well_type": "oil",
    "completion_type": "single",
    "drilling_permit_no": "812345",
    "cementing_company": "Permian Cementing Services LLC",
    "operator_signature_name": "Sharmeen Q.",
    "operator_title": "Operator Representative",
    "certification_date": "2026-05-21",
}


def _text(pdf_bytes: bytes) -> str:
    r = PdfReader(BytesIO(pdf_bytes))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def test_template_resolves():
    # docs/w-3ap.pdf must be locatable from the repo
    p = _resolve_w3a_template(None)
    assert p.exists()
    assert p.name == "w-3ap.pdf"


def test_render_free_is_valid_single_page_pdf():
    form, _ = prefill_w3a_with_mock(API, FULL_OVERRIDES)
    pdf = render_w3a_pdf(form, tier="free")
    assert pdf[:5] == b"%PDF-"
    r = PdfReader(BytesIO(pdf))
    assert len(r.pages) == 1  # W-3A is single-page; free tier appends nothing


def test_free_tier_has_draft_watermark():
    form, _ = prefill_w3a_with_mock(API, FULL_OVERRIDES)
    txt = _text(render_w3a_pdf(form, tier="free"))
    assert "DRAFT" in txt


def test_paid_tier_appends_audit_page():
    form, _ = prefill_w3a_with_mock(API, FULL_OVERRIDES)
    pdf = render_w3a_pdf(form, tier="paid")
    r = PdfReader(BytesIO(pdf))
    assert len(r.pages) >= 2  # form page + at least one audit page
    txt = _text(pdf)
    assert "W-3A Audit Trail" in txt
    assert "DRAFT" not in txt  # paid output is clean


def test_rendered_pdf_contains_key_values():
    form, _ = prefill_w3a_with_mock(API, FULL_OVERRIDES)
    txt = _text(render_w3a_pdf(form, tier="paid"))
    # operator + well identity flow through to the rendered text layer
    assert "Apex Permian Operating LLC" in txt
    assert "Heritage A" in txt
    assert "Pecos" in txt
    # API state-code prefix is stripped (pre-printed on the form)
    assert "371-30001" in txt
    # cementing company override rendered
    assert "Permian Cementing Services LLC" in txt


def test_audit_lists_proposed_plugs():
    form, _ = prefill_w3a_with_mock(API, FULL_OVERRIDES)
    txt = _text(render_w3a_pdf(form, tier="paid"))
    assert "Proposed plug program" in txt
    # at least one TAC citation appears
    assert "cite=" in txt


def test_calibration_overlay_renders():
    pdf = render_w3a_calibration_overlay()
    assert pdf[:5] == b"%PDF-"
    r = PdfReader(BytesIO(pdf))
    assert len(r.pages) == 1


def test_renders_for_all_mock_wells():
    for api in ("42-371-30001", "42-401-12345", "42-103-77001",
                "42-461-00042", "42-329-55555"):
        form, _ = prefill_w3a_with_mock(api, FULL_OVERRIDES)
        pdf = render_w3a_pdf(form, tier="free")
        assert pdf[:5] == b"%PDF-"
