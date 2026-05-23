"""Prefill engine for Texas RRC Form W-3A (Notice of Intention to Plug).

The W-3A declares *intent* before plugging.  Unlike the W-3 (which records the
plugs that were actually set), the W-3A carries the **proposed** plug program —
which is exactly what the deterministic §3.14 engine computes from the wellbore.
So this prefill reuses almost the entire W-3 machinery:

    api_number + fetcher  -->  Boxes 1-12, 15, 16 + casing/perfs (authoritative)
            +
    compute_plug_program  -->  proposed_plug_record (the proposal)
            +
    operator_overrides    -->  well/completion type, AOR, cementer, certification
            =
                              W3AForm (populated) + list[FieldConflict] (warnings)

It reuses the private helpers from `prefill` (`_wellbore_from_form`,
`_plug_to_dict`) so the wellbore-construction and plug-flattening logic stays in
one place.  Conflict detection mirrors the W-3 warn-and-flag policy but uses the
W-3A field-source map.
"""

from __future__ import annotations

from typing import Any

from .lookups import Fetcher, FetcherError, MockFetcher
from .prefill import FieldConflict, Severity, _plug_to_dict, _wellbore_from_form
from .tac_3_14 import compute_plug_program
from .w3a_schema import W3A_SCHEMA, W3AForm
from .w3_schema import FieldSource


_W3A_SOURCE_BY_NAME = {f.name: f.source for f in W3A_SCHEMA}

# Override keys handled by merge/assignment rather than scalar conflict checks.
_NON_SCALAR_OVERRIDES = {"aor_findings", "historic_plugs", "perforations",
                         "casing_record", "proposed_plug_record"}

# Operator-sourced scalar fields the operator may supply via overrides.
_OPERATOR_SCALAR_FIELDS = (
    "well_type", "completion_type",
    "drilling_permit_no", "rule_37_case_no", "abstract_no",
    "location_description", "gau_letter_date",
    "cementing_company", "cementer_p5_specialty_code",
    "w3a_issue_date", "w3a_expiration_date",
    "operator_signature_name", "operator_title", "certification_date",
)


def _w3a_conflicts(form: W3AForm, overrides: dict[str, Any]) -> list[FieldConflict]:
    """Compare scalar overrides against populated form values (warn-and-flag).

    Mismatches against authoritative-source fields are `warn`; mismatches
    against operator-sourced fields are `info` (the operator's value wins
    there anyway).
    """
    conflicts: list[FieldConflict] = []
    for name, op_value in overrides.items():
        if name in _NON_SCALAR_OVERRIDES:
            continue
        if not hasattr(form, name):
            continue
        auth_value = getattr(form, name)
        if op_value is None or auth_value is None or op_value == auth_value:
            continue
        source = _W3A_SOURCE_BY_NAME.get(name, FieldSource.OPERATOR_INPUT)
        severity: Severity = (
            "info"
            if source in (
                FieldSource.OPERATOR_INPUT,
                FieldSource.OPERATOR_OBSERVED,
                FieldSource.OPERATOR_CERTIFICATION,
            )
            else "warn"
        )
        conflicts.append(
            FieldConflict(
                field_name=name,
                operator_value=op_value,
                authoritative_value=auth_value,
                source=source,
                severity=severity,
                message=(
                    f"Operator value differs from {source.value}; "
                    "authoritative value retained — operator should verify "
                    "or update the source record."
                ),
            )
        )
    return conflicts


def prefill_w3a(
    api_number: str,
    fetcher: Fetcher,
    operator_overrides: dict[str, Any] | None = None,
) -> tuple[W3AForm, list[FieldConflict]]:
    """Populate a W3AForm for the given API number.

    Authoritative data (well master, operator P-5, GAU, completion) comes from
    `fetcher`; the proposed plug program is computed by the §3.14 engine.
    `operator_overrides` supplies operator-sourced fields (well/completion type,
    AOR findings, historic plugs, cementer info, certification).

    Returns (form, conflicts). Conflicts are advisory; authoritative values are
    always retained in the form.
    """
    overrides = operator_overrides or {}
    form = W3AForm()

    # ---- Boxes 1-12: well-master record (Section I/II) --------------------
    well = fetcher.lookup_well_by_api(api_number)
    for k, v in well.items():
        if hasattr(form, k):
            setattr(form, k, v)

    # ---- Boxes 1/2: operator P-5 ------------------------------------------
    p5 = None
    if hasattr(fetcher, "operator_p5_for_api"):
        try:
            p5 = fetcher.operator_p5_for_api(api_number)  # type: ignore[attr-defined]
        except FetcherError:
            p5 = None
    if p5:
        op = fetcher.lookup_operator(p5)
        for k, v in op.items():
            if hasattr(form, k):
                setattr(form, k, v)

    # ---- Box 16: GAU (required for the W-3A to be reviewed) ---------------
    gau = fetcher.lookup_gau(api_number)
    form.buqw_depth_ft = gau["buqw_depth_ft"]
    form.gau_letter_reference = gau["gau_letter_reference"]
    # GAULookupResult may not carry a date; accept it from the override if so.
    form.gau_letter_date = gau.get("gau_letter_date") or overrides.get("gau_letter_date")  # type: ignore[attr-defined]

    # ---- Box 15 + casing + perforations: completion record ----------------
    comp = fetcher.lookup_completion(api_number)
    form.total_depth_ft = comp["total_depth_ft"]
    form.casing_record = list(comp["casing_record"])
    # W-3A doesn't need per-perf operator status (that's a W-3 plug-time fact).
    form.perforations = [dict(p) for p in comp["perforations"]]

    # ---- Box 17 AOR + historic plugs (operator-entered, v1) ---------------
    if overrides.get("aor_findings"):
        form.aor_findings = list(overrides["aor_findings"])
    if overrides.get("historic_plugs"):
        form.historic_plugs = list(overrides["historic_plugs"])

    # ---- The proposal: deterministic §3.14 plug program -------------------
    well_obj = _wellbore_from_form(form)  # duck-typed; W3AForm has the attrs read
    plugs = compute_plug_program(well_obj)
    form.proposed_plug_record = [_plug_to_dict(p) for p in plugs]
    form.plug_program_rule_paths = sorted({p.rule_path for p in plugs})
    form.buqw_protected_by_surface_casing = (
        well_obj.buqw_protected_by_surface_casing()
    )

    # ---- operator-sourced scalar fields -----------------------------------
    for fld in _OPERATOR_SCALAR_FIELDS:
        if fld in overrides and overrides[fld] is not None:
            setattr(form, fld, overrides[fld])

    conflicts = _w3a_conflicts(form, overrides)
    return form, conflicts


def prefill_w3a_with_mock(
    api_number: str,
    operator_overrides: dict[str, Any] | None = None,
) -> tuple[W3AForm, list[FieldConflict]]:
    """Shortcut for tests / demos using the in-memory MockFetcher."""
    return prefill_w3a(api_number, MockFetcher(), operator_overrides=operator_overrides)
