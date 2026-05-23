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
import os
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

# BUQW depth — patterns cover synthetic letters + real RRC Form GW-2 language
_BUQW_PATTERNS: list[re.Pattern] = [
    # "base of usable quality water ... 1,500 feet" (full phrase, hyphen or space)
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
    # Real Form GW-2: "estimated to occur at a depth of 1550 feet below the land surface"
    re.compile(
        r"estimated\s+to\s+occur\s+at\s+a\s+depth\s+of\s+(\d{1,2},\d{3}|\d{2,5})\s*(?:feet|ft)\b",
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
    # Fallback: 3-5 digit number + feet near "water" or "surface"
    re.compile(
        r"(\d{1,2},\d{3}|\d{3,5})\s*(?:feet|ft)\b[^.]{0,80}?"
        r"(?:water|groundwater|usable|land\s+surface)",
        re.IGNORECASE | re.DOTALL,
    ),
]

# GAU letter reference number.
# Supports three real RRC formats:
#   "GAU-2024-03-12-Pecos-21874"   (advisory letter, date+county+seq)
#   "GAU Number: 208803"            (Form GW-2 Groundwater Protection Determination)
#   "GAU 2024-03-12"                (older date-only format)
_REF_PATTERNS: list[re.Pattern] = [
    # Explicit "Reference:" / "Letter No." label before full date-county ref
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
    # Real Form GW-2: "GAU Number: 208803"
    re.compile(
        r"GAU\s+Number[:\s]+(\d{4,7})\b",
        re.IGNORECASE,
    ),
]

# API number in text
_API_PATTERN = re.compile(r"\b(42-\d{3}-\d{5})\b")

_MONTHS_ABBR = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)
_MONTH_RE = "|".join(_MONTHS_ABBR)

# Date — three formats:
#   "March 12, 2024"    (month-first, comma)
#   "25 September 2018" (day-first, Form GW-2)
#   "MM/DD/YYYY"
_DATE_PATTERN = re.compile(
    r"(?:" + _MONTH_RE + r")\s+\d{1,2},?\s+\d{4}"   # month-first
    r"|\d{1,2}\s+(?:" + _MONTH_RE + r")\s+\d{4}"     # day-first (Form GW-2)
    r"|\d{1,2}/\d{1,2}/\d{4}",                        # MM/DD/YYYY
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

# County — two layouts:
#   "Pecos County"    (name before keyword — standard letters)
#   "County: POLK"    (keyword before name — Form GW-2)
#
# The label-first alternative captures only one word so that it does not
# consume multi-word values like "Pecos County" (→ "Pecos") or bleed across
# a newline into an address line (→ "POLK\n   HOUSTON").  The name-first
# alternative uses [ \t]+ (horizontal whitespace only) in the optional word
# separator to prevent newline-crossing as well.
_COUNTY_PATTERN = re.compile(
    r"([A-Z][a-zA-Z]+(?:[ \t]+[A-Z][a-zA-Z]+)?)\s+County"   # name-first
    r"|County[ \t]*[:\s]+([A-Z][A-Za-z]+)",                   # label-first (one word)
    re.IGNORECASE,
)

# Operator — "Operator:" label or "Attention:" (Form GW-2 addressee line)
_OPERATOR_PATTERN = re.compile(
    r"(?:Operator|Attention)\s*[:\s]+([^\n,\d]{3,60})",
    re.IGNORECASE,
)


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
            # Normalize spaces to hyphens
            gau_ref = re.sub(r"\s+", "-", gau_ref)
            # Form GW-2: bare numeric ID → prefix with "GAU-"
            if re.match(r"^\d+$", gau_ref):
                gau_ref = f"GAU-{gau_ref}"
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
    if county_match:
        # group(1) = name-first layout; group(2) = label-first (Form GW-2)
        county = (county_match.group(1) or county_match.group(2) or "").strip()
    else:
        county = None

    op_match = _OPERATOR_PATTERN.search(text)
    operator_name = op_match.group(1).strip() if op_match else None

    # ---- synthesize reference if not found ----------------------------------
    if gau_ref is None:
        parts = ["GAU"]
        if letter_date:
            # Try multiple date formats: "March 12, 2024", "March 12 2024",
            # "25 September 2018" (Form GW-2 day-first), "MM/DD/YYYY"
            import datetime
            _date_fmts = ("%B %d, %Y", "%B %d %Y", "%d %B %Y", "%m/%d/%Y")
            for _fmt in _date_fmts:
                try:
                    dt = datetime.datetime.strptime(letter_date, _fmt)
                    parts.append(dt.strftime("%Y-%m-%d"))
                    break
                except ValueError:
                    continue
            else:
                parts.append(letter_date.replace("/", "-").replace(" ", "-"))
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


_DOTENV_LOADED = False


def _load_dotenv() -> None:
    """Populate os.environ from a ``.env`` file if one exists.

    Dependency-free loader (no python-dotenv).  Searches, in order:
      1. each directory from the current working dir up to the filesystem root
      2. the package's repo root (where ``pyproject.toml`` lives)
    for a file named ``.env``.  Parses simple ``KEY=VALUE`` lines (``#`` comments
    and blank lines ignored; surrounding quotes stripped).  Existing environment
    variables always win — the ``.env`` only *fills gaps* so a real shell var is
    never overridden.

    Runs at most once per process (idempotent via the ``_DOTENV_LOADED`` flag).
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    candidates: list[Path] = []
    cwd = Path.cwd()
    candidates.extend([cwd, *cwd.parents])
    # repo root relative to this file: src/plugfile/gau_parser.py -> repo root
    candidates.append(Path(__file__).resolve().parents[2])

    seen: set[Path] = set()
    for d in candidates:
        if d in seen:
            continue
        seen.add(d)
        env_path = d / ".env"
        if not env_path.is_file():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            continue
        return  # first .env found wins


def _pick_ocr_model(client) -> str:  # type: ignore[valid-type]
    """Return the best available Claude model for OCR.

    OCR of GAU letters extracts *safety-critical numbers* (BUQW depth, GAU
    reference) that land on a regulatory filing.  Accuracy matters more than
    cost here — a single letter is read once — so we prefer Sonnet over Haiku.
    Haiku mis-transcribes small/scanned digits (observed: 1550→1650), which is
    unacceptable for a W-3.

    Priority:
      1. ``PLUGFILE_LLM_MODEL`` env var (explicit user override).
      2. Auto-discover via ``client.models.list()`` — prefers a sonnet-class
         model, then opus, then haiku as a last resort.
         Works with any Anthropic SDK version that exposes the Models API.
      3. Hard-coded fallback (may fail if that model is since deprecated).
    """
    import os

    override = os.environ.get("PLUGFILE_LLM_MODEL", "").strip()
    if override:
        return override

    # Auto-discover: prefer the most accurate model for digit OCR.
    try:
        available_ids = [m.id for m in client.models.list().data]
        for preference in ("sonnet", "opus", "haiku", "claude"):
            found = next(
                (mid for mid in available_ids if preference in mid.lower()), None
            )
            if found:
                return found
    except Exception:
        pass  # SDK too old or no network — fall through to hardcoded name

    return "claude-sonnet-4-6"  # last resort; set PLUGFILE_LLM_MODEL to override


def _ocr_pdf_with_claude(pdf_bytes: bytes) -> str:
    """Send a scanned GAU letter PDF to Claude for OCR transcription.

    Used as a fallback when pypdf text extraction yields < 100 characters
    (i.e. the letter is a scanned image rather than a selectable-text PDF).

    Requires ``ANTHROPIC_API_KEY`` to be set.  If absent, raises
    ``GauParseError`` with a user-friendly message directing the operator
    to enter the BUQW depth manually.

    Model selection (highest priority first):
      1. ``PLUGFILE_LLM_MODEL`` env var
      2. Auto-discovered via ``client.models.list()`` (prefers Sonnet for
         digit accuracy)
      3. Hardcoded ``claude-sonnet-4-6`` as last resort

    The function sends the raw PDF bytes as a base64-encoded document,
    asking Claude to transcribe all visible text.  The returned text is then
    parsed by the normal ``parse_gau_text`` regex pipeline.

    The ``ANTHROPIC_API_KEY`` is read from the process environment, falling
    back to a ``.env`` file at the repo root (see ``_load_dotenv``) so the
    feature does not silently break when a shell is started without the var.
    """
    import base64
    import os

    _load_dotenv()  # populate ANTHROPIC_API_KEY from .env if not already set
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise GauParseError(
            "This GAU letter is a scanned image — pypdf extracted 0 characters. "
            "Set ANTHROPIC_API_KEY (in your environment or a .env file at the "
            "repo root) to enable automatic OCR, or enter the BUQW depth "
            "manually in the app."
        )

    try:
        import anthropic as _ant
    except ImportError as exc:
        raise GauParseError(
            "anthropic package required for OCR of scanned GAU letters. "
            "pip install anthropic — or enter BUQW depth manually."
        ) from exc

    client = _ant.Anthropic()
    model = _pick_ocr_model(client)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a Texas Railroad Commission Groundwater Advisory Unit "
                            "letter (Form GW-2 or similar RRC groundwater determination). "
                            "Transcribe ALL visible text exactly as it appears — every field "
                            "label and its value on the same line. "
                            "Include: GAU Number, Date Issued, County, API Number, Operator, "
                            "Lease Name, Well Number, and the full body paragraph(s) describing "
                            "the base of usable-quality water depth. "
                            "Do not summarize. Transcribe only."
                        ),
                    },
                ],
            }],
        )
    except Exception as exc:
        raise GauParseError(
            f"Claude OCR call failed ({exc}). "
            f"Model used: {model!r}. "
            "Override with: $env:PLUGFILE_LLM_MODEL = 'your-model-id'"
        ) from exc

    return response.content[0].text


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

    ocr_used = False
    if len(full_text.strip()) < 100:
        # Scanned image — try Claude vision OCR before giving up.
        # _ocr_pdf_with_claude raises GauParseError if ANTHROPIC_API_KEY not set.
        full_text = _ocr_pdf_with_claude(pdf_bytes)
        ocr_used = True

    result = parse_gau_text(full_text)
    result.raw_text = full_text
    if ocr_used:
        result.warnings.insert(0, "Text extracted via Claude OCR (scanned PDF). Verify depth before filing.")
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
