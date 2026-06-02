"""agent-chassis — the shared, domain-free agent kernel.

Reuse rule of thumb: the chassis owns the VERB (call an LLM for structured
output, run a tool loop, serialize results, swap providers); the apps
(plugfile, familyops) own the NOUN (W-3 forms, family graphs).

Nothing in this package may import from `plugfile` or `familyops`.
"""

from __future__ import annotations

from .serialize import to_jsonable
from .model import Model, AnthropicModel, GeminiModel
from .toolloop import ToolLoopResult, run_tool_loop
from .store import Store, InMemoryStore, SqliteStore, HasDedupKey

__all__ = [
    "to_jsonable",
    "Model",
    "AnthropicModel",
    "GeminiModel",
    "ToolLoopResult",
    "run_tool_loop",
    "Store",
    "InMemoryStore",
    "SqliteStore",
    "HasDedupKey",
]
