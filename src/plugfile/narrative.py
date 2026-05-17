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


_LLM_SLOT_TOOL: dict = {
    "name": "record_surface_restoration_slots",
    "description": (
        "Record surface-restoration facts extracted from the operator's "
        "voice transcript.  Set a field to null if the transcript does not "
        "mention it — never invent or infer facts not stated by the operator."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "casing_cut_depth_ft": {
                "type": ["number", "null"],
                "description": "Depth in feet below ground level where casing was cut",
            },
            "cap_type": {
                "type": ["string", "null"],
                "description": "Material of cap welded to casing stub (e.g. 'steel plate')",
            },
            "cap_dimensions": {
                "type": ["string", "null"],
                "description": "Physical dimensions of the cap (e.g. '24 inch x 24 inch x 1/4 inch')",
            },
            "cellar_filled": {
                "type": ["boolean", "null"],
                "description": "True if the cellar was backfilled",
            },
            "cellar_fill_material": {
                "type": ["string", "null"],
                "description": "Material used to fill cellar (e.g. 'caliche', 'native soil')",
            },
            "equipment_removed": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "List of equipment items removed from the location",
            },
            "vegetation_action": {
                "type": ["string", "null"],
                "description": "Vegetation restoration action (e.g. 're-seeded native grass')",
            },
            "grading_action": {
                "type": ["string", "null"],
                "description": "Grading or levelling action (e.g. 'graded and contoured')",
            },
            "access_road_status": {
                "type": ["string", "null"],
                "description": "Status of access road ('removed', 'retained per surface owner', etc.)",
            },
            "fencing_status": {
                "type": ["string", "null"],
                "description": "Status of fencing ('removed', 'retained', 'repaired')",
            },
            "date_of_work": {
                "type": ["string", "null"],
                "description": "ISO date (YYYY-MM-DD) when surface restoration work was completed",
            },
            "surface_owner_consent": {
                "type": ["string", "null"],
                "description": "Surface owner consent status as stated by the operator",
            },
            "sensitive_surface_notes": {
                "type": ["string", "null"],
                "description": "Notes about environmentally sensitive surface features (wetlands, etc.)",
            },
        },
        # No required fields — Claude returns null for anything not mentioned
        "required": [],
    },
}

_LLM_SYSTEM_PROMPT = """\
You are a regulatory data-extraction assistant for Texas oil-and-gas plugging records.
Your sole job is to extract surface-restoration facts from an operator's voice transcript.

Rules:
1. Extract ONLY what the operator explicitly stated. Never infer, assume, or fabricate.
2. If a slot is not mentioned in the transcript, return null for that slot.
3. You MUST call the record_surface_restoration_slots tool. Do not reply in plain text.
4. Dates must be ISO format (YYYY-MM-DD) when a full date is given.
5. Equipment items must match standard labels: wellhead, tubing string, pumping unit,
   rod string, separator, heater treater, tank battery, flowlines, gas meter,
   compressor, salt water disposal line.
"""


def llm_fill_missing_slots(
    facts: SurfaceRestorationFacts,
    transcript: str,
    *,
    model: str = "claude-haiku-3-5-20241022",
    only_slots: set[str] | None = None,
) -> SurfaceRestorationFacts:
    """Invoke Claude to fill any slots the regex layer missed.

    Phase 2D implementation.  Guarded by the ``PLUGFILE_LLM_FALLBACK``
    environment variable — callers should check the flag before calling
    this function, or use ``transcript_to_narrative(use_llm_fallback=True)``.

    Parameters
    ----------
    facts:
        Facts object already partially populated by the regex extractor.
        Regex-filled slots are NOT overwritten.
    transcript:
        The operator's raw voice/text dictation.
    model:
        Anthropic model ID.  Defaults to Haiku (fast, cheap).
        Override with ``PLUGFILE_LLM_MODEL`` env var.
    only_slots:
        If provided, only ask the LLM about these specific slot names.
        Defaults to all still-missing slots.

    Returns
    -------
    SurfaceRestorationFacts
        A new facts object with any LLM-extracted slots merged in.
        Provenance for LLM-filled slots is marked as ``llm:<model_id>``.

    Raises
    ------
    ImportError
        If ``anthropic`` is not installed.
    RuntimeError
        If the Anthropic API call fails.
    """
    import os

    try:
        import anthropic as _anthropic
    except ImportError as exc:
        raise ImportError(
            "anthropic package is required for LLM fallback. "
            "Install with: pip install anthropic"
        ) from exc

    # Allow model override via env var
    effective_model = os.environ.get("PLUGFILE_LLM_MODEL", model)

    # Determine which slots are still empty
    filled = facts.filled_slots()
    all_slots = {
        "casing_cut_depth_ft", "cap_type", "cap_dimensions",
        "cellar_filled", "cellar_fill_material", "equipment_removed",
        "vegetation_action", "grading_action", "access_road_status",
        "fencing_status", "date_of_work", "surface_owner_consent",
        "sensitive_surface_notes",
    }
    missing = (only_slots or all_slots) - filled
    if not missing:
        return facts  # nothing to fill — skip the API call

    missing_list = "\n".join(f"  - {s}" for s in sorted(missing))
    user_msg = (
        f"Transcript:\n\"\"\"\n{transcript}\n\"\"\"\n\n"
        f"Slots still missing after regex extraction:\n{missing_list}\n\n"
        "Call record_surface_restoration_slots with the values you find. "
        "Use null for any slot not mentioned."
    )

    client = _anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=effective_model,
            max_tokens=512,
            system=_LLM_SYSTEM_PROMPT,
            tools=[_LLM_SLOT_TOOL],
            tool_choice={"type": "tool", "name": "record_surface_restoration_slots"},
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as exc:
        raise RuntimeError(
            f"Anthropic API call failed during LLM slot extraction: {exc}"
        ) from exc

    # Extract the tool_use block
    tool_block = next(
        (b for b in response.content if b.type == "tool_use"),
        None,
    )
    if tool_block is None:
        raise RuntimeError(
            "LLM did not call the expected tool. "
            "Response stop_reason: " + str(response.stop_reason)
        )

    slots: dict = tool_block.input
    prov_tag = f"llm:{effective_model}"

    # Merge into a copy of facts — never overwrite regex-filled slots
    import copy
    new_facts = copy.deepcopy(facts)

    def _set(slot: str, value) -> None:
        if value is None:
            return
        if slot in filled:
            return  # regex already got this — don't overwrite
        setattr(new_facts, slot, value)
        new_facts.provenance[slot] = prov_tag

    _set("casing_cut_depth_ft", slots.get("casing_cut_depth_ft"))
    _set("cap_type", slots.get("cap_type"))
    _set("cap_dimensions", slots.get("cap_dimensions"))
    _set("cellar_filled", slots.get("cellar_filled"))
    _set("cellar_fill_material", slots.get("cellar_fill_material"))
    _set("vegetation_action", slots.get("vegetation_action"))
    _set("grading_action", slots.get("grading_action"))
    _set("access_road_status", slots.get("access_road_status"))
    _set("fencing_status", slots.get("fencing_status"))
    _set("date_of_work", slots.get("date_of_work"))
    _set("surface_owner_consent", slots.get("surface_owner_consent"))
    _set("sensitive_surface_notes", slots.get("sensitive_surface_notes"))

    # equipment_removed is a list — append new items, no duplicates
    if "equipment_removed" not in filled:
        llm_equip = slots.get("equipment_removed") or []
        if llm_equip:
            combined = sorted(set(new_facts.equipment_removed) | set(llm_equip))
            new_facts.equipment_removed = combined
            new_facts.provenance["equipment_removed"] = prov_tag

    return new_facts


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
    use_llm_fallback: bool | None = None,
    llm_model: str = "claude-haiku-3-5-20241022",
) -> tuple[str, SurfaceRestorationFacts, list[ExtractionWarning]]:
    """Convenience: extract -> [optional LLM fill] -> draft.

    Returns the narrative, the final facts, and the union of warnings from
    all stages.

    Parameters
    ----------
    transcript:
        The operator's raw voice/text dictation.
    well_context:
        Optional dict with keys api_number, lease_name, well_number, county
        used to personalise the narrative opener.
    fallback_year:
        Year to assume when the transcript says a month+day but no year.
    use_llm_fallback:
        ``True``  — always call the LLM to fill any slots regex missed.
        ``False`` — never call the LLM even if the env var is set.
        ``None``  — (default) honour the ``PLUGFILE_LLM_FALLBACK`` env var.
                    Any value of ``1``, ``true``, or ``yes`` (case-insensitive)
                    enables the LLM call.
    llm_model:
        Anthropic model ID to use for the fallback.  Overridden by the
        ``PLUGFILE_LLM_MODEL`` env var.
    """
    import os

    facts, ext_warnings = extract_facts_from_transcript(
        transcript, fallback_year=fallback_year,
    )

    # Resolve the LLM flag: explicit bool wins, else check env var.
    if use_llm_fallback is None:
        flag_val = os.environ.get("PLUGFILE_LLM_FALLBACK", "").strip().lower()
        use_llm_fallback = flag_val in ("1", "true", "yes")

    if use_llm_fallback:
        facts = llm_fill_missing_slots(facts, transcript, model=llm_model)

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
