"""Export the Python W-3 schema to JSON Schema (Draft 2020-12).

This is the machine-readable artifact filed alongside the deterministic
core. The generated schema can be:

  * Used by external tooling (form builders, JSON validators, OpenAPI specs).
  * Diffed across rule revisions to track what changed.
  * Submitted to internal compliance reviewers.

The exporter walks `W3_SCHEMA`, builds a Draft 2020-12 doc, and decorates
each property with x-* extension keywords carrying the source-of-truth
metadata (`x-source`, `x-rrc-section`, `x-canonical`, `x-unit`).

Run:
    PYTHONPATH=src python -m plugfile.json_schema_export > schemas/w3.schema.json
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .w3_schema import W3_SCHEMA


SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID = "https://plugfile.example/schemas/w3.schema.json"


def export_w3_json_schema() -> dict[str, Any]:
    """Build the JSON Schema doc for the W-3 form."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for spec in W3_SCHEMA:
        properties[spec.name] = spec.to_json_schema()
        if spec.required:
            required.append(spec.name)

    return {
        "$schema": SCHEMA_URI,
        "$id": SCHEMA_ID,
        "title": "Texas RRC Form W-3 (Plugging Record)",
        "description": (
            "Schema for the Texas Railroad Commission Form W-3 (Plugging "
            "Record), with field-level source-of-truth annotations under "
            "x-source. Field-level RRC form sections are tagged via "
            "x-rrc-section. Fields whose source is `computed` are derived "
            "by the deterministic engine in plugfile.tac_3_14 and must "
            "never be operator-edited."
        ),
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def main() -> int:
    sys.stdout.write(json.dumps(export_w3_json_schema(), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
