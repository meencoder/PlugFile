"""Texas RRC API number normalization.

The Railroad Commission of Texas (RRC) identifies every well by a 10-digit
American Petroleum Institute (API) number, displayed canonically as
``42-371-30001`` (state-county-unique). Operators submit this value in a
variety of shapes: bare digits, hyphen- or space-separated, with stray
whitespace. Downstream code (W-3 / W-3A forms, RRC lookups, AOR imports)
expects the canonical hyphenated form.

This module exposes :func:`normalize_api_number`, a pure helper that
validates a raw input and returns the canonical ``42-XXX-XXXXX`` string,
raising :class:`ValueError` with a clear message otherwise.
"""

from __future__ import annotations

__all__ = ["normalize_api_number"]


def normalize_api_number(raw: str) -> str:
    """Validate and canonicalize a Texas RRC API number.

    Accepts 10-digit input with optional hyphen or space separators and
    surrounding whitespace (e.g. ``"4237130001"``, ``"42-371-30001"``,
    ``"42 371 30001"``, ``" 42-371-30001 "``). Returns the canonical
    hyphenated form ``"42-371-30001"``.

    Raises :class:`ValueError` if ``raw`` is not a string, contains
    non-digit characters once separators are stripped, is not exactly 10
    digits, or carries a state code other than ``42`` (Texas).
    """
    if not isinstance(raw, str):
        raise ValueError(
            f"API number must be a string, got {type(raw).__name__}"
        )

    stripped = raw.strip()
    if not stripped:
        raise ValueError("API number is empty")

    digits = stripped.replace("-", "").replace(" ", "")

    if not digits.isdigit():
        raise ValueError(
            f"API number must contain only digits (and optional '-' or ' ' "
            f"separators); got {raw!r}"
        )

    if len(digits) != 10:
        raise ValueError(
            f"API number must be exactly 10 digits; got {len(digits)} "
            f"in {raw!r}"
        )

    state = digits[:2]
    if state != "42":
        raise ValueError(
            f"API number must start with Texas state code '42'; got "
            f"{state!r} in {raw!r}"
        )

    return f"{digits[:2]}-{digits[2:5]}-{digits[5:]}"
