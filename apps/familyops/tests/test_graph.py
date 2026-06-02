from __future__ import annotations

from datetime import date

from familyops.graph import Item, ItemType, Lens, Provider


def _field_trip(seen_in):
    return Item(
        child="Maya",
        lens=Lens.EDUCATION,
        type=ItemType.PAYMENT,
        title="Field trip fee",
        due=date(2026, 6, 10),
        amount_usd=14,
        seen_in=list(seen_in),
    )


def test_same_obligation_from_two_providers_shares_dedup_key():
    # The MVP moat in one assertion: same item from mom's Gmail + dad's Outlook
    # must collapse to one canonical key.
    mom = _field_trip([Provider.GMAIL])
    dad = _field_trip([Provider.MICROSOFT])
    assert mom.dedup_key == dad.dedup_key


def test_dedup_key_is_case_and_whitespace_insensitive():
    a = _field_trip([Provider.GMAIL])
    b = Item(child="  maya ", lens=Lens.EDUCATION, type=ItemType.PAYMENT,
             title="  FIELD TRIP FEE  ", due=date(2026, 6, 10), amount_usd=14)
    assert a.dedup_key == b.dedup_key


def test_distinct_items_differ():
    a = _field_trip([Provider.GMAIL])
    b = Item(child="Maya", lens=Lens.EDUCATION, type=ItemType.FORM,
             title="Permission slip", due=date(2026, 6, 10))
    assert a.dedup_key != b.dedup_key
