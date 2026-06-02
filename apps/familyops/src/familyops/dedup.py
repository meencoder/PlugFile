"""FO-2: Cross-source dedup/merge engine.

Collapses Items that represent the same real-world obligation (same
`dedup_key`) into ONE canonical Item regardless of which provider or
member surfaced it. That merge is the defensible moat: a single-account
assistant cannot express it.

Public API
----------
merge_items(items)          -> list[Item]  (pure, no I/O)
apply_and_store(items, store) -> list[Item]  (fetches, merges, upserts)
"""

from __future__ import annotations

from typing import Iterable

from agent_chassis import Store

from .graph import Item, Provider


def merge_items(items: Iterable[Item]) -> list[Item]:
    """Merge a flat sequence of Items into one canonical Item per dedup_key.

    Within each group the merge rules are:
    - ``seen_in``      : union (deduplicated, ordered by first-seen).
    - ``confidence``   : max across the group.
    - ``needs_review`` : True if ANY item in the group has needs_review=True.
    - ``assignee``     : first non-None value encountered, else None.
    - scalar fields    : taken from the highest-confidence item (tie-break:
                         first item in the group).

    The result is ORDER-INDEPENDENT for ``seen_in`` (union is commutative)
    and always picks the highest-confidence scalars regardless of arrival
    order.
    """
    # Preserve insertion order per group while collecting.
    groups: dict[str, list[Item]] = {}
    for item in items:
        key = item.dedup_key
        groups.setdefault(key, []).append(item)

    merged: list[Item] = []
    for group in groups.values():
        merged.append(_merge_group(group))
    return merged


def _merge_group(group: list[Item]) -> Item:
    """Merge a non-empty list of Items with the same dedup_key."""
    # Highest-confidence item supplies the scalar fields (tie-break: first).
    canonical = max(group, key=lambda it: it.confidence)

    # seen_in: union, deduplicated, ordered by first occurrence across group.
    seen_in: list[Provider] = []
    seen_set: set[Provider] = set()
    for item in group:
        for provider in item.seen_in:
            if provider not in seen_set:
                seen_set.add(provider)
                seen_in.append(provider)

    # Derived aggregate fields.
    confidence = max(it.confidence for it in group)
    needs_review = any(it.needs_review for it in group)
    assignee = next((it.assignee for it in group if it.assignee is not None), None)

    return Item(
        child=canonical.child,
        lens=canonical.lens,
        type=canonical.type,
        title=canonical.title,
        due=canonical.due,
        amount_usd=canonical.amount_usd,
        action=canonical.action,
        seen_in=seen_in,
        assignee=assignee,
        confidence=confidence,
        needs_review=needs_review,
    )


def apply_and_store(items: Iterable[Item], store: Store) -> list[Item]:
    """Fetch existing items from *store*, merge with *items*, upsert, return.

    This makes the operation idempotent: calling it twice with the same
    payload leaves the store in the same state.
    """
    existing: list[Item] = [it for it in store.get_items() if isinstance(it, Item)]
    combined = list(items) + existing
    result = merge_items(combined)
    store.upsert_items(result)
    return result
