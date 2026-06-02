# agent-chassis

The shared, domain-free agent kernel for the PlugFile workspace.

Reuse rule of thumb: the chassis owns the VERB (call an LLM for structured
output, run a tool loop, serialize results, swap providers, store/dedup items);
the apps (`plugfile`, `familyops`) own the NOUN (W-3 forms, family graphs).

Nothing in this package may import from `plugfile` or `familyops`.

## Modules

- `serialize` — recursive dataclass/collection -> JSON-friendly conversion.
- `model` — model-provider abstraction (Anthropic, Gemini).
- `toolloop` — structured-extraction tool loop.
- `store` — storage interface with offline in-memory and SQLite implementations.
