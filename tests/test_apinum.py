"""Tests for :func:`plugfile.apinum.normalize_api_number`."""

from __future__ import annotations

import pytest

from plugfile.apinum import normalize_api_number


CANONICAL = "42-371-30001"


@pytest.mark.parametrize(
    "raw",
    [
        "4237130001",
        "42-371-30001",
        "42 371 30001",
        " 42-371-30001 ",
        "\t42-371-30001\n",
        "42-371 30001",
    ],
)
def test_accepts_variants(raw: str) -> None:
    assert normalize_api_number(raw) == CANONICAL


def test_other_valid_unique_digits() -> None:
    assert normalize_api_number("4200112345") == "42-001-12345"


def test_rejects_wrong_length_short() -> None:
    with pytest.raises(ValueError, match="exactly 10 digits"):
        normalize_api_number("423713000")


def test_rejects_wrong_length_long() -> None:
    with pytest.raises(ValueError, match="exactly 10 digits"):
        normalize_api_number("42371300011")


def test_rejects_non_numeric() -> None:
    with pytest.raises(ValueError, match="only digits"):
        normalize_api_number("42-37A-30001")


def test_rejects_non_texas_state_code() -> None:
    with pytest.raises(ValueError, match="Texas state code"):
        normalize_api_number("30-371-30001")


def test_rejects_empty_string() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_api_number("   ")


def test_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        normalize_api_number(4237130001)  # type: ignore[arg-type]
