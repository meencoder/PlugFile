"""LLM prompt scaffold for W-3 plugging-program drafting.

This module defines the system prompt and Anthropic tool-use schema that an
LLM agent uses to convert an operator's narrative description of a well into
a structured, regulation-compliant plug program.

The agent does NOT do arithmetic. All cement-volume math and rule application
happens in the deterministic Python tools below — the LLM just routes inputs
to them, structures outputs, and drafts narrative text.

USAGE
-----

    from anthropic import Anthropic
    from plugfile.prompt_scaffold import (
        SYSTEM_PROMPT, TOOL_SCHEMAS, dispatch_tool_call,
    )

    client = Anthropic()
    messages = [{"role": "user", "content": operator_narrative}]
    while True:
        resp = client.messages.create(
            model="claude-sonnet-4-5",
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            max_tokens=4096,
            messages=messages,
        )
        if resp.stop_reason != "tool_use":
            break
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                result = dispatch_tool_call(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id,
                     "content": result}
                )
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": tool_results})
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from .cement_volume import (
    annular_plug_volume,
    cylinder_plug_volume,
)
from .geometry import (
    BUQW,
    CasingKind,
    CasingString,
    OpenHoleSection,
    Perforation,
    Wellbore,
)
from .lookups import Fetcher, FetcherError, MockFetcher


def _select_fetcher() -> Fetcher:
    """Choose fetcher based on PLUGFILE_FETCHER env var.

    PLUGFILE_FETCHER=real -> RRCRoRQFetcher (Phase 2A; live RRC scraper)
    PLUGFILE_FETCHER=mock -> MockFetcher (default; Phase 1A fixtures)

    Tests pass a Fetcher explicitly, so this only affects the
    dispatch_tool_call path used by the Anthropic SDK runtime.
    """
    import os as _os
    if (_os.environ.get("PLUGFILE_FETCHER") or "mock").lower() == "real":
        try:
            from .lookups_rrc import RRCRoRQFetcher
            return RRCRoRQFetcher()
        except ImportError as e:
            raise FetcherError(
                f"PLUGFILE_FETCHER=real requires Phase 2A deps: {e}"
            )
    return MockFetcher()
from .narrative import transcript_to_narrative
from .prefill import prefill_w3
from .tac_3_14 import compute_plug_program


# ---- system prompt ----------------------------------------------------------

SYSTEM_PROMPT = """\
You are a regulatory engineering assistant that helps Texas oil-and-gas
operators draft Form W-3 (Plugging Record) filings under 16 TAC §3.14
(Statewide Rule 14, "Plugging").

YOUR JOB
========
Given a narrative description of a well and how it was plugged, produce a
complete, structured plug program that an operator can transcribe directly
onto a W-3.

HARD RULES — FOLLOW THESE WITHOUT EXCEPTION
==========================================
1. NEVER do arithmetic in your head. Every cement volume MUST come from a
   call to `compute_cement_volume_cylinder` or `compute_cement_volume_annulus`.
   Reporting an un-tool-derived volume is a regulatory error.

2. NEVER decide where plugs go based on memory of §3.14. Always call
   `compute_plug_program` with the parsed wellbore — or, preferably, call
   `prefill_w3_form` with the API number to do the lookup AND the rule
   computation in one step. The deterministic rule engine is the single
   source of truth for plug placement.

2a. PREFER `prefill_w3_form` over `compute_plug_program` whenever an API
    number is available. It pulls operator info, GAU letter, completion
    record, and computes the plug program in a single call. Only fall
    back to `compute_plug_program` when the operator hands you raw
    wellbore geometry without an API number.

3. If the operator's narrative is missing any of these, STOP and ask:
   - API number, operator, lease/well, county
   - Total depth (MD ft)
   - Every casing string: kind, OD, ID, set depth, top of cement
   - BUQW depth (with source — typically the GAU letter)
   - All perforations with zone names and status

4. After the tool returns the plug program, draft the W-3 narrative in the
   format specified by RRC W-3 instructions: top-down, one row per plug,
   with depths, hole/casing diameter, cement volume in sacks AND barrels,
   and the §3.14 cite that authorizes the plug.

5. Always note any TAC §3.14 special case that fires (e.g. continuous column
   to surface for BUQW not covered by surface casing) explicitly in the
   narrative -- do not silently apply it.

6. For Section IX surface-restoration text, prefer
   `draft_surface_restoration_narrative` over hand-writing prose. The
   tool extracts facts deterministically from the operator's voice
   transcript and inserts clearly-flagged placeholders for missing
   slots; pass the warnings back to the operator for review.

UNIT CONVENTIONS
================
- Diameters: inches.
- Depths and lengths: feet from KB/RT (assume KB ≈ ground level unless told).
- Volumes: report sacks AND barrels; cubic feet for engineering reviewers.
- Always echo the excess factor used (0% in cased hole, 25% default open hole).

WHEN UNCERTAIN
==============
Say so. Ask the operator. Do not fabricate casing dimensions, BUQW depths,
or perforation intervals. A wrong W-3 is worse than a delayed W-3.
"""


# ---- tool schemas (Anthropic tool-use format) -------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "compute_cement_volume_cylinder",
        "description": (
            "Compute cement volume for a plug set inside a single cylindrical "
            "bore (open hole or inside one casing string). Returns ft³, "
            "barrels, and sacks. Use excess_factor=0.25 for open hole, 0.0 "
            "for cased hole."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "diameter_in": {
                    "type": "number",
                    "description": "Bore diameter in inches (open-hole bit size or casing ID)",
                },
                "length_ft": {
                    "type": "number",
                    "description": "Plug length in feet",
                },
                "excess_factor": {
                    "type": "number",
                    "description": "Excess factor as a decimal (e.g. 0.25 for +25%). Default 0.",
                },
                "sack_yield_ft3": {
                    "type": "number",
                    "description": "Cement sack yield in ft³/sack. Default 1.06 (Class H neat).",
                },
            },
            "required": ["diameter_in", "length_ft"],
        },
    },
    {
        "name": "compute_cement_volume_annulus",
        "description": (
            "Compute cement volume for a plug set in the annulus between two "
            "strings (or open hole and casing). Use the bore the cement sits "
            "inside as outer_id_in and the OD of the inner pipe as inner_od_in."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "outer_id_in": {
                    "type": "number",
                    "description": "Inner diameter of the bore the cement sits inside (inches)",
                },
                "inner_od_in": {
                    "type": "number",
                    "description": "Outer diameter of the pipe in the middle of that bore (inches)",
                },
                "length_ft": {"type": "number"},
                "excess_factor": {"type": "number"},
                "sack_yield_ft3": {"type": "number"},
            },
            "required": ["outer_id_in", "inner_od_in", "length_ft"],
        },
    },
    {
        "name": "compute_plug_program",
        "description": (
            "Apply TAC §3.14 (general rule + special-case rule for BUQW not "
            "covered by surface casing) to a fully-described wellbore. Returns "
            "an ordered list of PlugRequirements with computed volumes and "
            "rule citations. Always call this BEFORE drafting any W-3 narrative."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "api_number": {"type": "string"},
                "operator": {"type": "string"},
                "lease_name": {"type": "string"},
                "well_number": {"type": "string"},
                "county": {"type": "string"},
                "total_depth_ft": {"type": "number"},
                "buqw_depth_ft": {"type": "number"},
                "buqw_source": {"type": "string"},
                "casing": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": [k.value for k in CasingKind],
                            },
                            "od_in": {"type": "number"},
                            "id_in": {"type": "number"},
                            "set_depth_ft": {"type": "number"},
                            "top_of_cement_ft": {"type": "number"},
                        },
                        "required": [
                            "kind", "od_in", "id_in",
                            "set_depth_ft", "top_of_cement_ft",
                        ],
                    },
                },
                "perforations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "top_ft": {"type": "number"},
                            "bottom_ft": {"type": "number"},
                            "zone_name": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["producing", "injection", "abandoned", "squeezed"],
                            },
                        },
                        "required": ["top_ft", "bottom_ft", "zone_name"],
                    },
                },
                "open_hole": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "top_ft": {"type": "number"},
                            "bottom_ft": {"type": "number"},
                            "bit_size_in": {"type": "number"},
                        },
                        "required": ["top_ft", "bottom_ft", "bit_size_in"],
                    },
                },
            },
            "required": [
                "api_number", "operator", "lease_name", "well_number", "county",
                "total_depth_ft", "buqw_depth_ft", "casing",
            ],
        },
    },
    {
        "name": "lookup_well_by_api",
        "description": (
            "Query authoritative RRC sources (well master, operator P-5, "
            "GAU letter, completion record) for one well. Returns the raw "
            "lookup payloads — useful when the operator wants to verify a "
            "single fact without producing a full W-3. For drafting a W-3, "
            "prefer `prefill_w3_form` instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "api_number": {
                    "type": "string",
                    "description": "14-digit Texas API number (e.g. '42-371-30001')",
                },
            },
            "required": ["api_number"],
        },
    },
    {
        "name": "prefill_w3_form",
        "description": (
            "End-to-end W-3 prefill: pull operator + well + GAU + completion "
            "data from authoritative sources, run the deterministic TAC "
            "§3.14 plug-program engine, and return a populated W-3 form "
            "object plus a list of FieldConflict warnings (operator-supplied "
            "values that disagree with authoritative sources). Use this as "
            "the FIRST tool call whenever an API number is available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "api_number": {
                    "type": "string",
                    "description": "14-digit Texas API number (e.g. '42-371-30001')",
                },
                "plugging_date": {
                    "type": "string",
                    "description": "ISO-formatted date plugging was performed (YYYY-MM-DD)",
                },
                "operator_overrides": {
                    "type": "object",
                    "description": (
                        "Optional operator-supplied values: certification "
                        "fields (operator_signature_name, operator_title, "
                        "certification_date, cementing_company); plus a "
                        "perforations array with status updates "
                        "(top_ft, zone_name, status)."
                    ),
                },
            },
            "required": ["api_number"],
        },
    },
    {
        "name": "draft_surface_restoration_narrative",
        "description": (
            "Convert an operator's free-form voice transcript of surface "
            "restoration work into the formal Section IX narrative for "
            "Form W-3. Uses a deterministic regex extractor; missing "
            "slots are flagged in the warnings list. Optionally takes "
            "well_context (api_number, lease_name, well_number, county) "
            "for the narrative opener -- pull these via prefill_w3_form "
            "or lookup_well_by_api when an API number is available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "transcript": {
                    "type": "string",
                    "description": "Operator's voice/text dictation of surface restoration work performed",
                },
                "well_context": {
                    "type": "object",
                    "description": "Optional: api_number, lease_name, well_number, county for narrative opener",
                },
                "fallback_year": {
                    "type": "integer",
                    "description": "Year to use if the transcript names a month and day but no year",
                },
            },
            "required": ["transcript"],
        },
    },
]



# ---- dispatcher -------------------------------------------------------------

def _serialize(obj: Any) -> Any:
    """Recursively dataclass -> dict for JSON-friendly tool results."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def _build_wellbore(args: dict[str, Any]) -> Wellbore:
    return Wellbore(
        api_number=args["api_number"],
        operator=args["operator"],
        lease_name=args["lease_name"],
        well_number=args["well_number"],
        county=args["county"],
        total_depth_ft=float(args["total_depth_ft"]),
        buqw=BUQW(
            depth_ft=float(args["buqw_depth_ft"]),
            source=args.get("buqw_source", "GAU letter"),
        ),
        casing=tuple(
            CasingString(
                kind=CasingKind(c["kind"]),
                od_in=float(c["od_in"]),
                id_in=float(c["id_in"]),
                set_depth_ft=float(c["set_depth_ft"]),
                top_of_cement_ft=float(c["top_of_cement_ft"]),
            )
            for c in args.get("casing", [])
        ),
        perforations=tuple(
            Perforation(
                top_ft=float(p["top_ft"]),
                bottom_ft=float(p["bottom_ft"]),
                zone_name=p["zone_name"],
                status=p.get("status", "producing"),
            )
            for p in args.get("perforations", [])
        ),
        open_hole=tuple(
            OpenHoleSection(
                top_ft=float(o["top_ft"]),
                bottom_ft=float(o["bottom_ft"]),
                bit_size_in=float(o["bit_size_in"]),
            )
            for o in args.get("open_hole", [])
        ),
    )


def dispatch_tool_call(name: str, args: dict[str, Any]) -> str:
    """Route an LLM tool call to the deterministic implementation. Always
    returns a JSON string suitable for an Anthropic tool_result block.
    """
    if name == "compute_cement_volume_cylinder":
        result = cylinder_plug_volume(
            diameter_in=float(args["diameter_in"]),
            length_ft=float(args["length_ft"]),
            excess_factor=float(args.get("excess_factor", 0.0)),
            sack_yield_ft3=float(args.get("sack_yield_ft3", 1.06)),
        )
        return json.dumps(_serialize(result))

    if name == "compute_cement_volume_annulus":
        result = annular_plug_volume(
            outer_id_in=float(args["outer_id_in"]),
            inner_od_in=float(args["inner_od_in"]),
            length_ft=float(args["length_ft"]),
            excess_factor=float(args.get("excess_factor", 0.0)),
            sack_yield_ft3=float(args.get("sack_yield_ft3", 1.06)),
        )
        return json.dumps(_serialize(result))

    if name == "compute_plug_program":
        well = _build_wellbore(args)
        plugs = compute_plug_program(well)
        return json.dumps(_serialize(plugs))

    if name == "lookup_well_by_api":
        fetcher = MockFetcher()
        api = args["api_number"]
        try:
            well = fetcher.lookup_well_by_api(api)
            p5 = fetcher.operator_p5_for_api(api)
            operator = fetcher.lookup_operator(p5)
            gau = fetcher.lookup_gau(api)
            completion = fetcher.lookup_completion(api)
        except FetcherError as e:
            return json.dumps({"error": str(e)})
        return json.dumps({
            "well": well, "operator": operator,
            "gau": gau, "completion": completion,
        })

    if name == "prefill_w3_form":
        fetcher = MockFetcher()
        try:
            form, conflicts = prefill_w3(
                api_number=args["api_number"],
                fetcher=fetcher,
                operator_overrides=args.get("operator_overrides"),
                plugging_date=args.get("plugging_date"),
            )
        except FetcherError as e:
            return json.dumps({"error": str(e)})
        return json.dumps({
            "form": form.to_dict(),
            "missing_required": sorted(form.missing_required()),
            "conflicts": [_serialize(c) for c in conflicts],
        })

    if name == "draft_surface_restoration_narrative":
        narrative, facts, warnings = transcript_to_narrative(
            args["transcript"],
            well_context=args.get("well_context"),
            fallback_year=args.get("fallback_year"),
        )
        return json.dumps({
            "narrative": narrative,
            "facts": _serialize(facts),
            "warnings": [_serialize(w) for w in warnings],
        })

    raise ValueError(f"Unknown tool: {name}")
