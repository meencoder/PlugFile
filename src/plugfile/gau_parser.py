"""Phase 2C — GAU letter PDF parser.

Extracts ``buqw_depth_ft`` and ``gau_letter_reference`` from a Texas RRC
Groundwater Advisory Unit (GAU) letter PDF so that operators can upload the
letter instead of typing the depth manually.

The RRC GAU unit issues letters in two formats:

  GAU-1  Standard advisory — single BUQW depth, no special requirements.
  GAU-2  Special-case advisory — BUQW depth *plus* one or more special
         plugging requirements (e.g. BUQW is uncovered / above top of
         cement on the surface string).

Both land as PDF letters.  The text is selectable in modern versions;
older letters may be scanned images.  We attempt:

  1. pypdf text extraction (fast, works on modern PDFs).
  2. pypdfium2 OCR-ready rendering hint (flag if pypdf returns <100 chars).

We do NOT bundle an OCR engine — if the letter is a scan the caller sees
``GauParseWarning.POSSIBLE_SCAN`` in ``result.warnings`` and should prompt
the operator to type the depth manually as a fallback.

Public API
----------
  parse_gau_pdf(pdf_bytes)  -> GauParseResult
  parse_gau_text(text)      -> GauParseResult   (useful for tests)
  _cli_main()               -> int               (plugfile-gau entry point)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class GauParseError(ValueError):
    """Raised when BUQW depth cannot be extracted with confidence."""


@dataclass
class GauParseResult:
    """Structured output of the GAU letter parser.

    Only ``buqw_depth_ft`` and ``gau_letter_reference`` are required for
    downstream use in ``prefill_w3()``.  The remaining fields are best-effort
    and useful for audit trail / display.
    """
    buqw_depth_ft: float
    gau_letter_reference: str

    # ---- optional best-effort fields ----------------------------------------
    api_number: Optional[str] = None          # e.g. "42-371-30001"
    county: Optional[str] = None              # e.g. "Pecos"
    operator_name: Optional[str] = None
    letter_date: Optional[str] = None         # ISO or as-printed
    letter_type: str = "GAU-1"               # "GAU-1" | "GAU-2"
    special_requirements: list[str] = field(default_factory=list)

    # ---- parser diagnostics -------------------------------------------------
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""

    def as_lookup_result(self) -> dict:
        """Return a dict compatible with ``GAULookupResult`` TypedDict."""
        return {
            "buqw_depth_ft": self.buqw_depth_ft,
            "gau_letter_reference": self.gau_letter_reference,
        }


# ---------------------------------------------------------------------------
# Regex patterns  (compiled once at import time)
# ---------------------------------------------------------------------------

# BUQW depth — primary patterns in expected text order
_BUQW_PATTERNS: list[re.Pattern] = [
    # "base of usable quality water ... 1,500 feet" (full phrase)
    re.compile(
        r"base\s+of\s+usable[\s-]quality\s+water[^.]{0,120}?"
        r"(\d{1,2},\d{3}|\d{2,5})\s*(?:feet|ft)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    # "BUQW depth: 1500 feet" or "BUQW: 1,500'"
    re.compile(
        r"BUQW\s*(?:depth)?[:\s]+(\d{1,2},\d{3}|\d{2,5})\s*(?:feet|ft|')",
        re.IGNORECASE,
    ),
    # "depth of 1,500 feet" in proximity to "usable" or "groundwater"
    re.compile(
        r"(?:usable|groundwater|freshwater)[^.]{0,200}?"
        r"depth\s+of\s+(\d{1,2},\d{3}|\d{2,5})\s*(?:feet|ft)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    # "1,500-foot" or "1500-foot" e.g. "protected to a 1,500-foot depth"
    re.compile(
        r"(\d{1,2},\d{3}|\d{2,5})-foot\s+depth",
        re.IGNORECASE,
    ),
    # "BUQW depth for this well: 1,200 feet" — anything between BUQW and colon
    re.compile(
        r"BUQW[^:\n]{0,40}:\s*(\d{1,2},\d{3}|\d{2,5})\s*(?:feet|ft)\b",
        re.IGNORECASE,
    ),
    # Fallback: first 4-digit number followed by feet near "water"
    re.compile(
        r"(\d{1,2},\d{3}|\d{3,5})\s*(?:feet|ft)\b[^.]{0,80}?"
        r"(?:water|groundwater|usable)",
        re.IGNORECASE | re.DOTALL,
    ),
]

# GAU letter reference number — e.g. "GAU-2024-03-12-Pecos-21874"
_REF_PATTERNS: list[re.Pattern] = [
    # Explicit "Reference:" / "Letter No." label
    re.compile(
        r"(?:reference|letter\s+no\.?|ref\.?)\s*[:\s]+"
        r"(GAU[-\s]\d{4}[-\s]\d{2}[-\s]\d{2}[-\s]\w+[-\s]\d+)",
        re.IGNORECASE,
    ),
    # Bare GAU-YYYY-MM-DD-County-NNN pattern anywhere in text
    re.compile(
        r"\b(GAU-\d{4}-\d{2}-\d{2}-[A-Za-z]+-\d+)\b",
        re.IGNORECASE,
    ),
    # Older format: "GAU 2024-03-12" without county
    re.compile(
        r"\b(GAU[-\s]\d{4}[-\s]\d{2}[-\s]\d{2})\b",
        re.IGNORECASE,
    ),
]

# API number in text
_API_PATTERN = re.compile(r"\b(42-\d{3}-\d{5})\b")

# Date: Month D, YYYY  or  MM/DD/YYYY
_DATE_PATTERN = re.compile(
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4}",
    re.IGNORECASE,
)

# Special-case requirement indicators
_SPECIAL_CASE_PHRASES = [
    (re.compile(r"surface\s+casing.*?does\s+not\s+cover", re.IGNORECASE | re.DOTALL),
     "Surface casing does not cover BUQW"),
    (re.compile(r"BUQW.*?uncover", re.IGNORECASE | re.DOTALL),
     "BUQW uncovered"),
    (re.compile(r"cement.*?bridge.*?plug", re.IGNORECASE),
     "Cement bridge plug required at BUQW"),
    (re.compile(r"special.*?plugging.*?requirement", re.IGNORECASE),
     "Special plugging requirements apply"),
    (re.compile(r"TAC\s+§\s*3\.14\(d\)", re.IGNORECASE),
     "TAC §3.14(d) special-case rule applies"),
]

# County name extraction near "County" keyword
_COUNTY_PATTERN = re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+County", re.IGNORECASE)

# Operator name — "Operator:" label
_OPERATOR_PATTERN = re.compile(r"Operator\s*[:\s]+([^\n,]{3,60})", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_gau_text(text: str) -> GauParseResult:
    """Parse GAU letter text and return a ``GauParseResult``.

    Parameters
    ----------
    text:
        Full extracted text of the GAU letter (plain text, any encoding).

    Raises
    ------
    GauParseError
        If BUQW depth cannot be extracted with any confidence.
    """
    warnings: list[str] = []

    # ---- BUQW depth ---------------------------------------------------------
    buqw_depth_ft: Optional[float] = None
    for pat in _BUQW_PATTERNS:
        m = pat.search(text)
        if m:
            raw = m.group(1).replace(",", "")
            buqw_depth_ft = float(raw)
            break

    if buqw_depth_ft is None:
        raise GauParseError(
            "Could not extract BUQW depth from the GAU letter text. "
            "The letter may be a scanned image (OCR required) or use an "
            "unexpected format. Enter BUQW depth manually via operator_overrides."
        )

    # Sanity check: BUQW depth for Texas wells is typically 100–6000 ft
    if not (100.0 <= buqw_depth_ft <= 6000.0):
        warnings.append(
            f"Extracted BUQW depth {buqw_depth_ft} ft is outside the "
            f"expected range (100–6000 ft). Verify before filing."
        )

    # ---- GAU reference number -----------------------------------------------
    gau_ref: Optional[str] = None
    for pat in _REF_PATTERNS:
        m = pat.search(text)
        if m:
            gau_ref = m.group(1).strip()
            # Normalize spaces to hyphens in reference
            gau_ref = re.sub(r"\s+", "-", gau_ref)
            break

    if gau_ref is None:
        warnings.append(
            "GAU letter reference number not found. "
            "A synthetic reference will be generated from the letter date if available."
        )

    # ---- optional fields ----------------------------------------------------
    api_match = _API_PATTERN.search(text)
    api_number = api_match.group(1) if api_match else None

    date_match = _DATE_PATTERN.search(text)
    letter_date = date_match.group(0) if date_match else None

    county_match = _COUNTY_PATTERN.search(text)
    county = county_match.group(1) if county_match else None

    op_match = _OPERATOR_PATTERN.search(text)
    operator_name = op_match.group(1).strip() if op_match else None

    # ---- synthesize reference if not found ----------------------------------
    if gau_ref is None:
        parts = ["GAU"]
        if letter_date:
            # Try to convert "March 12, 2024" -> "2024-03-12"
            try:
                import datetime
                dt = datetime.datetime.strptime(letter_date, "%B %d, %Y")
                parts.append(dt.strftime("%Y-%m-%d"))
            except ValueError:
                parts.append(letter_date.replace("/", "-"))
        if county:
            parts.append(county)
        if api_number:
            parts.append(api_number.replace("-", ""))
        gau_ref = "-".join(parts) if len(parts) > 1 else "GAU-UNKNOWN"
        warnings.append(f"Synthesized GAU reference: {gau_ref}")

    # ---- special requirements -----------------------------------------------
    special_reqs: list[str] = []
    for pat, label in _SPECIAL_CASE_PHRASES:
        if pat.search(text):
            special_reqs.append(label)

    letter_type = "GAU-2" if special_reqs else "GAU-1"

    return GauParseResult(
        buqw_depth_ft=buqw_depth_ft,
        gau_letter_reference=gau_ref,
        api_number=api_number,
        county=county,
        operator_name=operator_name,
        letter_date=letter_date,
        letter_type=letter_type,
        special_requirements=special_reqs,
        warnings=warnings,
        raw_text=text,
    )


def parse_gau_pdf(pdf_bytes: bytes) -> GauParseResult:
    """Extract text from a GAU letter PDF and parse it.

    Parameters
    ----------
    pdf_bytes:
        Raw bytes of the GAU letter PDF.

    Returns
    -------
    GauParseResult

    Raises
    ------
    GauParseError
        If text extraction yields too little content (likely a scanned image)
        or if the BUQW depth cannot be found.
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise GauParseError(
            "pypdf is required for PDF parsing. "
            "Install with: pip install pypdf"
        ) from e

    reader = PdfReader(BytesIO(pdf_bytes))
    pages_text: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        pages_text.append(extracted)

    full_text = "\n".join(pages_text)

    if len(full_text.strip()) < 100:
        raise GauParseError(
            f"PDF text extraction yielded only {len(full_text.strip())} characters — "
            "the letter is likely a scanned image. "
            "Enter BUQW depth manually via operator_overrides, or use an OCR tool "
            "to convert the scan to searchable PDF first."
        )

    result = parse_gau_text(full_text)
    result.raw_text = full_text
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main() -> int:
    """Entry point: plugfile-gau <letter.pdf>"""
    p = argparse.ArgumentParser(
        prog="plugfile-gau",
        description="Extract BUQW depth and reference from a GAU letter PDF.",
    )
    p.add_argument("pdf", type=Path, help="Path to the GAU letter PDF.")
    p.add_argument("--json", action="store_true", help="Output as JSON.")
    p.add_argument("--raw-text", action="store_true",
                   help="Also print the extracted PDF text (debug).")
    args = p.parse_args()

    if not args.pdf.exists():
        sys.stderr.write(f"ERROR: file not found: {args.pdf}\n")
        return 1

    try:
        result = parse_gau_pdf(args.pdf.read_bytes())
    except GauParseError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    if args.json:
        import json
        out = {
            "buqw_depth_ft": result.buqw_depth_ft,
            "gau_letter_reference": result.gau_letter_reference,
            "api_number": result.api_number,
            "county": result.county,
            "operator_name": result.operator_name,
            "letter_date": result.letter_date,
            "letter_type": result.letter_type,
            "special_requirements": result.special_requirements,
            "warnings": result.warnings,
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"BUQW depth         : {result.buqw_depth_ft:,.0f} ft")
    print(f"GAU reference      : {result.gau_letter_reference}")
    print(f"Letter type        : {result.letter_type}")
    if result.api_number:
        print(f"API number         : {result.api_number}")
    if result.county:
        print(f"County             : {result.county}")
    if result.operator_name:
        print(f"Operator           : {result.operator_name}")
    if result.letter_date:
        print(f"Letter date        : {result.letter_date}")
    if result.special_requirements:
        print("Special requirements:")
        for req in result.special_requirements:
            print(f"  • {req}")
    if result.warnings:
        print("Warnings:")
        for w in result.warnings:
            print(f"  ! {w}")

    if args.raw_text:
        print("\n--- Extracted text ---")
        print(result.raw_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
