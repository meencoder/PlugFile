"""The family graph — FamilyOps' defensible core.

Models a household as many MEMBERS, each with many SOURCES (inboxes), where
the same real-world obligation may arrive via several sources and must
collapse to ONE canonical, assignable Item. That cross-source / cross-person
merge is the thing a single-account assistant (Gmail/Gemini) cannot express.

This file is the data model only. Extraction (chassis), dedup logic (FO-2),
and the brief composer (FO-7) build on these types.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Provider(str, Enum):
    GMAIL = "gmail"
    MICROSOFT = "microsoft"        # Outlook / Hotmail / Live / M365
    ICLOUD = "icloud"
    YAHOO = "yahoo"
    AOL = "aol"
    IMAP = "imap"                  # generic ISP / other
    FORWARD = "forward"            # universal forward-to-address fallback


class Lens(str, Enum):
    EDUCATION = "education"        # MVP beachhead
    HEALTH = "health"
    FINANCE = "finance"
    SOCIAL = "social"
    FAMILY = "family"


class ItemType(str, Enum):
    EVENT = "event"
    FORM = "form"
    PAYMENT = "payment"
    SUPPLY = "supply"


@dataclass(frozen=True)
class Source:
    """One connected inbox belonging to a member."""
    provider: Provider
    address: str


@dataclass
class Member:
    name: str
    is_child: bool = False
    sources: list[Source] = field(default_factory=list)


@dataclass
class Household:
    name: str
    members: list[Member] = field(default_factory=list)


@dataclass
class Item:
    """A normalized obligation extracted from a source and placed on the graph."""
    child: str                       # which child it concerns
    lens: Lens
    type: ItemType
    title: str
    due: date | None = None
    amount_usd: float | None = None
    action: str | None = None        # e.g. "sign_return", "pay"
    seen_in: list[Provider] = field(default_factory=list)   # provenance -> trust
    assignee: str | None = None      # which parent owns it -> shared to-do
    confidence: float = 1.0
    needs_review: bool = False

    @property
    def dedup_key(self) -> str:
        """Stable key for collapsing the same obligation seen across sources.

        Deliberately ignores provider/assignee/confidence so the SAME field
        trip arriving in mom's Gmail and dad's Outlook hashes identically.
        """
        basis = f"{self.child.strip().lower()}|{self.type.value}|{self.due}|{self.title.strip().lower()}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
