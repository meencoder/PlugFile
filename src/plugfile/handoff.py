"""Operator ↔ plugging-company collaboration handoff.

The RRC W-3 online filing is a multi-party workflow (training deck pp.23,
38): the operator creates the filing, hands it to the plugging company to
enter the plugging/cementing details, the plugging company returns it, the
operator reviews and certifies, then clicks "Submit to District" — which
routes it to the RRC district office.

Plugfile has no accounts or database, so this module does not *persist* a
filing. Instead it models the workflow as a deterministic state machine:
given the current stage and a few readiness facts, it reports who holds the
filing, what they must do, what is blocking the next handoff, and who
receives it next. Transitions are gated on the same required-attachments
logic used elsewhere (:func:`plugfile.attachments.check_attachments`), so
the handoff can't advance past a stage with missing documents.

Usage::

    from plugfile.handoff import evaluate_handoff

    state = evaluate_handoff(
        "operator_review",
        form_type="w3",
        has_gau_letter=True, has_l1_well_log=True, has_p13_affidavit=True,
        has_plugging_details=True, operator_certified=True,
    )
    if state.can_advance:
        print(state.next_action)        # "Submit to District"
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .attachments import FormType, check_attachments
from .lookups import Fetcher, MockFetcher


# ---- roles + stages ---------------------------------------------------------

ROLE_OPERATOR = "operator"
ROLE_PLUGGING = "plugging_company"
ROLE_RRC = "rrc_district"

_ROLE_LABELS = {
    ROLE_OPERATOR: "Operator",
    ROLE_PLUGGING: "Plugging company",
    ROLE_RRC: "RRC district office",
}


class HandoffStage(str, Enum):
    DRAFT = "draft"
    PLUGGING_REVIEW = "plugging_company_review"
    OPERATOR_REVIEW = "operator_review"
    SUBMITTED = "submitted_to_district"
    ACCEPTED = "accepted"


# ---- workflow definition ----------------------------------------------------

@dataclass(frozen=True)
class HandoffStep:
    """One stage in the ordered RRC W-3 collaboration workflow."""
    stage: str
    holder_role: str
    title: str
    description: str
    advance_action: Optional[str]   # the action that moves it forward (None = terminal/RRC-side)
    next_stage: Optional[str]
    next_holder: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "holder_role": self.holder_role,
            "holder_label": _ROLE_LABELS.get(self.holder_role, self.holder_role),
            "title": self.title,
            "description": self.description,
            "advance_action": self.advance_action,
            "next_stage": self.next_stage,
            "next_holder": self.next_holder,
        }


WORKFLOW: tuple[HandoffStep, ...] = (
    HandoffStep(
        HandoffStage.DRAFT.value, ROLE_OPERATOR,
        "Draft created",
        "Operator looks up the well, prefills the W-3/W-3A, and prepares the "
        "filing. Hand it to the plugging company to add the cementing record.",
        "Send to plugging company",
        HandoffStage.PLUGGING_REVIEW.value, ROLE_PLUGGING,
    ),
    HandoffStep(
        HandoffStage.PLUGGING_REVIEW.value, ROLE_PLUGGING,
        "Plugging company review",
        "Plugging company enters the actual plug placements, cement volumes, "
        "and gathers the required attachments, then returns the filing to the "
        "operator.",
        "Return to operator",
        HandoffStage.OPERATOR_REVIEW.value, ROLE_OPERATOR,
    ),
    HandoffStep(
        HandoffStage.OPERATOR_REVIEW.value, ROLE_OPERATOR,
        "Operator review",
        "Operator verifies the plugging details, confirms all required "
        "attachments are present, certifies (signs), and submits to the RRC "
        "district office.",
        "Submit to District",
        HandoffStage.SUBMITTED.value, ROLE_RRC,
    ),
    HandoffStep(
        HandoffStage.SUBMITTED.value, ROLE_RRC,
        "Submitted to district",
        "The RRC district office has received the filing. Confirmation emails "
        "go to the filer and the district. Awaiting RRC acceptance — no "
        "further operator action unless the district returns it.",
        None,
        HandoffStage.ACCEPTED.value, ROLE_RRC,
    ),
    HandoffStep(
        HandoffStage.ACCEPTED.value, ROLE_RRC,
        "Accepted",
        "The RRC district office has accepted the W-3 plugging record. The "
        "filing is complete.",
        None, None, None,
    ),
)

_STEP_BY_STAGE: dict[str, HandoffStep] = {s.stage: s for s in WORKFLOW}

VALID_STAGES: tuple[str, ...] = tuple(s.stage for s in WORKFLOW)


# ---- result type ------------------------------------------------------------

@dataclass
class HandoffState:
    """The handoff state for a filing at a given stage."""
    api_number: Optional[str]
    operator_name: Optional[str]
    plugging_company: Optional[str]
    form_type: str
    current_stage: str
    holder_role: str
    holder_label: str
    title: str
    description: str
    can_advance: bool
    blocking: list[str]
    next_stage: Optional[str]
    next_holder_role: Optional[str]
    next_holder_label: Optional[str]
    next_action: Optional[str]
    attachments_ready: bool
    attachments_missing: list[str]
    workflow: list[HandoffStep]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_number": self.api_number,
            "operator_name": self.operator_name,
            "plugging_company": self.plugging_company,
            "form_type": self.form_type,
            "current_stage": self.current_stage,
            "holder_role": self.holder_role,
            "holder_label": self.holder_label,
            "title": self.title,
            "description": self.description,
            "can_advance": self.can_advance,
            "blocking": self.blocking,
            "next_stage": self.next_stage,
            "next_holder_role": self.next_holder_role,
            "next_holder_label": self.next_holder_label,
            "next_action": self.next_action,
            "attachments_ready": self.attachments_ready,
            "attachments_missing": self.attachments_missing,
            "workflow": [s.to_dict() for s in self.workflow],
            "warnings": self.warnings,
        }


# ---- core (pure) ------------------------------------------------------------

def evaluate_handoff(
    stage: str,
    *,
    form_type: FormType = "w3",
    api_number: str | None = None,
    operator_name: str | None = None,
    plugging_company: str | None = None,
    has_gau_letter: bool = False,
    has_w15_plugging_permit: bool = False,
    has_l1_well_log: bool = False,
    has_p13_affidavit: bool = False,
    has_plugging_details: bool = False,
    operator_certified: bool = False,
) -> HandoffState:
    """Evaluate the collaboration state for a filing at *stage*.

    Pure function: given the stage and readiness facts, returns who holds the
    filing and whether it can advance. Document-readiness gating reuses
    :func:`plugfile.attachments.check_attachments`.

    Raises:
        ValueError: if *stage* is not one of :data:`VALID_STAGES`.
    """
    if stage not in _STEP_BY_STAGE:
        raise ValueError(
            f"Unknown handoff stage {stage!r}. Valid: {', '.join(VALID_STAGES)}"
        )

    step = _STEP_BY_STAGE[stage]

    checklist = check_attachments(
        api_number or "",
        form_type=form_type,
        has_gau_letter=has_gau_letter,
        has_w15_plugging_permit=has_w15_plugging_permit,
        has_l1_well_log=has_l1_well_log,
        has_p13_affidavit=has_p13_affidavit,
    )
    attachments_ready = checklist.ready
    attachments_missing = list(checklist.missing)

    blocking: list[str] = []

    # Stage-specific gating for advancing the handoff.
    if stage == HandoffStage.DRAFT.value:
        # Operator can always hand a prefilled draft to the plugging company.
        pass
    elif stage == HandoffStage.PLUGGING_REVIEW.value:
        if not has_plugging_details:
            blocking.append(
                "Plugging company must enter the plug placements and cement "
                "record before returning the filing."
            )
        if not attachments_ready:
            blocking.append(
                "Required attachments still missing: "
                + ", ".join(attachments_missing) + "."
            )
    elif stage == HandoffStage.OPERATOR_REVIEW.value:
        if not has_plugging_details:
            blocking.append(
                "Plugging details are not complete — return to the plugging "
                "company."
            )
        if not attachments_ready:
            blocking.append(
                "Required attachments still missing: "
                + ", ".join(attachments_missing) + "."
            )
        if not operator_certified:
            blocking.append(
                "Operator must certify (sign) the filing before submitting to "
                "the district."
            )
    elif stage == HandoffStage.SUBMITTED.value:
        blocking.append(
            "Awaiting RRC district review — no operator action available."
        )
    elif stage == HandoffStage.ACCEPTED.value:
        # Terminal — nothing to advance.
        pass

    # Terminal stages have no advance action regardless of gating.
    can_advance = step.advance_action is not None and not blocking

    next_holder_label = (
        _ROLE_LABELS.get(step.next_holder) if step.next_holder else None
    )

    return HandoffState(
        api_number=api_number,
        operator_name=operator_name,
        plugging_company=plugging_company,
        form_type=form_type,
        current_stage=stage,
        holder_role=step.holder_role,
        holder_label=_ROLE_LABELS.get(step.holder_role, step.holder_role),
        title=step.title,
        description=step.description,
        can_advance=can_advance,
        blocking=blocking,
        next_stage=step.next_stage,
        next_holder_role=step.next_holder,
        next_holder_label=next_holder_label,
        next_action=step.advance_action,
        attachments_ready=attachments_ready,
        attachments_missing=attachments_missing,
        workflow=list(WORKFLOW),
        warnings=[],
    )


# ---- enriched (with RRC lookup for party names) -----------------------------

def build_handoff(
    api_number: str,
    fetcher: Fetcher,
    *,
    stage: str = HandoffStage.DRAFT.value,
    form_type: FormType = "w3",
    plugging_company: str | None = None,
    has_gau_letter: bool = False,
    has_w15_plugging_permit: bool = False,
    has_l1_well_log: bool = False,
    has_p13_affidavit: bool = False,
    has_plugging_details: bool = False,
    operator_certified: bool = False,
) -> HandoffState:
    """Evaluate the handoff and enrich it with the operator's name.

    Resolves the operator name from RRC lookups (best-effort — falls back to
    None with a warning if the lookup fails) so the workflow can name the
    party that holds the filing.
    """
    warnings: list[str] = []
    operator_name: str | None = None
    try:
        # prefill_w3a resolves operator identity through the lookup chain.
        from .prefill_w3a import prefill_w3a
        overrides = {"cementing_company": plugging_company} if plugging_company else None
        form, _ = prefill_w3a(api_number, fetcher, operator_overrides=overrides)
        operator_name = form.operator_name
        if plugging_company is None:
            plugging_company = getattr(form, "cementing_company", None)
    except Exception as exc:
        warnings.append(f"Could not resolve operator/plugger names: {exc}")

    state = evaluate_handoff(
        stage,
        form_type=form_type,
        api_number=api_number,
        operator_name=operator_name,
        plugging_company=plugging_company,
        has_gau_letter=has_gau_letter,
        has_w15_plugging_permit=has_w15_plugging_permit,
        has_l1_well_log=has_l1_well_log,
        has_p13_affidavit=has_p13_affidavit,
        has_plugging_details=has_plugging_details,
        operator_certified=operator_certified,
    )
    state.warnings = warnings + state.warnings
    return state


def build_handoff_with_mock(
    api_number: str,
    *,
    stage: str = HandoffStage.DRAFT.value,
    **kwargs: Any,
) -> HandoffState:
    """Shortcut for tests / demos using the in-memory MockFetcher."""
    return build_handoff(api_number, MockFetcher(), stage=stage, **kwargs)
