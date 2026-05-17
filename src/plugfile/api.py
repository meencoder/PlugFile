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
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from plugfile.gau_parser import GauParseError, parse_gau_pdf
from plugfile.lookups import MockFetcher
from plugfile.narrative import transcript_to_narrative
from plugfile.pdf_export import render_w3_pdf
from plugfile.prefill import prefill_w3

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
        from plugfile.lookups_rrc import RrcFetcher
        return RrcFetcher()
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
async def gau_parse(file: UploadFile = File(...)):
    """Parse a GAU letter PDF and extract BUQW depth + reference number."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF.")
    pdf_bytes = await file.read()
    try:
        r = parse_gau_pdf(pdf_bytes)
    except GauParseError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "buqw_depth_ft": r.buqw_depth_ft,
        "gau_letter_reference": r.gau_letter_reference,
        "letter_type": r.letter_type,
        "special_requirements": r.special_requirements,
        "warnings": r.warnings,
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
