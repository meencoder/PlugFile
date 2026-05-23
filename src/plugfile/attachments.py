"""Required-Attachments Checker for Texas RRC W-3 / W-3A filings.

Tracks the four documents required by the RRC District before a filing
is reviewed. Missing any of these is the #1 cause of district rejection
per the July 2025 RRC training deck (slide p.34).

  1. GAU Determination Letter     — already parsed by gau_parser.py
  2. W-15 Plugging Permit         — RRC-issued permit for the proposed program
  3. L-1 Well Log Report          — electric / mud / gamma-ray log
  4. P-13 Plugging Cost Affidavit — certifies actual plugging cost

Usage::

    from plugfile.attachments import check_attachments

    result = check_attachments(
        "42-371-30001",
        form_type="w3a",
        has_gau_letter=True,
        has_w15_plugging_permit=False,
        has_l1_well_log=False,
        has_p13_affidavit=False,
        gau_reference="GAU-2024-03-12-Pecos-21874",
    )
    if not result.ready:
        print("Missing:", result.missing)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AttachmentKey = Literal[
    "gau_letter",
    "w15_plugging_permit",
    "l1_well_log",
    "p13_affidavit",
]

FormType = Literal["w3a", "w3"]

# All four attachments in canonical order.
_ALL_KEYS: tuple[AttachmentKey, ...] = (
    "gau_letter",
    "w15_plugging_permit",
    "l1_well_log",
    "p13_affidavit",
)

# Which attachments are required per form type.
# W-3A (intent to plug): all four must be assembled before the district
#   will schedule a review.
# W-3 (plugging record): W-15 is the permit that was granted after W-3A
#   approval and is referenced rather than re-submitted; all others required.
_REQUIRED: dict[FormType, frozenset[AttachmentKey]] = {
    "w3a": frozenset({"gau_letter", "w15_plugging_permit", "l1_well_log", "p13_affidavit"}),
    "w3":  frozenset({"gau_letter", "l1_well_log", "p13_affidavit"}),
}

# Static metadata per attachment type.
_META: dict[AttachmentKey, dict[str, str]] = {
    "gau_letter": {
        "display_name": "GAU Determination Letter",
        "description": (
            "RRC Groundwater Advisory Unit letter confirming BUQW depth and "
            "H-15 acceptability for plugging. Must be the 'acceptable for "
            "plugging' determination (GW-2 / H-15 acceptable)."
        ),
        "rrc_ref": "§3.14(d)(2) / RRC GAU",
        "tip": (
            "Upload the PDF. Plugfile parses BUQW depth and reference number "
            "automatically — verify the parsed values match the letter."
        ),
    },
    "w15_plugging_permit": {
        "display_name": "W-15 Plugging Permit",
        "description": (
            "The plugging permit issued by the RRC District after W-3A "
            "approval. Authorises the operator to proceed with the proposed "
            "plug program."
        ),
        "rrc_ref": "16 TAC §3.14(a)",
        "tip": (
            "Download from the RRC Online System after your W-3A is approved "
            "by the district. Valid for 2 years from issue date."
        ),
    },
    "l1_well_log": {
        "display_name": "L-1 Well Log Report",
        "description": (
            "Electric log, mud log, or gamma-ray log documenting the wellbore "
            "formation record. Needed to verify plug placement vs. productive "
            "zones and BUQW depth."
        ),
        "rrc_ref": "RRC Oil & Gas Form L-1",
        "tip": (
            "Acceptable formats: digitised wireline log (LAS file), scanned "
            "paper log (PDF). District may request specific log types."
        ),
    },
    "p13_affidavit": {
        "display_name": "P-13 Plugging Cost Affidavit",
        "description": (
            "Affidavit certifying the actual cost of plugging operations, "
            "required for RRC bond-release and orphan-well-fund accounting."
        ),
        "rrc_ref": "RRC Oil & Gas Form P-13",
        "tip": (
            "Complete after plugging is finished; submit together with the "
            "W-3 plugging record. Notarisation required."
        ),
    },
}


# ── output types ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AttachmentStatus:
    """Status of one document in the checklist."""
    key: AttachmentKey
    display_name: str
    required: bool
    present: bool
    description: str
    rrc_ref: str
    tip: str
    reference: str | None        # document-specific reference (e.g. GAU letter ref #)


@dataclass(frozen=True)
class AttachmentChecklist:
    """Full readiness assessment for one filing."""
    api_number: str
    form_type: FormType
    ready: bool                  # True only when all required docs are present
    present_count: int           # required docs that are present
    required_count: int          # total required docs for this form type
    missing: list[str]           # display names of missing required docs
    items: list[AttachmentStatus]

    def to_dict(self) -> dict:
        return {
            "api_number": self.api_number,
            "form_type": self.form_type,
            "ready": self.ready,
            "present_count": self.present_count,
            "required_count": self.required_count,
            "missing": self.missing,
            "items": [
                {
                    "key": item.key,
                    "display_name": item.display_name,
                    "required": item.required,
                    "present": item.present,
                    "description": item.description,
                    "rrc_ref": item.rrc_ref,
                    "tip": item.tip,
                    "reference": item.reference,
                }
                for item in self.items
            ],
        }


# ── public API ────────────────────────────────────────────────────────────────

def check_attachments(
    api_number: str,
    *,
    form_type: FormType = "w3a",
    has_gau_letter: bool = False,
    has_w15_plugging_permit: bool = False,
    has_l1_well_log: bool = False,
    has_p13_affidavit: bool = False,
    gau_reference: str | None = None,
) -> AttachmentChecklist:
    """Evaluate attachment readiness for a W-3 or W-3A filing.

    Each ``has_*`` flag is True when the operator has uploaded / confirmed
    that document. Returns an :class:`AttachmentChecklist` with a ``ready``
    flag and a ``missing`` list of required-but-absent display names.

    Args:
        api_number:            RRC API number for the well.
        form_type:             ``"w3a"`` (intent) or ``"w3"`` (plugging record).
        has_gau_letter:        GAU determination letter uploaded.
        has_w15_plugging_permit: W-15 permit document present.
        has_l1_well_log:       L-1 well log uploaded.
        has_p13_affidavit:     P-13 cost affidavit uploaded.
        gau_reference:         GAU letter reference number, if known (advisory).
    """
    required_set = _REQUIRED[form_type]
    presence: dict[AttachmentKey, bool] = {
        "gau_letter":          has_gau_letter,
        "w15_plugging_permit": has_w15_plugging_permit,
        "l1_well_log":         has_l1_well_log,
        "p13_affidavit":       has_p13_affidavit,
    }
    ref_map: dict[AttachmentKey, str | None] = {
        "gau_letter":          gau_reference,
        "w15_plugging_permit": None,
        "l1_well_log":         None,
        "p13_affidavit":       None,
    }

    items: list[AttachmentStatus] = []
    missing: list[str] = []

    for key in _ALL_KEYS:
        meta = _META[key]
        required = key in required_set
        present  = presence[key]
        if required and not present:
            missing.append(meta["display_name"])
        items.append(AttachmentStatus(
            key=key,
            display_name=meta["display_name"],
            required=required,
            present=present,
            description=meta["description"],
            rrc_ref=meta["rrc_ref"],
            tip=meta["tip"],
            reference=ref_map[key],
        ))

    present_count = sum(
        1 for key in _ALL_KEYS
        if key in required_set and presence[key]
    )

    return AttachmentChecklist(
        api_number=api_number,
        form_type=form_type,
        ready=len(missing) == 0,
        present_count=present_count,
        required_count=len(required_set),
        missing=missing,
        items=items,
    )
