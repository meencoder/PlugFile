from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from agent_chassis import to_jsonable


class Color(Enum):
    RED = "red"


@dataclass
class Inner:
    n: int


@dataclass
class Outer:
    name: str
    when: date
    color: Color
    kids: list[Inner]


def test_to_jsonable_handles_nested_dataclasses_enums_dates():
    out = to_jsonable(Outer(name="a", when=date(2026, 6, 1), color=Color.RED, kids=[Inner(1), Inner(2)]))
    assert out == {
        "name": "a",
        "when": "2026-06-01",
        "color": "red",
        "kids": [{"n": 1}, {"n": 2}],
    }


def test_to_jsonable_passes_primitives_through():
    assert to_jsonable({"a": [1, 2.0, "x", None, True]}) == {"a": [1, 2.0, "x", None, True]}
