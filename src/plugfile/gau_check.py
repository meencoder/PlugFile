"""GW-2 / H-15 "acceptable for plugging" check.

The RRC Groundwater Advisory Unit (GAU) issues groundwater-protection
determinations (Form GW-2) for several different purposes — drilling,
surface-casing setting, injection/disposal permitting, and **plugging**.
Only a determination that is *acceptable for plugging* (the "H-15
acceptable" determination) may be attached to a W-3 / W-3A plugging filing.

Attaching the wrong GAU letter — most often the original drilling-permit
GW-2 instead of a plugging determination, or a letter for a different
well — is a top cause of district rejection (training deck pp.12-13, 34).

This module verifies a parsed GAU letter (:class:`~plugfile.gau_parser.
GauParseResult`) against the plugging requirements and returns a structured
verdict. It performs no I/O and adds no new parsing — it reasons over the
fields and ``raw_text`` the parser already produced.

Usage::

    from plugfile.gau_parser import parse_gau_pdf
    from plugfile.gau_check import check_gau_acceptability

    result = parse_gau_pdf(pdf_bytes)
    verdict = check_gau_acceptability(result, expected_api="42-371-30001")
    if not verdict.acceptable_for_plugging:
        print("Blocked:", verdict.blocking_issues)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from .gau_parser import GauParseResult, parse_gau_text


CheckStatus = Literal["pass", "warn", "fail"]
Confidence = Literal["high", "medium", "low"]


# ---- phrase libraries -------------------------------------------------------

# Language that affirmatively marks a GAU determination as usable for plugging.
_PLUGGING_ACCEPT_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"acceptable\s+for\s+plugging", re.IGNORECASE),
    re.compile(r"approved\s+for\s+plugging", re.IGNORECASE),
    re.compile(r"for\s+(?:the\s+)?plugging\s+of\s+(?:this\s+)?(?:the\s+)?well", re.IGNORECASE),
    re.compile(r"plugging\s+(?:purposes|operations)", re.IGNORECASE),
    re.compile(r"for\s+plugging\s+purposes", re.IGNORECASE),
    re.compile(r"\bH[-\s]?15\b", re.IGNORECASE),
    re.compile(r"to\s+be\s+plugged", re.IGNORECASE),
)

# Language that suggests the letter was issued for a *different* purpose.
# Only treated as blocking when NO plugging-acceptance phrase is present.
# The Form GW-2 "Purpose:" field is the strongest signal — a determination
# issued for "New Production Well" / "Recompletion" / injection is NOT a
# plugging determination and must not be attached to a W-3 / W-3A.
_WRONG_PURPOSE_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"Purpose\s*:\s*New\s+(?:Production|Drill)", re.IGNORECASE),
     "is a new-well determination (Purpose: New Production Well), not a plugging determination"),
    (re.compile(r"Purpose\s*:\s*Recompletion", re.IGNORECASE),
     "is a recompletion determination"),
    (re.compile(r"Purpose\s*:\s*(?:Injection|Disposal)", re.IGNORECASE),
     "is an injection/disposal determination"),
    (re.compile(r"for\s+(?:the\s+)?(?:purpose\s+of\s+)?drilling", re.IGNORECASE),
     "issued for drilling"),
    (re.compile(r"injection\s+well\s+permit", re.IGNORECASE),
     "issued for injection-well permitting"),
    (re.compile(r"disposal\s+well\s+permit", re.IGNORECASE),
     "issued for disposal-well permitting"),
    (re.compile(r"prior\s+to\s+(?:setting|running)\s+surface\s+casing", re.IGNORECASE),
     "is a surface-casing-setting determination"),
)

_BUQW_MIN_FT = 100.0
_BUQW_MAX_FT = 6000.0


# ---- output types -----------------------------------------------------------

@dataclass
class GauCheckItem:
    """One named check with a pass/warn/fail status and explanation."""
    name: str
    status: CheckStatus
    detail: str


@dataclass
class GauAcceptabilityResult:
    """Verdict on whether a GAU letter is acceptable for a plugging filing."""
    acceptable_for_plugging: bool
    confidence: Confidence
    letter_type: str                       # "GAU-1" | "GAU-2"
    buqw_depth_ft: Optional[float]
    gau_letter_reference: Optional[str]
    found_api: Optional[str]
    expected_api: Optional[str]
    api_match: Optional[bool]              # None when expected_api not supplied
    has_special_requirements: bool
    special_requirements: list[str]
    checks: list[GauCheckItem]
    warnings: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "acceptable_for_plugging": self.acceptable_for_plugging,
            "confidence": self.confidence,
            "letter_type": self.letter_type,
            "buqw_depth_ft": self.buqw_depth_ft,
            "gau_letter_reference": self.gau_letter_reference,
            "found_api": self.found_api,
            "expected_api": self.expected_api,
            "api_match": self.api_match,
            "has_special_requirements": self.has_special_requirements,
            "special_requirements": self.special_requirements,
            "warnings": self.warnings,
            "blocking_issues": self.blocking_issues,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail}
                for c in self.checks
            ],
        }


# ---- helpers ----------------------------------------------------------------

def _norm_api(api: str | None) -> str | None:
    """Normalise an API number to digits only for comparison."""
    if not api:
        return None
    return re.sub(r"\D", "", api)


# ---- public API -------------------------------------------------------------

def check_gau_acceptability(
    result: GauParseResult,
    *,
    expected_api: str | None = None,
) -> GauAcceptabilityResult:
    """Assess whether *result* is a GAU determination acceptable for plugging.

    Args:
        result:        A parsed GAU letter from :func:`parse_gau_pdf` /
                       :func:`parse_gau_text`.
        expected_api:  The API number of the well being plugged. When given,
                       the letter's own API number is cross-checked against it
                       so a letter for the wrong well is caught.

    Returns:
        A :class:`GauAcceptabilityResult`. ``acceptable_for_plugging`` is
        False only when at least one check fails (a blocking issue);
        ambiguous letters pass with reduced ``confidence`` and a warning.
    """
    text = result.raw_text or ""
    checks: list[GauCheckItem] = []
    warnings: list[str] = []
    blocking: list[str] = []

    # ── check 1: BUQW depth present and sane ──────────────────────────────────
    depth = result.buqw_depth_ft
    if depth is None:
        checks.append(GauCheckItem(
            "buqw_depth", "fail",
            "No base-of-usable-quality-water (BUQW) depth found in the letter.",
        ))
        blocking.append("GAU letter has no readable BUQW depth.")
    elif not (_BUQW_MIN_FT <= depth <= _BUQW_MAX_FT):
        checks.append(GauCheckItem(
            "buqw_depth", "warn",
            f"BUQW depth {depth:,.0f} ft is outside the typical "
            f"{int(_BUQW_MIN_FT)}–{int(_BUQW_MAX_FT)} ft range — verify the letter.",
        ))
        warnings.append(f"BUQW depth {depth:,.0f} ft is unusual; double-check it.")
    else:
        checks.append(GauCheckItem(
            "buqw_depth", "pass",
            f"BUQW depth {depth:,.0f} ft is present and within the expected range.",
        ))

    # ── check 2: plugging-purpose / H-15 acceptance ──────────────────────────
    plugging_found = any(p.search(text) for p in _PLUGGING_ACCEPT_PATTERNS)
    wrong_hits = [label for pat, label in _WRONG_PURPOSE_PATTERNS if pat.search(text)]

    if plugging_found:
        checks.append(GauCheckItem(
            "plugging_purpose", "pass",
            "Letter states it is acceptable for plugging (H-15 / plugging "
            "language found).",
        ))
        purpose_confidence: Confidence = "high"
    elif wrong_hits:
        reason = "; ".join(sorted(set(wrong_hits)))
        checks.append(GauCheckItem(
            "plugging_purpose", "fail",
            f"Letter appears to have been {reason}, and contains no "
            "'acceptable for plugging' / H-15 language. This is likely the "
            "wrong GAU determination for a plugging filing.",
        ))
        blocking.append(
            f"GAU letter purpose looks wrong for plugging ({reason})."
        )
        purpose_confidence = "high"
    else:
        checks.append(GauCheckItem(
            "plugging_purpose", "warn",
            "Could not confirm explicit 'acceptable for plugging' / H-15 "
            "language. Verify this determination was issued for plugging, not "
            "drilling or injection.",
        ))
        warnings.append(
            "GAU letter does not clearly state it is acceptable for plugging — "
            "verify before filing."
        )
        purpose_confidence = "low"

    # ── check 3: API cross-check ─────────────────────────────────────────────
    found_api = result.api_number
    api_match: Optional[bool] = None
    if expected_api:
        nf, ne = _norm_api(found_api), _norm_api(expected_api)
        if nf is None:
            api_match = None
            checks.append(GauCheckItem(
                "api_match", "warn",
                "GAU letter contains no API number to cross-check against the "
                f"well being plugged ({expected_api}).",
            ))
            warnings.append("Could not cross-check the GAU letter's API number.")
        elif nf == ne:
            api_match = True
            checks.append(GauCheckItem(
                "api_match", "pass",
                f"GAU letter API matches the well being plugged ({expected_api}).",
            ))
        else:
            api_match = False
            checks.append(GauCheckItem(
                "api_match", "fail",
                f"GAU letter is for API {found_api}, but you are plugging "
                f"{expected_api}. This is the wrong letter.",
            ))
            blocking.append(
                f"GAU letter API {found_api} does not match well {expected_api}."
            )

    # ── check 4: special-case (GAU-2) requirements ───────────────────────────
    has_special = bool(result.special_requirements)
    if has_special:
        reqs = "; ".join(result.special_requirements)
        checks.append(GauCheckItem(
            "special_requirements", "warn",
            f"GAU-2 special-case letter — §3.14(d) requirements apply: {reqs}. "
            "Make sure the plug program includes the required isolation/BUQW "
            "plugs.",
        ))
        warnings.append(
            "GAU-2 letter carries special §3.14(d) plugging requirements — "
            "confirm they are reflected in the plug program."
        )
    else:
        checks.append(GauCheckItem(
            "special_requirements", "pass",
            "Standard GAU-1 letter — no special §3.14(d) plugging requirements.",
        ))

    # ── check 5: letter date present ─────────────────────────────────────────
    if result.letter_date:
        checks.append(GauCheckItem(
            "letter_date", "pass",
            f"Letter is dated {result.letter_date}.",
        ))
    else:
        checks.append(GauCheckItem(
            "letter_date", "warn",
            "No letter date found — confirm the determination is current.",
        ))
        warnings.append("GAU letter date not found; confirm it is current.")

    # ── overall verdict + confidence ─────────────────────────────────────────
    acceptable = len(blocking) == 0

    if not acceptable:
        confidence: Confidence = "high"          # we're confident it's wrong
    elif purpose_confidence == "low":
        confidence = "low"                       # passed but couldn't confirm purpose
    elif any(c.status == "warn" for c in checks):
        confidence = "medium"
    else:
        confidence = "high"

    return GauAcceptabilityResult(
        acceptable_for_plugging=acceptable,
        confidence=confidence,
        letter_type=result.letter_type,
        buqw_depth_ft=result.buqw_depth_ft,
        gau_letter_reference=result.gau_letter_reference,
        found_api=found_api,
        expected_api=expected_api,
        api_match=api_match,
        has_special_requirements=has_special,
        special_requirements=list(result.special_requirements),
        checks=checks,
        warnings=warnings,
        blocking_issues=blocking,
    )


def check_gau_text(
    text: str,
    *,
    expected_api: str | None = None,
) -> GauAcceptabilityResult:
    """Parse *text* as a GAU letter and run the acceptability check.

    Convenience wrapper for tests / callers that already have letter text.
    """
    return check_gau_acceptability(parse_gau_text(text), expected_api=expected_api)
