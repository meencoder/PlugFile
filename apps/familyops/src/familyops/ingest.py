"""FO-4 — forward-to-address inbound ingest.

The universal fallback channel: a household forwards (or auto-forwards) school /
health / finance email to a per-child address like ``maya@in.familyops.app``.
A mail provider (e.g. Postmark) POSTs the parsed message here as JSON.

This ticket does ONE thing: persist the forwarded email as a single RAW record
via the chassis ``Store``, tagged with a cheap household/child routing GUESS so a
later extraction pass (FO-3) knows which child the payload concerns. Extraction
into ``Item``s is explicitly out of scope here.

The ``Store`` is dependency-injected (default ``InMemoryStore``) so tests run
fully offline against a fresh store.
"""

from __future__ import annotations

from typing import Any

from agent_chassis import InMemoryStore, Store
from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel, Field

#: The chassis ``source`` tag every forwarded record is stored under.
SOURCE = "forward"


class ForwardedEmail(BaseModel):
    """A forwarded email as a mail provider's inbound webhook delivers it.

    Deliberately permissive: real providers add many extra keys, and we persist
    the payload verbatim, so unknown fields are kept rather than rejected.
    """

    model_config = {"extra": "allow"}

    from_: str = Field("", alias="from")
    to: str = ""
    subject: str = ""
    text: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)


def _localpart(address: str) -> str:
    """Return the lowercased localpart of an email address.

    Tolerates display-name forms (``"Maya" <maya@x>``) and plus-addressing
    (``maya+school@x`` -> ``maya``). Returns ``""`` when no address is present.
    """
    if not address:
        return ""
    addr = address.strip()
    if "<" in addr and ">" in addr:
        addr = addr[addr.index("<") + 1 : addr.index(">")]
    local = addr.split("@", 1)[0].strip().lower()
    return local.split("+", 1)[0]


def route_household(payload: dict) -> tuple[str, str | None]:
    """Heuristically route a forwarded email to a household and child.

    The forward-to address encodes the child in its localpart, so the recipient
    ``maya@in.familyops.app`` routes to child ``"maya"``. This is intentionally a
    dumb, fully testable stub: real household resolution (mapping an address to a
    registered ``Household``) lands in a later ticket.

    Returns ``(household_id, child_guess)`` where ``child_guess`` is ``None`` when
    no recipient localpart could be parsed.
    """
    child = _localpart(payload.get("to", "")) or None
    household_id = f"household:{child}" if child else "household:unknown"
    return household_id, child


def ingest_forward(payload: dict, store: Store) -> str:
    """Persist a forwarded email as one raw record and return its ``raw_id``.

    The stored record wraps the ORIGINAL payload untouched under ``email`` and
    adds the routing guess, so downstream extraction has both the source of truth
    and a cheap hint without re-parsing.
    """
    household_id, child_guess = route_household(payload)
    record = {
        "email": payload,
        "routing": {"household_id": household_id, "child_guess": child_guess},
    }
    return store.put_raw(source=SOURCE, payload=record)


def create_app(store: Store | None = None) -> FastAPI:
    """Build the FastAPI app with an injected ``Store`` (default in-memory)."""
    app = FastAPI(title="FamilyOps ingest", version="0.0.1")
    app.state.store = store if store is not None else InMemoryStore()
    app.include_router(router)
    return app


router = APIRouter()


@router.post("/ingest/forward")
async def post_forward(email: ForwardedEmail, request: Request) -> dict[str, str]:
    """Webhook: accept a forwarded email and stash it as one raw record."""
    store: Store = request.app.state.store
    payload = email.model_dump(by_alias=True)
    raw_id = ingest_forward(payload, store)
    return {"raw_id": raw_id}
