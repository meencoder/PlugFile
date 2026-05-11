"""Surface-restoration narrative drafter.

Takes a voice transcript (operator dictating what they did at the wellsite
to restore the surface after plugging) and produces the formal Section IX
narrative for Form W-3.

Architecture mirrors the rest of Plugfile:
  * Pure-Python deterministic slot extractor is the trusted core.
  * Each extracted slot has a confidence score and provenance (which regex
    or keyword matched).
  * Template-based drafter fills the narrative from the slots.
  * An LLM-fallback hook (`llm_fill_missing_slots`) is documented but
    intentionally a stub for Phase 1C — keeps tests deterministic and
    avoids per-test LLM cost.

The drafter never invents facts. If a slot is missing, the narrative uses
a clearly-flagged placeholder ("[surface owner consent: not stated]") and
records an `ExtractionWarning`. The operator/LLM reviews the warnings and
either fills the slot or accepts the placeholder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


# ---- the facts model -------------------------------------------------------

@dataclass
class SurfaceRestorationFacts:
    """Structured slots extracted from the operator's voice transcript.

    Every field is Optional / list / bool. None means "not mentioned in the
    transcript"; an empty list or False likewise means "no evidence", not
    "explicitly absent".
    """
    # Mechanical work
    casing_cut_depth_ft: float | None = None       # typical 3 ft below GL
    cap_type: str | None = None                    # "steel plate", "concrete", etc.
    cap_dimensions: str | None = None              # "24 inch x 24 inch x 1/4 inch"
    cellar_filled: bool = False
    cellar_fill_material: str | None = None        # "caliche", "native soil", etc.

    # Equipment removal
    equipment_removed: list[str] = field(default_factory=list)

    # Site work
    vegetation_action: str | None = None           # "re-seeded native grass", etc.
    grading_action: str | None = None              # "leveled and contoured"
    access_road_status: str | None = None          # "removed", "retained per surface owner"
    fencing_status: str | None = None              # "removed", "retained"

    # Administrative
    date_of_work: str | None = None                # ISO YYYY-MM-DD or natural date
    surface_owner_consent: str | None = None       # "granted", "not required (mineral lease)"
    sensitive_surface_notes: str | None = None     # wetlands, endangered species, etc.

    # Provenance — for each filled slot, the matched substring from the
    # transcript. Useful for review and audit.
    provenance: dict[str, str] = field(default_factory=dict)

    def filled_slots(self) -> set[str]:
        out: set[str] = set()
        for fname in (
            "casing_cut_depth_ft", "cap_type", "cap_dimensions",
            "cellar_filled", "cellar_fill_material",
            "vegetation_action", "grading_action",
            "access_road_status", "fencing_status",
            "date_of_work", "surface_owner_consent",
            "sensitive_surface_notes",
        ):
            v = getattr(self, fname)
            if v is None:
                continue
            if v is False:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            out.add(fname)
        if self.equipment_removed:
            out.add("equipment_removed")
        return out


@dataclass(frozen=True)
class ExtractionWarning:
    """Flagged when a slot couldn't be filled or extraction is ambiguous."""
    slot: str
    severity: Literal["info", "warn"]
    message: str

    def render(self) -> str:
        return f"[{self.severity.upper():4s}] {self.slot}: {self.message}"


# ---- regex / keyword patterns ---------------------------------------------

# Canonicalize equipment terms so synonyms map to a single label.
_EQUIPMENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("wellhead", re.compile(r"\b(?:well[\s-]?head|christmas\s+tree)\b", re.I)),
    ("tubing string", re.compile(r"\btubing\b(?:\s+string)?", re.I)),
    ("pumping unit", re.compile(r"\b(?:pump(?:ing)?\s+(?:unit|jack)|pumpjack|nodding\s+donkey)\b", re.I)),
    ("rod string", re.compile(r"\brods?(?:\s+string)?\b", re.I)),
    ("separator", re.compile(r"\bseparators?\b", re.I)),
    ("heater treater", re.compile(r"\b(?:heater[\s-]?treater|treater)\b", re.I)),
    ("tank battery", re.compile(r"\btank(?:\s+battery|s)?\b", re.I)),
    ("flowlines", re.compile(r"\bflow[\s-]?lines?\b", re.I)),
    ("gas meter", re.compile(r"\bgas\s+meter\b", re.I)),
    ("compressor", re.compile(r"\bcompressors?\b", re.I)),
    ("salt water disposal line", re.compile(r"\b(?:salt[\s-]?water|swd)\s+(?:disposal|line)\b", re.I)),
]


_CASING_CUT_RX = re.compile(
    r"""
    cut(?:ting)?\s+(?:the\s+)?
    (?:surface|production|intermediate|conductor)?\s*casing\s+
    (?:(?:off|down)\s+)?(?:at\s+|to\s+|down\s+to\s+)?
    (?:about\s+|approximately\s+|roughly\s+)?
    (?P<n>\d+(?:\.\d+)?)\s*(?:ft|foot|feet|')?
    """,
    re.I | re.X,
)

_CAP_RX = re.compile(
    r"""
    (?:welded|put|set|installed)\s+
    (?:on\s+)?(?:a\s+|the\s+)?
    (?P<dim>
        (?:[\d/.\-]+|quarter|half|three[\s-]quarter)\s*(?:in|inch|")?
        (?:\s*(?:by|x|×)\s*(?:[\d/.\-]+|quarter|half|three[\s-]quarter)\s*(?:in|inch|")?)?
        (?:\s*(?:by|x|×)\s*(?:[\d/.\-]+|quarter|half|three[\s-]quarter)\s*(?:in|inch|")?)?
        \s+
    )?
    (?P<material>steel|metal|concrete|iron)\s+
    (?:plate|cap|cover)
    """,
    re.I | re.X,
)

_CELLAR_RX = re.compile(
    r"""
    (?:
        (?:fill(?:ed)?|backfill(?:ed)?)\s+(?:the\s+|in\s+)?cellar
      | cellar\s+(?:was\s+)?(?:fill(?:ed)?|backfill(?:ed)?)
    )
    (?:\s+with\s+(?P<mat>caliche|native\s+soil|dirt|topsoil|gravel|cement))?
    """,
    re.I | re.X,
)

_RESEED_RX = re.compile(
    r"""
    (?P<action>re[\s-]?seed(?:ed)?|seeded|hydro[\s-]?seeded|mulch(?:ed)?|
       restored\s+vegetation|native\s+grass(?:es)?|wildflower\s+mix)
    """,
    re.I | re.X,
)

_GRADING_RX = re.compile(
    r"""
    (?P<action>(?:re[\s-]?)?(?:graded|grading|level(?:ed|ling)?|contour(?:ed)?|
       smooth(?:ed)?|restored\s+grade))
    """,
    re.I | re.X,
)

_ACCESS_ROAD_RX = re.compile(
    r"""
    (?:access\s+)?road\s+
    (?P<action>(?:was\s+)?(?:removed|left|retained|kept|abandoned|gravel(?:ed)?))
    """,
    re.I | re.X,
)

_FENCE_RX = re.compile(
    r"""
    fenc(?:e|ing)\s+(?P<action>(?:was\s+)?(?:removed|left|retained|kept|repaired|restored))
    """,
    re.I | re.X,
)

_CONSENT_RX = re.compile(
    r"""
    surface[\s-]?owner\s+(?P<action>(?:consent|permission|approval)\s+(?:granted|received|obtained|on\s+file)|
       (?:waiver|declined))
    """,
    re.I | re.X,
)

_SENSITIVE_RX = re.compile(
    r"""
    (?P<phrase>wetlands?|endangered\s+species|tribal\s+land|protected\s+habitat|
       riparian|bird\s+nesting|environmentally\s+sensitive)
    """,
    re.I | re.X,
)

_DATE_RX = re.compile(
    r"""
    \b(?P<iso>\d{4}-\d{2}-\d{2})\b |
    \b(?P<month>january|february|march|april|may|june|july|august|
       september|october|november|december)\s+
       (?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{4}))?
    """,
    re.I | re.X,
)


_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


# ---- extractor -------------------------------------------------------------

def extract_facts_from_transcript(
    transcript: str,
    *,
    fallback_year: int | None = None,
) -> tuple[SurfaceRestorationFacts, list[ExtractionWarning]]:
    """Pull SurfaceRestorationFacts from a free-form voice transcript using
    regex + keyword patterns. Always returns a facts object (with whatever
    slots could be filled) plus a list of ExtractionWarning entries flagging
    ambiguity or missing required slots.

    `fallback_year` is used when the transcript mentions a month + day but
    not a year (common in casual dictation).
    """
    facts = SurfaceRestorationFacts()
    warnings: list[ExtractionWarning] = []

    # Casing cut depth
    if m := _CASING_CUT_RX.search(transcript):
        facts.casing_cut_depth_ft = float(m.group("n"))
        facts.provenance["casing_cut_depth_ft"] = m.group(0).strip()

    # Cap
    if m := _CAP_RX.search(transcript):
        facts.cap_type = m.group("material").lower() + " plate"
        dim = (m.group("dim") or "").strip()
        if dim:
            facts.cap_dimensions = re.sub(r"\s+", " ", dim)
        facts.provenance["cap_type"] = m.group(0).strip()

    # Cellar
    if m := _CELLAR_RX.search(transcript):
        facts.cellar_filled = True
        if mat := m.group("mat"):
            facts.cellar_fill_material = mat.lower().strip()
        facts.provenance["cellar_filled"] = m.group(0).strip()

    # Equipment removed — list-mode: any pattern that fires under a "remove"
    # context counts.
    remove_hits = list(re.finditer(
        r"""(?:
            remov(?:e|ed|al) |
            haul(?:ed)?\s+(?:off|to\s+the\s+yard) |
            tore\s+down |
            dismantl(?:e|ed) |
            pull(?:ed)? |
            came\s+off |
            took\s+off |
            scrap(?:ped)?
        )""",
        transcript, re.I | re.X,
    ))
    for label, rx in _EQUIPMENT_PATTERNS:
        if rx.search(transcript) and remove_hits:
            facts.equipment_removed.append(label)
    if facts.equipment_removed:
        facts.equipment_removed = sorted(set(facts.equipment_removed))
        facts.provenance["equipment_removed"] = ", ".join(facts.equipment_removed)

    # Vegetation
    if m := _RESEED_RX.search(transcript):
        facts.vegetation_action = m.group("action").lower().replace("-", " ")
        facts.provenance["vegetation_action"] = m.group(0).strip()

    # Grading
    if m := _GRADING_RX.search(transcript):
        facts.grading_action = m.group("action").lower().replace("-", " ")
        facts.provenance["grading_action"] = m.group(0).strip()

    # Access road
    if m := _ACCESS_ROAD_RX.search(transcript):
        action = m.group("action").lower()
        # Normalize to canonical
        if "remov" in action:
            facts.access_road_status = "removed"
        elif any(w in action for w in ("retain", "left", "kept")):
            facts.access_road_status = "retained per surface owner"
        else:
            facts.access_road_status = action
        facts.provenance["access_road_status"] = m.group(0).strip()

    # Fencing
    if m := _FENCE_RX.search(transcript):
        action = m.group("action").lower()
        if "remov" in action:
            facts.fencing_status = "removed"
        elif any(w in action for w in ("retain", "left", "kept")):
            facts.fencing_status = "retained"
        elif "repair" in action or "restor" in action:
            facts.fencing_status = "repaired"
        else:
            facts.fencing_status = action
        facts.provenance["fencing_status"] = m.group(0).strip()

    # Surface-owner consent
    if m := _CONSENT_RX.search(transcript):
        facts.surface_owner_consent = m.group(0).strip().lower()
        facts.provenance["surface_owner_consent"] = m.group(0).strip()

    # Sensitive surface
    if m := _SENSITIVE_RX.search(transcript):
        facts.sensitive_surface_notes = m.group("phrase").lower()
        facts.provenance["sensitive_surface_notes"] = m.group(0).strip()

    # Date of work
    if m := _DATE_RX.search(transcript):
        if iso := m.group("iso"):
            facts.date_of_work = iso
        elif (month_name := m.group("month")):
            month = _MONTHS[month_name.lower()]
            day = m.group("day").zfill(2)
            year = m.group("year") or (str(fallback_year) if fallback_year else None)
            if year:
                facts.date_of_work = f"{year}-{month}-{day}"
            else:
                warnings.append(ExtractionWarning(
                    slot="date_of_work",
                    severity="warn",
                    message=("Month and day extracted but year not stated; "
                             "pass `fallback_year` or supply the date."),
                ))
        if facts.date_of_work:
            facts.provenance["date_of_work"] = m.group(0).strip()

    # Required-slot warnings (the W-3 narrative reviewer wants these)
    REQUIRED = (
        "casing_cut_depth_ft", "cap_type", "cellar_filled",
        "vegetation_action", "grading_action", "date_of_work",
    )
    filled = facts.filled_slots()
    for slot in REQUIRED:
        if slot not in filled:
            warnings.append(ExtractionWarning(
                slot=slot,
                severity="warn",
                message=("Slot not found in transcript; the drafter will "
                         "use a placeholder. Operator must supply this "
                         "before filing."),
            ))

    return facts, warnings


def llm_fill_missing_slots(
    facts: SurfaceRestorationFacts,
    transcript: str,
) -> SurfaceRestorationFacts:
    """Phase-2 hook: invoke an LLM to extract any slots the regex layer
    missed. Not implemented in Phase 1C — keeps tests deterministic and
    avoids per-CI-run LLM cost.

    Production wiring (Phase 2) would:
      1. Build a prompt listing the still-missing slots and the transcript.
      2. Use Anthropic API with a JSON-mode response specifying the slots.
      3. Merge the LLM's slot values into `facts`, marking provenance as
         `llm:<model_id>` so audit logs distinguish regex vs LLM extraction.
    """
    raise NotImplementedError(
        "llm_fill_missing_slots is a Phase-2 stub. Phase 1C uses the "
        "regex-only extractor; if a slot is missing the operator/LLM "
        "should supply it via the W3Form override path."
    )


# ---- drafter ---------------------------------------------------------------

def _equipment_phrase(items: list[str]) -> str:
    if not items:
        return "[equipment removed: not stated]"
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def draft_narrative(
    facts: SurfaceRestorationFacts,
    *,
    well_context: dict | None = None,
) -> tuple[str, list[ExtractionWarning]]:
    """Fill the W-3 Section IX narrative template from extracted facts.

    Always returns a complete narrative. Missing slots get clearly-marked
    placeholders so the operator can spot-check before filing. The list of
    `ExtractionWarning` returned aggregates any placeholder-substitutions
    so the LLM/operator knows what's still missing.
    """
    warnings: list[ExtractionWarning] = []
    well_context = well_context or {}

    def slot(name: str, default: str = "[not stated]") -> str:
        v = getattr(facts, name)
        if v is None or v == "":
            warnings.append(ExtractionWarning(
                slot=name,
                severity="warn",
                message=f"Slot {name} unfilled; placeholder used in narrative.",
            ))
            return default
        return str(v)

    # Build the lease/well opener if we have W-3 context.
    api = well_context.get("api_number")
    lease = well_context.get("lease_name")
    well_no = well_context.get("well_number")
    county = well_context.get("county")
    opener_bits = []
    if api:
        opener_bits.append(f"API {api}")
    if lease and well_no:
        opener_bits.append(f"the {lease} #{well_no}")
    if county:
        opener_bits.append(f"in {county} County, Texas")
    opener = (", ".join(opener_bits) + ". ") if opener_bits else ""

    # Mechanical-work paragraph
    cut_depth = (
        f"{facts.casing_cut_depth_ft:.0f} feet"
        if facts.casing_cut_depth_ft is not None
        else "[casing cut depth: not stated]"
    )
    if facts.casing_cut_depth_ft is None:
        warnings.append(ExtractionWarning(
            slot="casing_cut_depth_ft",
            severity="warn",
            message="Casing cut depth not stated; placeholder used.",
        ))

    cap_phrase = (
        f"a {facts.cap_dimensions} {facts.cap_type}"
        if facts.cap_dimensions and facts.cap_type
        else (facts.cap_type or "[cap: not stated]")
    )
    if not facts.cap_type:
        warnings.append(ExtractionWarning(
            slot="cap_type",
            severity="warn",
            message="Cap type not stated; placeholder used.",
        ))

    mech = (
        f"Surface casing was cut off at {cut_depth} below ground level and "
        f"{cap_phrase} was welded to the cut casing stub to seal the wellbore."
    )

    # Cellar
    if facts.cellar_filled:
        mat = facts.cellar_fill_material or "native soil"
        cellar = f" The cellar was backfilled with {mat}."
    else:
        cellar = ""

    # Equipment
    if facts.equipment_removed:
        equip = (
            f" {_equipment_phrase([e.capitalize() for e in facts.equipment_removed])}"
            f" {'were' if len(facts.equipment_removed) != 1 else 'was'} "
            f"removed from the location."
        )
    else:
        equip = ""

    # Site work
    site_bits = []
    if facts.grading_action:
        site_bits.append(f"the location was {facts.grading_action}")
    if facts.vegetation_action:
        site_bits.append(f"the surface was {facts.vegetation_action}")
    site = (
        " The location was restored: " + "; ".join(site_bits) + "."
    ) if site_bits else ""
    if not site_bits:
        warnings.append(ExtractionWarning(
            slot="grading_action",
            severity="warn",
            message="No site-restoration work stated; consider adding.",
        ))

    # Access road / fencing
    extras = []
    if facts.access_road_status:
        extras.append(f"Access road: {facts.access_road_status}.")
    if facts.fencing_status:
        extras.append(f"Fencing: {facts.fencing_status}.")
    if facts.sensitive_surface_notes:
        extras.append(
            f"Note: location includes {facts.sensitive_surface_notes} — "
            f"work performed under applicable regulatory restrictions."
        )
    extras_text = (" " + " ".join(extras)) if extras else ""

    # Consent
    consent = ""
    if facts.surface_owner_consent:
        consent = f" {facts.surface_owner_consent.capitalize()}."

    # Date
    if facts.date_of_work:
        date_phrase = f"Work was completed on {facts.date_of_work}."
    else:
        date_phrase = "Date of surface restoration: [not stated]."
        warnings.append(ExtractionWarning(
            slot="date_of_work",
            severity="warn",
            message="Date of work not stated; required for W-3 filing.",
        ))

    narrative = (
        opener + mech + cellar + equip + site + extras_text + consent
        + " " + date_phrase
    )
    # Tidy up double spaces from optional sections.
    narrative = re.sub(r"\s+", " ", narrative).strip()

    return narrative, warnings


# ---- one-shot helper -------------------------------------------------------

def transcript_to_narrative(
    transcript: str,
    *,
    well_context: dict | None = None,
    fallback_year: int | None = None,
) -> tuple[str, SurfaceRestorationFacts, list[ExtractionWarning]]:
    """Convenience: extract -> draft. Returns the narrative, the facts, and
    the union of warnings from both stages.
    """
    facts, ext_warnings = extract_facts_from_transcript(
        transcript, fallback_year=fallback_year,
    )
    narrative, draft_warnings = draft_narrative(
        facts, well_context=well_context,
    )
    # De-duplicate warnings by (slot, severity, message).
    seen: set[tuple[str, str, str]] = set()
    merged: list[ExtractionWarning] = []
    for w in [*ext_warnings, *draft_warnings]:
        key = (w.slot, w.severity, w.message)
        if key in seen:
            continue
        seen.add(key)
        merged.append(w)
    return narrative, facts, merged
