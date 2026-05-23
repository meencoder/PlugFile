"""Plugfile web API — FastAPI backend for the mobile W-3 voice wizard.

Four endpoints wrap the existing plugfile engine:

  POST /api/lookup    {api_number}           → well metadata from RRC
  POST /api/gau       multipart PDF upload   → BUQW depth + reference
  POST /api/narrative {transcript}           → Section IX narrative + slots
  POST /api/generate  form data              → filled W-3 PDF bytes

The static PWA frontend (index.html / app.js / style.css) is served from
src/plugfile/static/ alongside the API.

Environment variables
---------------------
PLUGFILE_RRC_LIVE=true   Use live RrcFetcher instead of MockFetcher.
PLUGFILE_LLM_FALLBACK    Passed through to transcript_to_narrative().
PORT                     Bind port (default 8000). Set by Render automatically.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from plugfile.aor import assess_aor
from plugfile.attachments import check_attachments
from plugfile.gau_check import check_gau_acceptability
from plugfile.gau_parser import GauParseError, parse_gau_pdf, _load_dotenv
from plugfile.lookups import MockFetcher
from plugfile.narrative import transcript_to_narrative
from plugfile.pdf_export import render_w3_pdf, render_w3a_pdf
from plugfile.plug_plan import build_plug_plan
from plugfile.portal_format import format_for_portal
from plugfile.prefill import prefill_w3
from plugfile.prefill_w3a import prefill_w3a

# Load a repo-root .env (if present) so ANTHROPIC_API_KEY, PLUGFILE_RRC_LIVE,
# and PLUGFILE_LLM_FALLBACK work without depending on the launching shell's
# environment. Real environment variables always take precedence.
_load_dotenv()

app = FastAPI(
    title="Plugfile",
    version="0.4.0",
    description="Voice-first W-3 Plugging Record assistant for Texas RRC",
)

_STATIC = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Fetcher selection
# ---------------------------------------------------------------------------

def _fetcher():
    """Return live RrcFetcher if env var set, else MockFetcher for dev/demo."""
    if os.environ.get("PLUGFILE_RRC_LIVE", "").strip().lower() in ("1", "true", "yes"):
        from plugfile.lookups_rrc import RRCRoRQFetcher
        return RRCRoRQFetcher()
    return MockFetcher()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class LookupRequest(BaseModel):
    api_number: str


class NarrativeRequest(BaseModel):
    transcript: str


class GenerateRequest(BaseModel):
    api_number: str
    operator_signature_name: str
    operator_title: str = "Operator Representative"
    certification_date: str          # ISO YYYY-MM-DD
    plugging_date: str               # ISO YYYY-MM-DD
    buqw_depth_ft: Optional[float] = None
    gau_letter_reference: Optional[str] = None
    narrative: Optional[str] = None  # Section IX text (edited by operator)
    paid_tier: bool = False


class W3APrefillRequest(BaseModel):
    """Prefill a W-3A (Notice of Intention to Plug). `overrides` carries
    operator-sourced fields (well_type, completion_type, aor_findings,
    cementer info, certification, etc.)."""
    api_number: str
    overrides: Optional[dict[str, Any]] = None


class W3AGenerateRequest(BaseModel):
    """Generate a filled W-3A PDF. Same as W3APrefillRequest plus tier flag."""
    api_number: str
    overrides: Optional[dict[str, Any]] = None
    paid_tier: bool = False


class PlugProgramRequest(BaseModel):
    """Return the §3.14 plug program for a wellbore without rendering a PDF.

    `overrides` accepts the same operator-sourced fields as W3APrefillRequest
    (perf status, GAU date, AOR findings, etc.).
    """
    api_number: str
    overrides: Optional[dict[str, Any]] = None


class AttachmentCheckRequest(BaseModel):
    """Report which required filing attachments are present.

    Set each ``has_*`` flag True once the document has been uploaded /
    confirmed. ``gau_reference`` is optional but recommended — it is echoed
    back in the checklist for cross-reference.
    """
    api_number: str
    form_type: str = "w3a"          # "w3a" (intent) or "w3" (plugging record)
    has_gau_letter: bool = False
    has_w15_plugging_permit: bool = False
    has_l1_well_log: bool = False
    has_p13_affidavit: bool = False
    gau_reference: Optional[str] = None


class PortalFormatRequest(BaseModel):
    """Convert internal Plugfile values to RRC portal copy-paste strings.

    Returns every field the operator needs to enter into the RRC Online
    System formatted exactly as the portal expects: fractional casing ODs,
    integer depth strings, MM/DD/YYYY dates, rounded sack counts.
    ``overrides`` accepts the same operator-sourced fields as
    :class:`W3APrefillRequest`.
    """
    api_number: str
    overrides: Optional[dict[str, Any]] = None


class AORRequest(BaseModel):
    """Evaluate the area of review for a wellbore.

    Returns a manual GIS-Viewer review checklist plus, for each nearby-well
    finding in ``overrides['aor_findings']``, whether it sits inside the
    ½-mile radius and the §3.14(d)(1) isolation plug it requires (if any).
    ``overrides`` accepts the same operator-sourced fields as
    :class:`W3APrefillRequest` — supply ``aor_findings`` to get plug output.
    """
    api_number: str
    overrides: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/lookup")
def lookup(req: LookupRequest):
    """Fetch well metadata by API number."""
    try:
        fetcher = _fetcher()
        well = fetcher.lookup_well_by_api(req.api_number)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RRC lookup failed: {e}")
    return well


@app.post("/api/gau")
async def gau_parse(
    file: UploadFile = File(...),
    api_number: Optional[str] = Form(None),
):
    """Parse a GAU letter PDF and extract BUQW depth + reference number.

    Also runs the GW-2 / H-15 "acceptable for plugging" check and returns
    the verdict under ``acceptability``. Pass the ``api_number`` of the well
    being plugged (optional) to cross-check it against the API on the letter
    and catch a letter uploaded for the wrong well.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF.")
    pdf_bytes = await file.read()
    try:
        r = parse_gau_pdf(pdf_bytes)
    except GauParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    acceptability = check_gau_acceptability(
        r, expected_api=(api_number or None)
    ).to_dict()

    return {
        "buqw_depth_ft": r.buqw_depth_ft,
        "gau_letter_reference": r.gau_letter_reference,
        "letter_type": r.letter_type,
        "special_requirements": r.special_requirements,
        "warnings": r.warnings,
        "acceptability": acceptability,
    }


@app.post("/api/narrative")
def narrative(req: NarrativeRequest):
    """Extract surface-restoration slots and draft the Section IX narrative."""
    use_llm = os.environ.get("PLUGFILE_LLM_FALLBACK", "").strip().lower() in (
        "1", "true", "yes"
    )
    text, facts, warnings = transcript_to_narrative(
        req.transcript,
        use_llm_fallback=use_llm if use_llm else None,
    )
    return {
        "narrative": text,
        "warnings": [w.message for w in warnings],
        "slots": {
            "casing_cut_depth_ft": facts.casing_cut_depth_ft,
            "cap_type": facts.cap_type,
            "cap_dimensions": facts.cap_dimensions,
            "cellar_filled": facts.cellar_filled,
            "cellar_fill_material": facts.cellar_fill_material,
            "equipment_removed": facts.equipment_removed,
            "vegetation_action": facts.vegetation_action,
            "grading_action": facts.grading_action,
            "access_road_status": facts.access_road_status,
            "fencing_status": facts.fencing_status,
            "date_of_work": facts.date_of_work,
            "surface_owner_consent": facts.surface_owner_consent,
            "sensitive_surface_notes": facts.sensitive_surface_notes,
        },
    }


@app.post("/api/generate")
def generate(req: GenerateRequest):
    """Assemble a W3Form and return a filled PDF."""
    overrides: dict = {
        "operator_signature_name": req.operator_signature_name,
        "operator_title": req.operator_title,
        "certification_date": req.certification_date,
    }

    try:
        fetcher = _fetcher()
        form, _ = prefill_w3(
            req.api_number,
            fetcher,
            operator_overrides=overrides,
            plugging_date=req.plugging_date,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"W-3 prefill failed: {e}")

    # Apply GAU and narrative after prefill — these fields are operator-sourced
    # and are set directly rather than going through the conflict-detection path.
    if req.buqw_depth_ft is not None:
        form.buqw_depth_ft = req.buqw_depth_ft
    if req.gau_letter_reference:
        form.gau_letter_reference = req.gau_letter_reference
    if req.narrative:
        form.surface_restoration_narrative = req.narrative

    try:
        pdf_bytes = render_w3_pdf(form, tier="paid" if req.paid_tier else "free")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {e}")

    tier = "FINAL" if req.paid_tier else "DRAFT"
    fname = f"W3_{req.api_number.replace('-', '')}_{tier}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/w3a/prefill")
def w3a_prefill(req: W3APrefillRequest):
    """Prefill a W-3A (Notice of Intention to Plug) and return it as JSON.

    Populates Boxes 1-16 + casing/perforations from RRC lookups, computes the
    proposed plug program via the §3.14 engine, and applies operator overrides.
    No PDF yet — this feeds the 'Intent' wizard; the W-3A PDF export is separate.
    """
    try:
        fetcher = _fetcher()
        form, conflicts = prefill_w3a(
            req.api_number, fetcher, operator_overrides=req.overrides
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"W-3A prefill failed: {e}")
    return {
        "form": form.to_dict(),
        "missing_required": sorted(form.missing_required()),
        "proposed_plug_count": len(form.proposed_plug_record),
        "rule_paths": form.plug_program_rule_paths,
        "conflicts": [c.render() for c in conflicts],
    }


@app.post("/api/w3a/generate")
def w3a_generate(req: W3AGenerateRequest):
    """Prefill a W-3A and return the filled PDF as a download.

    `paid_tier=true`  → clean FINAL PDF with audit page appended.
    `paid_tier=false` → single-page PDF with DRAFT watermark.
    """
    try:
        fetcher = _fetcher()
        form, _ = prefill_w3a(
            req.api_number, fetcher, operator_overrides=req.overrides
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"W-3A prefill failed: {e}")

    try:
        pdf_bytes = render_w3a_pdf(form, tier="paid" if req.paid_tier else "free")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"W-3A PDF export failed: {e}")

    tier = "FINAL" if req.paid_tier else "DRAFT"
    fname = f"W3A_{req.api_number.replace('-', '')}_{tier}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/plug-program")
def plug_program(req: PlugProgramRequest):
    """Compute the §3.14 required plug program for a wellbore.

    Returns the full plug list with depths, cement volumes, TAC citations,
    and a human-readable rationale for each plug — without rendering a PDF.
    Useful for the PWA "plug preview" step and for standalone validation.
    """
    try:
        fetcher = _fetcher()
        plan, conflicts = build_plug_plan(
            req.api_number, fetcher, operator_overrides=req.overrides
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Plug-program computation failed: {e}")
    return {
        **plan.to_dict(),
        "conflicts": [c.render() for c in conflicts],
    }


@app.post("/api/attachments/check")
def attachments_check(req: AttachmentCheckRequest):
    """Evaluate required-attachment readiness for a W-3 or W-3A filing.

    Returns a ``ready`` flag plus a per-document checklist. Any missing
    required documents are listed in ``missing`` so the operator knows
    exactly what to gather before submitting to the RRC district.
    """
    if req.form_type not in ("w3a", "w3"):
        raise HTTPException(
            status_code=422,
            detail=f"form_type must be 'w3a' or 'w3', got {req.form_type!r}",
        )
    result = check_attachments(
        req.api_number,
        form_type=req.form_type,  # type: ignore[arg-type]
        has_gau_letter=req.has_gau_letter,
        has_w15_plugging_permit=req.has_w15_plugging_permit,
        has_l1_well_log=req.has_l1_well_log,
        has_p13_affidavit=req.has_p13_affidavit,
        gau_reference=req.gau_reference,
    )
    return result.to_dict()


@app.post("/api/portal-format")
def portal_format_endpoint(req: PortalFormatRequest):
    """Format well data as portal-ready copy-paste strings.

    Converts internal Plugfile values to the exact formats required by the
    RRC Online System web portal (casing OD as fractions, depths as integers,
    dates as MM/DD/YYYY, cement sacks rounded to the nearest whole number).

    Returns a ``ready_to_copy`` flag plus section-by-section dicts the
    operator can copy field-by-field into the portal.
    """
    try:
        fetcher = _fetcher()
        result, conflicts = format_for_portal(
            req.api_number, fetcher, operator_overrides=req.overrides
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Portal format failed: {e}"
        )
    return {
        **result.to_dict(),
        "conflicts": [c.render() for c in conflicts],
    }


@app.post("/api/aor")
def aor_endpoint(req: AORRequest):
    """Evaluate the area of review for a wellbore.

    Returns a step-by-step RRC GIS-Viewer review checklist (the AOR search
    is a manual, external step — no public spatial API) plus a per-finding
    assessment: which nearby wells sit inside the ½-mile radius and the
    §3.14(d)(1) isolation plug each penetrated zone requires.
    """
    try:
        fetcher = _fetcher()
        assessment, conflicts = assess_aor(
            req.api_number, fetcher, operator_overrides=req.overrides
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AOR assessment failed: {e}")
    return {
        **assessment.to_dict(),
        "conflicts": [c.render() for c in conflicts],
    }


# ---------------------------------------------------------------------------
# Static files + SPA
# ---------------------------------------------------------------------------

if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
def spa():
    if _STATIC.exists():
        return FileResponse(_STATIC / "index.html")
    return {
        "status": "Plugfile API running",
        "docs": "/docs",
        "note": "Frontend not found — run from the repo root or install the package.",
    }


# ---------------------------------------------------------------------------
# CLI entry point  (plugfile-serve)
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    """Start the Plugfile web server. Reads PORT env var (default 8000)."""
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    reload = os.environ.get("PLUGFILE_DEV", "").lower() in ("1", "true", "yes")
    uvicorn.run(
        "plugfile.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    _cli_main()
