"""Display formatting helpers.

Pure functions that normalize human-entered values to canonical display
forms. Currently exposes :func:`format_us_phone`, used so district-office
phone numbers render consistently regardless of how they were captured.
"""

from __future__ import annotations

__all__ = ["format_us_phone"]


def format_us_phone(raw: str) -> str:
    """Format a US phone number as ``"(XXX) XXX-XXXX"``.

    Accepts any input shape — bare digits, hyphen/space/paren separators,
    and an optional ``+1`` or leading ``1`` country code — and returns the
    canonical 10-digit display form. If ``raw`` is not a string or cannot
    be reduced to exactly 10 digits (after optionally trimming a leading
    ``1``), the input is returned unchanged rather than raising.
    """
    if not isinstance(raw, str):
        return raw

    digits = "".join(ch for ch in raw if ch.isdigit())

    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) != 10:
        return raw

    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
