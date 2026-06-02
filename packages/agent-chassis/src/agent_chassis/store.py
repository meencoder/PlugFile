"""Storage interface + offline implementations for the agent kernel.

The chassis owns the VERB ("stash raw payloads, dedup parsed items") while the
apps own the NOUN (what an Item actually is). The store therefore never imports
a concrete item type: it speaks to the `HasDedupKey` Protocol and persists items
through `to_jsonable`, so any dataclass with a `dedup_key` works unchanged.

Both implementations are dependency-light and fully offline:
- `InMemoryStore` keeps everything in dicts.
- `SqliteStore` uses stdlib `sqlite3` (a file path or ":memory:").
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Protocol, runtime_checkable
from uuid import uuid4

from .serialize import to_jsonable


@runtime_checkable
class HasDedupKey(Protocol):
    """Any object exposing a stable `dedup_key` used for idempotent upserts."""

    @property
    def dedup_key(self) -> str: ...


class Store(Protocol):
    """Persistence boundary for raw payloads and deduped items."""

    def put_raw(self, source: str, payload: dict) -> str:
        """Store a raw payload from `source`; return a generated id."""
        ...

    def get_raw(self, raw_id: str) -> dict | None:
        """Return the payload previously stored under `raw_id`, or None."""
        ...

    def upsert_items(self, items: Iterable[HasDedupKey]) -> None:
        """Insert/replace items keyed by `dedup_key` (idempotent, no dupes)."""
        ...

    def get_items(self) -> list:
        """Return all stored items."""
        ...


class InMemoryStore:
    """Dict-backed `Store` implementation. Not thread-safe; offline only."""

    def __init__(self) -> None:
        self._raw: dict[str, dict] = {}
        self._items: dict[str, Any] = {}

    def put_raw(self, source: str, payload: dict) -> str:
        raw_id = uuid4().hex
        self._raw[raw_id] = {"source": source, "payload": payload}
        return raw_id

    def get_raw(self, raw_id: str) -> dict | None:
        row = self._raw.get(raw_id)
        if row is None:
            return None
        return row["payload"]

    def upsert_items(self, items: Iterable[HasDedupKey]) -> None:
        for item in items:
            self._items[item.dedup_key] = item

    def get_items(self) -> list:
        return list(self._items.values())


class SqliteStore:
    """stdlib-`sqlite3` `Store` implementation.

    Items are persisted as JSON (via `to_jsonable`) keyed by `dedup_key`;
    `get_items()` returns the stored dict rows.
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS raw ("
            "  id TEXT PRIMARY KEY,"
            "  source TEXT NOT NULL,"
            "  payload TEXT NOT NULL"
            ")"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS items ("
            "  dedup_key TEXT PRIMARY KEY,"
            "  data TEXT NOT NULL"
            ")"
        )
        self._conn.commit()

    def put_raw(self, source: str, payload: dict) -> str:
        raw_id = uuid4().hex
        self._conn.execute(
            "INSERT INTO raw (id, source, payload) VALUES (?, ?, ?)",
            (raw_id, source, json.dumps(to_jsonable(payload))),
        )
        self._conn.commit()
        return raw_id

    def get_raw(self, raw_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT payload FROM raw WHERE id = ?", (raw_id,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    def upsert_items(self, items: Iterable[HasDedupKey]) -> None:
        for item in items:
            self._conn.execute(
                "INSERT INTO items (dedup_key, data) VALUES (?, ?) "
                "ON CONFLICT(dedup_key) DO UPDATE SET data = excluded.data",
                (item.dedup_key, json.dumps(to_jsonable(item))),
            )
        self._conn.commit()

    def get_items(self) -> list:
        rows = self._conn.execute(
            "SELECT data FROM items ORDER BY dedup_key"
        ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def close(self) -> None:
        self._conn.close()
