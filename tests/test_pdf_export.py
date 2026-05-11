"""Smoke tests for the Phase 2B W-3 PDF generator.

These tests verify the *renderer*, not the *coordinate fidelity*. Coordinate
calibration is a visual task — run `plugfile-pdf --calibrate -o calib.pdf`
and inspect the result.

Each test produces a PDF we can:

  1. Validate as a parseable PDF (round-trip through pypdf).
  2. Inspect for known scalar values (operator name, county, plugging date).
  3. Confirm tier-specific behavior (DRAFT watermark on free; audit pages
     appended on paid).
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from plugfile.lookups import MockFetcher
from plugfile.pdf_export import (
    PLUG_COL_X,
    PLUG_ROW_Y,
    W3_COORDS,
    render_calibration_overlay,
    render_w3_pdf,
)
from plugfile.prefill import prefill_w3


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "w-3p.pdf"
SAMPLE_API = "42-371-30001"  # Permian deep-gas fixture
SAMPLE_PLUGGING_DATE = "2026-04-22"


@pytest.fixture(scope="module")
def filled_form():
    form, _ = prefill_w3(
        SAMPLE_API,
        MockFetcher(),
        operator_overrides={
            "operator_signature_name": "Jane Doe, P.E.",
            "operator_title": "Operations Manager",
            "certification_date": "2026-04-23",
            "cementing_company": "Permian Cementing Services LLC",
        },
        plugging_date=SAMPLE_PLUGGING_DATE,
    )
    return form


def _has_template() -> bool:
    return TEMPLATE.exists()


requires_template = pytest.mark.skipif(
    not _has_template(),
    reason=f"Official W-3 template not present at {TEMPLATE}",
)


# ---- structural tests ------------------------------------------------------

def test_coord_map_pages_are_valid():
    """Every coord refers to page 0 or 1 of the 2-page template."""
    for name, coord in W3_COORDS.items():
        assert coord.page in (0, 1), f"{name}: invalid page {coord.page}"
        assert 0 < coord.x < 612, f"{name}: x={coord.x} off page"
        assert 0 < coord.y < 792, f"{name}: y={coord.y} off page"


def test_plug_grid_has_eight_columns():
    assert len(PLUG_COL_X) == 8
    # Columns must be monotonically increasing across the page
    assert list(PLUG_COL_X) == sorted(PLUG_COL_X)
    # And all within page width
    assert all(0 < x < 612 for x in PLUG_COL_X)
    # Row labels we always draw
    for required in ("cement_date", "hole_size_in", "sacks",
                     "slurry_volume", "calc_top"):
        assert required in PLUG_ROW_Y


# ---- render-bytes tests ----------------------------------------------------

@requires_template
def test_render_free_tier_produces_two_page_pdf(filled_form):
    pdf = render_w3_pdf(filled_form, tier="free")
    assert pdf.startswith(b"%PDF-")
    r = PdfReader(BytesIO(pdf))
    assert len(r.pages) == 2, "free tier must match the 2-page template"


@requires_template
def test_render_paid_tier_appends_audit_pages(filled_form):
    free = PdfReader(BytesIO(render_w3_pdf(filled_form, tier="free")))
    paid = PdfReader(BytesIO(render_w3_pdf(filled_form, tier="paid")))
    assert len(paid.pages) > len(free.pages), \
        "paid tier must add at least one audit-trail page"


@requires_template
def test_free_tier_contains_draft_watermark(filled_form):
    pdf = render_w3_pdf(filled_form, tier="free")
    text = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)
    assert "DRAFT" in text, "free tier must visibly stamp DRAFT on the output"


@requires_template
def test_paid_tier_omits_draft_watermark(filled_form):
    pdf = render_w3_pdf(filled_form, tier="paid")
    # Audit pages don't say DRAFT either
    text = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)
    assert "DRAFT — REVIEW BEFORE FILING" not in text


@requires_template
def test_overlay_carries_form_values(filled_form):
    pdf = render_w3_pdf(filled_form, tier="paid")
    text = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)
    # Sampled scalars from the Permian fixture and overrides
    assert "Apex Permian Operating LLC" in text
    assert "Pecos" in text
    assert SAMPLE_PLUGGING_DATE in text
    assert "Jane Doe" in text
    assert "Permian Cementing Services LLC" in text


@requires_template
def test_audit_page_lists_rule_paths(filled_form):
    pdf = render_w3_pdf(filled_form, tier="paid")
    pages = PdfReader(BytesIO(pdf)).pages
    audit_text = "\n".join(p.extract_text() or "" for p in pages[2:])
    assert "rule paths" in audit_text.lower()
    assert "general" in audit_text or "special_buqw_uncovered" in audit_text
    assert "Cement-volume" in audit_text


@requires_template
def test_calibration_overlay_renders():
    pdf = render_calibration_overlay()
    assert pdf.startswith(b"%PDF-")
    r = PdfReader(BytesIO(pdf))
    assert len(r.pages) == 2


# ---- coverage across all five fixtures -------------------------------------

@requires_template
@pytest.mark.parametrize("api_number", MockFetcher.known_api_numbers())
def test_render_works_for_every_fixture(api_number):
    form, _ = prefill_w3(
        api_number,
        MockFetcher(),
        plugging_date="2026-04-30",
        operator_overrides={
            "operator_signature_name": "Test Operator",
            "operator_title": "Engineer",
            "certification_date": "2026-04-30",
        },
    )
    pdf = render_w3_pdf(form, tier="paid")
    assert pdf.startswith(b"%PDF-")
    r = PdfReader(BytesIO(pdf))
    assert len(r.pages) >= 2
