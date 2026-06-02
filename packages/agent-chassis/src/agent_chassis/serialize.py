"""Recursive dataclass/collection -> JSON-friendly conversion.

Generalized from plugfile.prompt_scaffold._serialize so both apps share one
serializer for LLM tool_result blocks, API responses, and the daily brief.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


def to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses, enums, dates and collections into
    JSON-serializable primitives. Leaves already-primitive values untouched.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(x) for x in obj]
    return obj
