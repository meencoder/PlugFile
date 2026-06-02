from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent_chassis import InMemoryStore, SqliteStore


@dataclass
class Thing:
    """Tiny local stand-in for an app Item: any object with a dedup_key."""

    kind: str
    name: str
    note: str = ""

    @property
    def dedup_key(self) -> str:
        return f"{self.kind}:{self.name}"


def make_store(kind: str):
    if kind == "memory":
        return InMemoryStore()
    if kind == "sqlite":
        return SqliteStore(":memory:")
    raise ValueError(kind)


@pytest.fixture(params=["memory", "sqlite"])
def store(request):
    return make_store(request.param)


def test_put_raw_get_raw_round_trips_payload(store):
    payload = {"a": 1, "b": ["x", "y"], "nested": {"k": True}}
    raw_id = store.put_raw("inbox", payload)
    assert isinstance(raw_id, str) and raw_id
    assert store.get_raw(raw_id) == payload


def test_get_raw_missing_returns_none(store):
    assert store.get_raw("does-not-exist") is None


def test_upsert_same_dedup_key_twice_yields_one_item(store):
    store.upsert_items([Thing(kind="task", name="mow", note="first")])
    store.upsert_items([Thing(kind="task", name="mow", note="second")])

    items = store.get_items()
    assert len(items) == 1
    # The second upsert replaced the first in place.
    only = items[0]
    note = only["note"] if isinstance(only, dict) else only.note
    assert note == "second"


def test_upsert_two_different_keys_yields_two_items(store):
    store.upsert_items(
        [
            Thing(kind="task", name="mow"),
            Thing(kind="task", name="dishes"),
        ]
    )
    assert len(store.get_items()) == 2
