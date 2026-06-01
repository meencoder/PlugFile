"""Tests for :func:`plugfile.formatting.format_us_phone`."""

from __future__ import annotations

import pytest

from plugfile.formatting import format_us_phone


CANONICAL = "(432) 684-5581"


@pytest.mark.parametrize(
    "raw",
    [
        "4326845581",
        "432-684-5581",
        "(432) 684-5581",
        "+1 432 684 5581",
        "1-432-684-5581",
        "432.684.5581",
        "  432 684 5581  ",
    ],
)
def test_canonicalizes_known_variants(raw: str) -> None:
    assert format_us_phone(raw) == CANONICAL


def test_returns_input_unchanged_when_too_few_digits() -> None:
    assert format_us_phone("555-1234") == "555-1234"


def test_returns_input_unchanged_when_too_many_digits() -> None:
    raw = "+44 20 7946 0958"
    assert format_us_phone(raw) == raw


def test_returns_input_unchanged_when_eleven_digits_not_country_code() -> None:
    raw = "24326845581"
    assert format_us_phone(raw) == raw


def test_returns_input_unchanged_when_no_digits() -> None:
    assert format_us_phone("not a phone") == "not a phone"


def test_returns_input_unchanged_when_empty() -> None:
    assert format_us_phone("") == ""


def test_non_string_input_returned_unchanged() -> None:
    assert format_us_phone(4326845581) == 4326845581  # type: ignore[arg-type]


def test_other_valid_ten_digit_number() -> None:
    assert format_us_phone("2125551234") == "(212) 555-1234"
