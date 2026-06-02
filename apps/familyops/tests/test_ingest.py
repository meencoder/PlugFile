from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_chassis import InMemoryStore
from fastapi.testclient import TestClient

from familyops.ingest import create_app, route_household

FIXTURE = Path(__file__).parent / "fixtures" / "forwarded_school_email.json"


@pytest.fixture
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_post_forward_persists_one_raw_record(payload):
    # Fresh store injected per test -> fully offline, no shared state.
    store = InMemoryStore()
    client = TestClient(create_app(store))

    resp = client.post("/ingest/forward", json=payload)

    assert resp.status_code == 200
    raw_id = resp.json()["raw_id"]
    assert raw_id

    # Exactly one record, retrievable, with the ORIGINAL payload intact.
    record = store.get_raw(raw_id)
    assert record is not None
    assert record["email"] == payload
    assert len(store._raw) == 1


def test_post_forward_stores_routing_guess(payload):
    store = InMemoryStore()
    client = TestClient(create_app(store))

    raw_id = client.post("/ingest/forward", json=payload).json()["raw_id"]

    routing = store.get_raw(raw_id)["routing"]
    assert routing["child_guess"] == "maya"
    assert routing["household_id"] == "household:maya"


def test_route_household_parses_recipient_localpart(payload):
    household_id, child = route_household(payload)
    assert child == "maya"
    assert household_id == "household:maya"


def test_route_household_handles_plus_and_display_name():
    hh, child = route_household({"to": '"Maya R" <maya+school@in.familyops.app>'})
    assert child == "maya"
    assert hh == "household:maya"


def test_route_household_unknown_when_no_recipient():
    hh, child = route_household({"to": ""})
    assert child is None
    assert hh == "household:unknown"
