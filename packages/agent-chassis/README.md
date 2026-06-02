# agent-chassis

Shared, domain-free agent kernel consumed by `plugfile` and `familyops`.

The chassis owns the VERB (call an LLM for structured output, run a tool loop,
serialize results, swap providers); the apps own the NOUN (W-3 forms, family
graphs). Nothing here may import from `plugfile` or `familyops`.

## What's inside

- `model` — provider-agnostic `Model` protocol plus `AnthropicModel` and
  `GeminiModel` adapters. Provider SDKs are optional extras imported lazily, so
  importing this package never requires a provider package or API key.
- `toolloop` — `run_tool_loop`, a generic LLM tool-use loop.
- `serialize` — JSON helpers (`to_jsonable`).

## Install

Provider SDKs are optional extras:

```
uv sync --package agent-chassis --extra dev      # tests only, no SDK
uv sync --package agent-chassis --extra gemini   # google-genai
uv sync --package agent-chassis --extra anthropic
```
