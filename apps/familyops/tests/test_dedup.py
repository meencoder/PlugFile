"""Tests for FO-2: cross-source dedup/merge engine (familyops.dedup).

Headline moat test: the same real-world obligation arriving from two
different providers collapses to ONE canonical Item that carries provenance
from both sources.
"""

from __future__ import annotations

from datetime import date

import pytest
from agent_chassis import InMemoryStore

from familyops.dedup import apply_and_store, merge_items
from familyops.graph import Item, ItemType, Lens, Provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _field_trip(**overrides) -> Item:
    """Base Item representing a school field-trip payment."""
    defaults = dict(
        child="Maya",
        lens=Lens.EDUCATION,
        type=ItemType.PAYMENT,
        title="Field trip fee",
        due=date(2026, 6, 10),
        amount_usd=14.0,
        seen_in=[Provider.GMAIL],
        confidence=1.0,
        needs_review=False,
        assignee=None,
    )
    defaults.update(overrides)
    return Item(**defaults)


# ---------------------------------------------------------------------------
# Moat test
# ---------------------------------------------------------------------------

def test_same_obligation_two_providers_merges_to_one():
    """THE moat assertion: Gmail + Outlook → ONE item with both providers."""
    mom = _field_trip(seen_in=[Provider.GMAIL])
    dad = _field_trip(seen_in=[Provider.MICROSOFT])

    result = merge_items([mom, dad])

    assert len(result) == 1, "Two same-key items must collapse to one"
    merged = result[0]
    assert Provider.GMAIL in merged.seen_in
    assert Provider.MICROSOFT in merged.seen_in


# ---------------------------------------------------------------------------
# Order independence
# ---------------------------------------------------------------------------

def test_merge_is_order_independent():
    """merge_items([a, b]) and merge_items([b, a]) produce equivalent results."""
    a = _field_trip(seen_in=[Provider.GMAIL])
    b = _field_trip(seen_in=[Provider.MICROSOFT])

    ab = merge_items([a, b])
    ba = merge_items([b, a])

    assert len(ab) == 1
    assert len(ba) == 1

    assert ab[0].dedup_key == ba[0].dedup_key
    assert set(ab[0].seen_in) == set(ba[0].seen_in)


# ---------------------------------------------------------------------------
# Distinct keys → distinct items
# ---------------------------------------------------------------------------

def test_different_keys_produce_two_items():
    """Items with different obligations must NOT be collapsed."""
    payment = _field_trip(type=ItemType.PAYMENT, title="Field trip fee")
    form = _field_trip(type=ItemType.FORM, title="Permission slip")

    result = merge_items([payment, form])

    assert len(result) == 2


# ---------------------------------------------------------------------------
# confidence and needs_review aggregation
# ---------------------------------------------------------------------------

def test_confidence_is_max():
    a = _field_trip(seen_in=[Provider.GMAIL], confidence=0.6)
    b = _field_trip(seen_in=[Provider.MICROSOFT], confidence=0.9)

    result = merge_items([a, b])

    assert result[0].confidence == pytest.approx(0.9)


def test_needs_review_is_any():
    a = _field_trip(seen_in=[Provider.GMAIL], needs_review=False)
    b = _field_trip(seen_in=[Provider.MICROSOFT], needs_review=True)

    result = merge_items([a, b])

    assert result[0].needs_review is True


def test_needs_review_false_when_none_flagged():
    a = _field_trip(seen_in=[Provider.GMAIL], needs_review=False)
    b = _field_trip(seen_in=[Provider.MICROSOFT], needs_review=False)

    result = merge_items([a, b])

    assert result[0].needs_review is False


# ---------------------------------------------------------------------------
# assignee: first non-None
# ---------------------------------------------------------------------------

def test_assignee_first_non_none():
    a = _field_trip(seen_in=[Provider.GMAIL], assignee=None)
    b = _field_trip(seen_in=[Provider.MICROSOFT], assignee="dad")

    result = merge_items([a, b])

    assert result[0].assignee == "dad"


def test_assignee_none_when_all_none():
    a = _field_trip(seen_in=[Provider.GMAIL], assignee=None)
    b = _field_trip(seen_in=[Provider.MICROSOFT], assignee=None)

    result = merge_items([a, b])

    assert result[0].assignee is None


# ---------------------------------------------------------------------------
# Scalar fields from highest-confidence item
# ---------------------------------------------------------------------------

def test_scalar_fields_from_highest_confidence():
    low = _field_trip(
        seen_in=[Provider.GMAIL],
        confidence=0.5,
        amount_usd=10.0,
        action="pay_low",
    )
    high = _field_trip(
        seen_in=[Provider.MICROSOFT],
        confidence=0.9,
        amount_usd=20.0,
        action="pay_high",
    )

    result = merge_items([low, high])

    assert result[0].amount_usd == pytest.approx(20.0)
    assert result[0].action == "pay_high"


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty():
    assert merge_items([]) == []


# ---------------------------------------------------------------------------
# seen_in deduplication within a group
# ---------------------------------------------------------------------------

def test_seen_in_deduplicated():
    """If the same provider appears in multiple items it must appear once."""
    a = _field_trip(seen_in=[Provider.GMAIL])
    b = _field_trip(seen_in=[Provider.GMAIL, Provider.MICROSOFT])

    result = merge_items([a, b])

    assert result[0].seen_in.count(Provider.GMAIL) == 1


# ---------------------------------------------------------------------------
# apply_and_store round-trip
# ---------------------------------------------------------------------------

def test_apply_and_store_round_trips():
    """apply_and_store upserts merged items and they are retrievable."""
    store = InMemoryStore()
    mom = _field_trip(seen_in=[Provider.GMAIL])
    dad = _field_trip(seen_in=[Provider.MICROSOFT])

    result = apply_and_store([mom, dad], store)

    assert len(result) == 1
    stored = store.get_items()
    assert len(stored) == 1
    assert stored[0].dedup_key == result[0].dedup_key


def test_apply_and_store_merges_with_existing():
    """apply_and_store fetches existing store items and merges with new ones."""
    store = InMemoryStore()

    # First call: mom's Gmail item.
    apply_and_store([_field_trip(seen_in=[Provider.GMAIL])], store)

    # Second call: dad's Outlook item for the same obligation.
    result = apply_and_store([_field_trip(seen_in=[Provider.MICROSOFT])], store)

    # Must still resolve to ONE item carrying both providers.
    assert len(result) == 1
    assert Provider.GMAIL in result[0].seen_in
    assert Provider.MICROSOFT in result[0].seen_in


def test_apply_and_store_two_different_items():
    """Different obligations are stored as two separate items."""
    store = InMemoryStore()
    payment = _field_trip(type=ItemType.PAYMENT, title="Field trip fee")
    form = _field_trip(type=ItemType.FORM, title="Permission slip")

    result = apply_and_store([payment, form], store)

    assert len(result) == 2
    assert len(store.get_items()) == 2
