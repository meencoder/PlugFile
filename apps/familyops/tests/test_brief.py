"""Tests for FO-8: assignment + household daily-brief composer."""

from __future__ import annotations

from datetime import date, timedelta

from familyops.brief import BriefSection, assign_items, compose_brief, render_text
from familyops.graph import Household, Item, ItemType, Lens, Member, Provider


# ---------------------------------------------------------------------------
# Constants and helpers
# ---------------------------------------------------------------------------

TODAY = date(2026, 6, 1)
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)
IN_10_DAYS = TODAY + timedelta(days=10)


def _make_household() -> Household:
    """Two parents (Alice, Bob) + one child (Maya)."""
    alice = Member(name="Alice", is_child=False)
    bob = Member(name="Bob", is_child=False)
    maya = Member(name="Maya", is_child=True)
    return Household(name="Smith", members=[alice, bob, maya])


def _item(**overrides) -> Item:
    defaults = dict(
        child="Maya",
        lens=Lens.EDUCATION,
        type=ItemType.EVENT,
        title="Generic event",
        due=None,
        amount_usd=None,
        action=None,
        seen_in=[Provider.GMAIL],
        assignee=None,
        confidence=1.0,
        needs_review=False,
    )
    defaults.update(overrides)
    return Item(**defaults)


def _make_standard_items():
    """Return (overdue_form, tomorrow_payment, supply_review, far_event).

    - overdue_form:       FORM due yesterday  -> included (overdue)
    - tomorrow_payment:   PAYMENT due tomorrow -> included (within 7 days)
    - supply_review:      SUPPLY needs_review=True -> included
    - far_event:          EVENT due in 10 days, needs_review=False -> EXCLUDED
    """
    overdue_form = _item(
        type=ItemType.FORM,
        title="permission slip",
        action="sign_return",
        due=YESTERDAY,
    )
    tomorrow_payment = _item(
        type=ItemType.PAYMENT,
        title="field trip fee",
        amount_usd=14.00,
        due=TOMORROW,
    )
    supply_review = _item(
        type=ItemType.SUPPLY,
        title="science supplies",
        needs_review=True,
        due=TODAY + timedelta(days=3),
    )
    far_event = _item(
        type=ItemType.EVENT,
        title="school play",
        due=IN_10_DAYS,
        needs_review=False,
    )
    return overdue_form, tomorrow_payment, supply_review, far_event


# ---------------------------------------------------------------------------
# compose_brief tests
# ---------------------------------------------------------------------------

class TestComposeBrief:
    def test_returns_one_section_for_maya(self):
        household = _make_household()
        items = list(_make_standard_items())
        sections = compose_brief(items, household, TODAY)
        assert len(sections) == 1
        assert sections[0].child == "Maya"

    def test_excludes_far_future_event(self):
        """10-day-out event with needs_review=False must be excluded."""
        household = _make_household()
        items = list(_make_standard_items())
        sections = compose_brief(items, household, TODAY)
        assert len(sections[0].items) == 3

    def test_overdue_sorts_first(self):
        household = _make_household()
        overdue_form, tomorrow_payment, supply_review, _ = _make_standard_items()
        sections = compose_brief(
            [overdue_form, tomorrow_payment, supply_review], household, TODAY
        )
        first = sections[0].items[0]
        assert first.title == "permission slip", (
            f"Expected overdue item first, got '{first.title}'"
        )

    def test_sections_sorted_by_child_name(self):
        """With two children, sections appear alphabetically."""
        household = Household(
            name="Smith",
            members=[
                Member(name="Alice", is_child=False),
                Member(name="Bob", is_child=False),
                Member(name="Zoe", is_child=True),
                Member(name="Ava", is_child=True),
            ],
        )
        zoe_item = _item(child="Zoe", title="Zoe item", due=TODAY)
        ava_item = _item(child="Ava", title="Ava item", due=TODAY)
        sections = compose_brief([zoe_item, ava_item], household, TODAY)
        assert [s.child for s in sections] == ["Ava", "Zoe"]


# ---------------------------------------------------------------------------
# assign_items tests
# ---------------------------------------------------------------------------

class TestAssignItems:
    def test_round_robin_alphabetical_parents(self):
        """Alice < Bob alphabetically; items arrive in order -> Alice, Bob, Alice."""
        household = _make_household()
        overdue_form, tomorrow_payment, supply_review, _ = _make_standard_items()
        assigned = assign_items(
            [overdue_form, tomorrow_payment, supply_review], household
        )
        assert assigned[0].assignee == "Alice"
        assert assigned[1].assignee == "Bob"
        assert assigned[2].assignee == "Alice"

    def test_pre_assigned_item_unchanged(self):
        """An item that already has an assignee must not be changed."""
        household = _make_household()
        pre = _item(assignee="Bob", title="pre-assigned")
        unassigned = _item(title="unassigned")
        assigned = assign_items([pre, unassigned], household)
        assert assigned[0].assignee == "Bob"
        assert assigned[1].assignee == "Alice"

    def test_returns_new_instances_not_mutated(self):
        """assign_items must use dataclasses.replace, not mutate in place."""
        household = _make_household()
        original = _item(title="original")
        result = assign_items([original], household)
        assert original.assignee is None
        assert result[0].assignee is not None
        assert result[0] is not original

    def test_no_parents_returns_unchanged(self):
        """Household with only children -> items keep assignee=None."""
        household = Household(
            name="Solo",
            members=[Member(name="Maya", is_child=True)],
        )
        item = _item(title="orphan")
        result = assign_items([item], household)
        assert result[0].assignee is None


# ---------------------------------------------------------------------------
# Round-robin assignment via compose_brief
# ---------------------------------------------------------------------------

class TestRoundRobinViaComposeBrief:
    def test_compose_brief_assigns_round_robin(self):
        """compose_brief calls assign_items internally; verify assignment."""
        household = _make_household()
        overdue_form, tomorrow_payment, supply_review, _ = _make_standard_items()
        sections = compose_brief(
            [overdue_form, tomorrow_payment, supply_review], household, TODAY
        )
        by_title = {it.title: it.assignee for it in sections[0].items}
        assert by_title["permission slip"] == "Alice"
        assert by_title["field trip fee"] == "Bob"
        assert by_title["science supplies"] == "Alice"


# ---------------------------------------------------------------------------
# render_text tests
# ---------------------------------------------------------------------------

class TestRenderText:
    def _make_sections(self) -> list[BriefSection]:
        household = _make_household()
        items = list(_make_standard_items()[:3])
        return compose_brief(items, household, TODAY)

    def test_contains_overdue_marker(self):
        sections = self._make_sections()
        text = render_text(sections, TODAY)
        assert "OVERDUE" in text

    def test_contains_dollar_amount(self):
        sections = self._make_sections()
        text = render_text(sections, TODAY)
        assert "$" in text

    def test_contains_review_marker(self):
        sections = self._make_sections()
        text = render_text(sections, TODAY)
        assert "⚠ review" in text

    def test_contains_assignee_names(self):
        sections = self._make_sections()
        text = render_text(sections, TODAY)
        assert "[Alice]" in text
        assert "[Bob]" in text

    def test_date_header_present(self):
        sections = self._make_sections()
        text = render_text(sections, TODAY)
        assert str(TODAY) in text

    def test_no_date_item_renders_no_date(self):
        household = _make_household()
        no_due = _item(title="undated task", due=None, needs_review=True)
        sections = compose_brief([no_due], household, TODAY)
        text = render_text(sections, TODAY)
        assert "no date" in text