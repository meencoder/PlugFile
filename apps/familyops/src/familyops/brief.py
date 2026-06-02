"""FO-8: Assignment + household daily-brief composer.

Public API
----------
assign_items(items, household)              -> list[Item]
compose_brief(items, household, for_date)  -> list[BriefSection]
render_text(sections, for_date)            -> str
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Sequence

from .graph import Household, Item


# ---------------------------------------------------------------------------
# BriefSection
# ---------------------------------------------------------------------------

@dataclass
class BriefSection:
    """One child's block in the daily brief, with items sorted by priority."""
    child: str
    items: list[Item]


# ---------------------------------------------------------------------------
# assign_items
# ---------------------------------------------------------------------------

def assign_items(items: Sequence[Item], household: Household) -> list[Item]:
    """Return new Item instances with assignees filled in via round-robin.

    Rules:
    - Parents are sorted alphabetically by name.
    - Items that already have an assignee are returned unchanged.
    - Items without an assignee are round-robin assigned across parent names
      in arrival order (stable).
    - If there are no parent members, unassigned items remain unassigned.
    """
    parents = sorted(
        [m.name for m in household.members if not m.is_child]
    )

    if not parents:
        return list(items)

    result: list[Item] = []
    rr_index = 0
    for item in items:
        if item.assignee is not None:
            result.append(item)
        else:
            new_assignee = parents[rr_index % len(parents)]
            rr_index += 1
            result.append(replace(item, assignee=new_assignee))

    return result


# ---------------------------------------------------------------------------
# compose_brief
# ---------------------------------------------------------------------------

def compose_brief(
    items: Sequence[Item],
    household: Household,
    for_date: date,
) -> list[BriefSection]:
    """Compose the household daily brief.

    Steps:
    1. Assign items (round-robin) via assign_items.
    2. Filter to items that are relevant for for_date:
         - overdue (due < for_date) regardless of needs_review
         - due within 7 days (due <= for_date + 7)
         - needs_review=True regardless of due date
    3. Group by child, sort each group by priority, sort sections by child name.

    Priority within a child's section (lower index = higher urgency):
      1. Overdue (due < for_date and needs_review=False) - most urgent
      2. Due today or tomorrow (due <= for_date + timedelta(1))
      3. Needs review (confidence < 0.8 or needs_review=True)
      4. Everything else - sorted by due ascending, None-due last
    """
    assigned = assign_items(items, household)

    window_end = for_date + timedelta(days=7)

    def _is_relevant(item: Item) -> bool:
        if item.needs_review:
            return True
        if item.due is None:
            return False
        if item.due < for_date:          # overdue
            return True
        if item.due <= window_end:       # within 7 days
            return True
        return False

    relevant = [it for it in assigned if _is_relevant(it)]

    def _priority_key(item: Item) -> tuple:
        tomorrow = for_date + timedelta(days=1)

        overdue = item.due is not None and item.due < for_date and not item.needs_review
        due_soon = item.due is not None and item.due <= tomorrow
        needs_rev = item.confidence < 0.8 or item.needs_review

        if overdue:
            bucket = 0
        elif due_soon:
            bucket = 1
        elif needs_rev:
            bucket = 2
        else:
            bucket = 3

        # Secondary sort: due date ascending, None last
        due_sort = (1, date.max) if item.due is None else (0, item.due)

        return (bucket,) + due_sort

    # Group by child
    by_child: dict[str, list[Item]] = {}
    for item in relevant:
        by_child.setdefault(item.child, []).append(item)

    sections: list[BriefSection] = []
    for child in sorted(by_child.keys()):
        sorted_items = sorted(by_child[child], key=_priority_key)
        sections.append(BriefSection(child=child, items=sorted_items))

    return sections


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------

def render_text(sections: list[BriefSection], for_date: date) -> str:
    """Render a plain-text email body for the daily brief."""
    lines: list[str] = [f"Daily Brief — {for_date}", ""]

    for section in sections:
        lines.append(f"=== {section.child} ===")
        for item in section.items:
            line = _render_item(item, for_date)
            lines.append(line)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_item(item: Item, for_date: date) -> str:
    """Render a single bullet line for one item."""
    parts: list[str] = ["•"]

    overdue = item.due is not None and item.due < for_date
    if overdue:
        parts.append("[OVERDUE]")

    parts.append(item.child)

    title_str = item.title
    if item.action:
        title_str += f" ({item.action})"
    if item.amount_usd is not None:
        title_str += f" ${item.amount_usd:.2f}"

    parts.append(f"— {title_str}")

    if item.due is not None:
        if overdue:
            parts.append(f"— was {item.due}")
        else:
            parts.append(f"— due {item.due}")
    else:
        parts.append("— no date")

    if item.assignee is not None:
        parts.append(f"[{item.assignee}]")

    needs_rev = item.needs_review or item.confidence < 0.8
    if needs_rev:
        parts.append("⚠ review")

    return " ".join(parts)