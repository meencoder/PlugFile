"""FO-9: Brief delivery — 6 am email.

Public API
----------
MailTransport                          Protocol for pluggable mail back-ends.
FakeTransport                          In-memory capture for tests.
render_html(sections, for_date)        HTML version of render_text.
send_brief(*, household, items, ...)   Compose + render + send in one call.
CronWorker                             Scheduled-run stub (infra wired later).
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from .brief import BriefSection, compose_brief, render_text
from .graph import Household, Item


# ---------------------------------------------------------------------------
# MailTransport protocol
# ---------------------------------------------------------------------------


class MailTransport(Protocol):
    """Pluggable mail back-end.  Implement this to swap SMTP, SES, Postmark …"""

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        text: str,
        html: str,
    ) -> None:
        """Send one message.  Raises on failure."""
        ...


# ---------------------------------------------------------------------------
# FakeTransport — test double
# ---------------------------------------------------------------------------


class FakeTransport:
    """In-memory mail transport for tests.  Never touches a real mail service."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        text: str,
        html: str,
    ) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------


def _escape(s: str) -> str:
    """Minimal HTML entity escaping (stdlib only)."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_item_html(item: Item, for_date: date) -> str:
    """Render a single <li> for one item."""
    parts: list[str] = []

    overdue = item.due is not None and item.due < for_date
    if overdue:
        parts.append("<strong>[OVERDUE]</strong>")

    # child + title
    title_str = _escape(item.title)
    if item.action:
        title_str += f" ({_escape(item.action)})"
    if item.amount_usd is not None:
        title_str += f" ${item.amount_usd:.2f}"

    parts.append(f"{_escape(item.child)} &mdash; {title_str}")

    if item.due is not None:
        if overdue:
            parts.append(f"&mdash; was {item.due}")
        else:
            parts.append(f"&mdash; due {item.due}")
    else:
        parts.append("&mdash; no date")

    if item.assignee is not None:
        parts.append(f"[{_escape(item.assignee)}]")

    needs_rev = item.needs_review or item.confidence < 0.8
    if needs_rev:
        parts.append("&#x26A0;")  # ⚠

    return "    <li>" + " ".join(parts) + "</li>"


def render_html(sections: list[BriefSection], for_date: date) -> str:
    """HTML version of render_text.  Simple <ul><li> structure; stdlib only."""
    heading = _escape(f"Daily Brief — {for_date}")
    body_parts: list[str] = [
        "<!DOCTYPE html>",
        "<html>",
        "<body>",
        f"<h2>{heading}</h2>",
    ]

    for section in sections:
        body_parts.append(f"<h3>{_escape(section.child)}</h3>")
        body_parts.append("<ul>")
        for item in section.items:
            body_parts.append(_render_item_html(item, for_date))
        body_parts.append("</ul>")

    body_parts += ["</body>", "</html>"]
    return "\n".join(body_parts) + "\n"


# ---------------------------------------------------------------------------
# send_brief
# ---------------------------------------------------------------------------


def send_brief(
    *,
    household: Household,
    items: list[Item],
    for_date: date,
    recipients: list[str],
    transport: MailTransport,
) -> None:
    """Compose the daily brief and deliver it via *transport*."""
    sections = compose_brief(items, household, for_date)
    text = render_text(sections, for_date)
    html = render_html(sections, for_date)
    subject = f"Family brief — {for_date:%A, %d %b %Y}"
    transport.send(to=recipients, subject=subject, text=text, html=html)


# ---------------------------------------------------------------------------
# CronWorker stub
# ---------------------------------------------------------------------------


class CronWorker:
    """Scheduled-delivery worker.

    Wires together the store, household configuration, and mail transport for
    the 6 am cron run.  Real SMTP transport is a P1 infra task; until then,
    passing ``transport=None`` raises ``NotImplementedError`` with guidance.
    """

    def __init__(
        self,
        store,
        household: Household,
        recipients: list[str],
        transport: MailTransport | None = None,
    ) -> None:
        self._store = store
        self._household = household
        self._recipients = recipients
        self._transport = transport

    def run(self, for_date: date) -> None:
        """Fetch items from the store and deliver the brief for *for_date*."""
        if self._transport is None:
            raise NotImplementedError(
                "No mail transport configured.  "
                "Inject a MailTransport implementation (e.g. an SMTP back-end) "
                "when constructing CronWorker.  "
                "Real transport is tracked in the P1 infra task."
            )
        items: list[Item] = [
            it for it in self._store.get_items() if isinstance(it, Item)
        ]
        send_brief(
            household=self._household,
            items=items,
            for_date=for_date,
            recipients=self._recipients,
            transport=self._transport,
        )
