from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from agent_chassis import InMemoryStore
from fastapi.testclient import TestClient
from familyops.brief import assign_items, compose_brief
from familyops.dedup import apply_and_store, merge_items
from familyops.graph import Household, Item, ItemType, Lens, Member, Provider, Source
from familyops.ingest import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "forwarded_school_email.json"
FOR_DATE = date(2026, 6, 1)


def _load_alice_payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["from"] = "alice.smith@gmail.com"
    return payload


def _make_bob_payload() -> dict:
    bob = dict(_load_alice_payload())
    bob["from"] = "bob.smith@outlook.com"
    return bob


def _smith_household() -> Household:
    return Household(
        name="Smith",
        members=[
            Member(
                name="Alice",
                is_child=False,
                sources=[Source(provider=Provider.GMAIL, address="alice.smith@gmail.com")],
            ),
            Member(
                name="Bob",
                is_child=False,
                sources=[Source(provider=Provider.MICROSOFT, address="bob.smith@outlook.com")],
            ),
            Member(name="Maya", is_child=True, sources=[]),
        ],
    )


def extract_stub(raw: dict, provider: Provider) -> list[Item]:
    """Parse a raw ingest record and return one Item.

    Intentionally minimal: hard-codes the field-trip fixture values so the e2e
    pipeline runs fully offline without the real Gemini extractor (FO-3).
    The raw dict is what store.get_raw() returns, wrapping email under "email".
    """
    email: dict = raw.get("email", raw)
    subject: str = email.get("subject", "")
    title = subject.strip() if subject.strip() else "Unknown school item"
    return [
        Item(
            child="Maya",
            lens=Lens.EDUCATION,
            type=ItemType.PAYMENT,
            title=title,
            due=date(2026, 6, 6),
            amount_usd=14.0,
            action="sign_return",
            seen_in=[provider],
            confidence=1.0,
            needs_review=False,
        )
    ]


def items_to_ics(items: list[Item], household_name: str) -> str:
    """Generate a minimal iCalendar string for items that have a due date.

    Produces a valid VCALENDAR with one VEVENT per item. Uses stdlib only.
    Lines separated by CRLF per RFC 5545.
    """
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//FamilyOps//{household_name}//EN",
        "CALSCALE:GREGORIAN",
    ]
    for item in items:
        if item.due is None:
            continue
        due_str = item.due.strftime("%Y%m%d")
        summary = item.title.replace("\n", " ").replace("\r", "")
        desc_parts: list[str] = []
        if item.amount_usd is not None:
            desc_parts.append(f"Amount: ${item.amount_usd:.2f}")
        if item.assignee is not None:
            desc_parts.append(f"Assigned to: {item.assignee}")
        description = " | ".join(desc_parts)
        lines += [
            "BEGIN:VEVENT",
            f"DTSTART;VALUE=DATE:{due_str}",
            f"DTEND;VALUE=DATE:{due_str}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"UID:{item.dedup_key}@familyops.app",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def test_e2e_two_providers_one_canonical_todo():
    """Full pipeline: 2 parents x 2 providers -> 1 assigned to-do in ICS feed.

    Assertions:
    1. Two POSTs -> two distinct raw_ids (ingest works).
    2. merge_items returns exactly ONE item.
    3. merged.seen_in contains BOTH Provider.GMAIL and Provider.MICROSOFT.
    4. store.get_items() returns exactly ONE record after apply_and_store.
    5. compose_brief returns one BriefSection with one item for Maya.
    6. The assigned item has a non-None assignee (Alice or Bob).
    7. items_to_ics output contains structural ICS markers + item title.
    """
    # ---- Step 1: Ingest ------------------------------------------------
    store = InMemoryStore()
    app = create_app(store)
    client = TestClient(app)

    alice_payload = _load_alice_payload()
    bob_payload = _make_bob_payload()

    resp_a = client.post("/ingest/forward", json=alice_payload)
    assert resp_a.status_code == 200, f"Alice POST failed: {resp_a.text}"
    raw_id_a: str = resp_a.json()["raw_id"]

    resp_b = client.post("/ingest/forward", json=bob_payload)
    assert resp_b.status_code == 200, f"Bob POST failed: {resp_b.text}"
    raw_id_b: str = resp_b.json()["raw_id"]

    # Assertion 1
    assert raw_id_a and raw_id_b, "raw_ids must be non-empty"
    assert raw_id_a != raw_id_b, "Two POSTs must yield two DISTINCT raw_ids"

    # ---- Step 2: Extract -----------------------------------------------
    raw_a = store.get_raw(raw_id_a)
    raw_b = store.get_raw(raw_id_b)
    assert raw_a is not None
    assert raw_b is not None

    items_a = extract_stub(raw_a, Provider.GMAIL)
    items_b = extract_stub(raw_b, Provider.MICROSOFT)
    assert len(items_a) == 1
    assert len(items_b) == 1
    item_a = items_a[0]
    item_b = items_b[0]

    # ---- Step 3: Dedup -------------------------------------------------
    merged_items = merge_items([item_a, item_b])

    # Assertion 2
    assert len(merged_items) == 1, f"merge_items must return 1 item, got {len(merged_items)}"
    merged = merged_items[0]

    # Assertion 3
    assert Provider.GMAIL in merged.seen_in, "merged must include Provider.GMAIL"
    assert Provider.MICROSOFT in merged.seen_in, "merged must include Provider.MICROSOFT"

    # ---- Step 4: apply_and_store ---------------------------------------
    apply_and_store([item_a, item_b], store)
    stored = store.get_items()

    # Assertion 4
    assert len(stored) == 1, f"store must hold 1 item, got {len(stored)}"

    # ---- Step 5: compose_brief ----------------------------------------
    household = _smith_household()
    sections = compose_brief(merged_items, household, for_date=FOR_DATE)

    # Assertion 5
    assert len(sections) == 1, f"Expected 1 BriefSection, got {len(sections)}"
    maya_section = sections[0]
    assert maya_section.child == "Maya"
    assert len(maya_section.items) == 1, (
        f"Maya section must have 1 item, got {len(maya_section.items)}"
    )

    # ---- Step 6: assign_items -----------------------------------------
    assigned = assign_items(merged_items, household)
    assert len(assigned) == 1
    assigned_item = assigned[0]

    # Assertion 6
    assert assigned_item.assignee is not None, "assign_items must set a non-None assignee"
    assert assigned_item.assignee in {"Alice", "Bob"}, (
        f"Assignee must be Alice or Bob, got {assigned_item.assignee!r}"
    )

    # ---- Step 7: ICS feed ---------------------------------------------
    ics_str = items_to_ics(assigned, household_name="Smith")

    # Assertion 7
    assert "BEGIN:VCALENDAR" in ics_str, "ICS must contain BEGIN:VCALENDAR"
    assert "BEGIN:VEVENT" in ics_str, "ICS must contain at least one BEGIN:VEVENT"
    assert assigned_item.title in ics_str, "ICS must include the item title"
    assert "END:VCALENDAR" in ics_str, "ICS must contain END:VCALENDAR"