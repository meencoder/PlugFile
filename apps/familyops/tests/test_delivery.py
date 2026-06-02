"""Tests for FO-9: brief delivery — MailTransport, render_html, send_brief, CronWorker."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from agent_chassis import InMemoryStore
from familyops.brief import compose_brief
from familyops.delivery import (
    CronWorker,
    FakeTransport,
    render_html,
    send_brief,
)
from familyops.graph import Household, Item, ItemType, Lens, Member, Provider


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

TODAY = date(2026, 6, 1)
TOMORROW = TODAY + timedelta(days=1)
YESTERDAY = TODAY - timedelta(days=1)


def _make_household() -> Household:
    """One parent (Alice) + one child (Maya)."""
    alice = Member(name="Alice", is_child=False)
    maya = Member(name="Maya", is_child=True)
    return Household(name="Smith", members=[alice, maya])


def _payment_item() -> Item:
    """PAYMENT due tomorrow — not overdue."""
    return Item(
        child="Maya",
        lens=Lens.FINANCE,
        type=ItemType.PAYMENT,
        title="Field trip fee",
        due=TOMORROW,
        amount_usd=25.00,
        seen_in=[Provider.GMAIL],
        confidence=1.0,
        needs_review=False,
    )


def _overdue_form_item() -> Item:
    """FORM due yesterday — overdue."""
    return Item(
        child="Maya",
        lens=Lens.EDUCATION,
        type=ItemType.FORM,
        title="Permission slip",
        due=YESTERDAY,
        action="sign_return",
        seen_in=[Provider.GMAIL],
        confidence=1.0,
        needs_review=False,
    )


# ---------------------------------------------------------------------------
# send_brief tests
# ---------------------------------------------------------------------------


class TestSendBrief:
    def _run(self) -> FakeTransport:
        transport = FakeTransport()
        household = _make_household()
        items = [_payment_item(), _overdue_form_item()]
        send_brief(
            household=household,
            items=items,
            for_date=TODAY,
            recipients=["alice@example.com"],
            transport=transport,
        )
        return transport

    def test_exactly_one_message_sent(self):
        transport = self._run()
        assert len(transport.sent) == 1

    def test_subject_contains_weekday(self):
        transport = self._run()
        msg = transport.sent[0]
        # TODAY is 2026-06-01, which is a Monday
        assert "Monday" in msg["subject"]

    def test_text_contains_overdue(self):
        transport = self._run()
        assert "OVERDUE" in transport.sent[0]["text"]

    def test_text_contains_payment_title(self):
        transport = self._run()
        assert "Field trip fee" in transport.sent[0]["text"]

    def test_html_contains_ul(self):
        transport = self._run()
        assert "<ul>" in transport.sent[0]["html"]

    def test_html_contains_overdue_strong(self):
        transport = self._run()
        assert "<strong>[OVERDUE]</strong>" in transport.sent[0]["html"]


# ---------------------------------------------------------------------------
# render_html tests
# ---------------------------------------------------------------------------


class TestRenderHtml:
    def _make_sections(self):
        household = _make_household()
        items = [_payment_item(), _overdue_form_item()]
        return compose_brief(items, household, TODAY)

    def test_contains_ul_tag(self):
        sections = self._make_sections()
        html = render_html(sections, TODAY)
        assert "<ul>" in html

    def test_contains_overdue_strong(self):
        sections = self._make_sections()
        html = render_html(sections, TODAY)
        assert "<strong>[OVERDUE]</strong>" in html

    def test_contains_child_heading(self):
        sections = self._make_sections()
        html = render_html(sections, TODAY)
        assert "Maya" in html

    def test_no_external_deps(self):
        """render_html is importable — just calling it proves no exotic deps."""
        from familyops.delivery import render_html as rh  # noqa: F401 (re-import ok)
        assert callable(rh)

    def test_needs_review_marker(self):
        """Items with needs_review=True should have the ⚠ symbol in HTML."""
        household = _make_household()
        item = Item(
            child="Maya",
            lens=Lens.EDUCATION,
            type=ItemType.FORM,
            title="Review me",
            due=TOMORROW,
            seen_in=[Provider.GMAIL],
            confidence=1.0,
            needs_review=True,
        )
        sections = compose_brief([item], household, TODAY)
        html = render_html(sections, TODAY)
        # ⚠ is encoded as &#x26A0; in the HTML
        assert "&#x26A0;" in html or "⚠" in html


# ---------------------------------------------------------------------------
# CronWorker tests
# ---------------------------------------------------------------------------


class TestCronWorker:
    def test_run_sends_one_message(self):
        """CronWorker.run with InMemoryStore seeded with 2 items sends exactly one message."""
        store = InMemoryStore()
        items = [_payment_item(), _overdue_form_item()]
        store.upsert_items(items)

        household = _make_household()
        transport = FakeTransport()
        worker = CronWorker(
            store=store,
            household=household,
            recipients=["alice@example.com"],
            transport=transport,
        )
        worker.run(for_date=TODAY)

        assert len(transport.sent) == 1

    def test_run_without_transport_raises(self):
        """CronWorker with transport=None must raise NotImplementedError."""
        store = InMemoryStore()
        household = _make_household()
        worker = CronWorker(
            store=store,
            household=household,
            recipients=["alice@example.com"],
            transport=None,
        )
        with pytest.raises(NotImplementedError):
            worker.run(for_date=TODAY)
