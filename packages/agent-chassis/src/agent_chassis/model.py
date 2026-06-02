"""Provider-agnostic Model abstraction — the seam that lets us 'rent the engine'.

Both apps depend on `Model`, never on a concrete SDK. Swapping Claude for
Gemini (or running both for evals) is a one-line change at the call site.

The interface mirrors the Anthropic Messages tool-use shape because that is
the shape the tool loop in `toolloop.py` consumes. Concrete adapters translate
each provider into that shape. SDKs are imported lazily so importing this
module never requires a provider package to be installed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Model(Protocol):
    """Minimal contract the tool loop needs from any LLM provider."""

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> Any:
        """Return a response exposing `.stop_reason` and `.content`
        (a list of blocks with `.type`, and for tool_use: `.name`,
        `.input`, `.id`)."""
        ...


class AnthropicModel:
    """Claude adapter. Requires the `anthropic` extra."""

    def __init__(self, model: str = "claude-sonnet-4-5", client: Any | None = None) -> None:
        if client is None:
            from anthropic import Anthropic  # lazy import

            client = Anthropic()
        self._client = client
        self._model = model

    def create(self, *, system, messages, tools=None, max_tokens=4096):  # type: ignore[no-untyped-def]
        return self._client.messages.create(
            model=self._model,
            system=system,
            messages=messages,
            tools=tools or [],
            max_tokens=max_tokens,
        )


class GeminiModel:
    """Gemini adapter (Vertex / AI Studio). Requires the `gemini` extra.

    Translates Gemini's function-calling response into the Anthropic-style
    block shape that `toolloop.run_tool_loop` consumes. The translation is
    duck-typed: it reads attributes off whatever the client returns rather
    than importing `google-genai`. The SDK is imported lazily, and only when
    we must construct a real client (`client is None`), so importing this
    module — and running the tests — needs neither the SDK nor an API key.
    """

    def __init__(self, model: str = "gemini-2.5-pro", client: Any | None = None) -> None:
        self._model = model
        if client is None:
            # Lazy import — only the real-client path touches the SDK / key.
            import os

            from google import genai  # type: ignore[import-not-found]

            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self._client = client

    def create(self, *, system, messages, tools=None, max_tokens=4096):  # type: ignore[no-untyped-def]
        """Call the Gemini client and translate the result into the
        Anthropic-style response shape (`.stop_reason` + `.content` blocks)."""
        request = _to_gemini_request(
            model=self._model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
        )
        raw = self._client.models.generate_content(**request)
        return _to_anthropic_response(raw)


# --- translation helpers (duck-typed; no google-genai import) ----------------


def _to_gemini_request(*, model, system, messages, tools, max_tokens):  # type: ignore[no-untyped-def]
    """Minimal chassis -> Gemini request translation for a single-tool loop.

    Chassis tools are Anthropic-shaped (name/description/input_schema). Gemini
    wants function declarations (name/description/parameters). Messages map
    role "assistant" -> "model"; everything else stays "user". Content blocks
    are reduced to plain text parts, which is enough to drive the loop.
    """
    function_declarations = [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
        }
        for t in (tools or [])
    ]

    contents = []
    for msg in messages:
        role = "model" if msg.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": _content_to_text(msg.get("content"))}]})

    request: dict[str, Any] = {
        "model": model,
        "contents": contents,
        "config": {
            "max_output_tokens": max_tokens,
            "system_instruction": system,
        },
    }
    if function_declarations:
        request["config"]["tools"] = [{"function_declarations": function_declarations}]
    return request


def _content_to_text(content: Any) -> str:
    """Flatten a chassis message `content` (str or list of blocks) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text") or block.get("content")
        if text:
            parts.append(str(text))
    return "".join(parts)


def _to_anthropic_response(raw: Any) -> SimpleNamespace:
    """Translate a Gemini function-calling response into the Anthropic-style
    `.stop_reason` + `.content` shape, reading attributes duck-typed.

    Each Gemini function call -> a `tool_use` block; each text part -> a
    `text` block. `stop_reason` is "tool_use" when any function call is
    present, else "end_turn".
    """
    parts = _extract_parts(raw)

    content: list[SimpleNamespace] = []
    call_index = 0
    for part in parts:
        fn = getattr(part, "function_call", None)
        if fn is None and isinstance(part, dict):
            fn = part.get("function_call")
        if fn is not None:
            name = getattr(fn, "name", None)
            args = getattr(fn, "args", None)
            if isinstance(fn, dict):
                name = fn.get("name")
                args = fn.get("args")
            content.append(
                SimpleNamespace(
                    type="tool_use",
                    name=name,
                    input=dict(args or {}),
                    id=f"call_{call_index}",
                )
            )
            call_index += 1
            continue

        text = getattr(part, "text", None)
        if text is None and isinstance(part, dict):
            text = part.get("text")
        if text:
            content.append(SimpleNamespace(type="text", text=text))

    stop_reason = "tool_use" if call_index else "end_turn"
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def _extract_parts(raw: Any) -> list[Any]:
    """Pull the list of content parts out of a Gemini response, duck-typed.

    Real shape: response.candidates[0].content.parts. We tolerate dicts and
    missing pieces so fakes and live responses both work.
    """
    candidates = getattr(raw, "candidates", None)
    if candidates is None and isinstance(raw, dict):
        candidates = raw.get("candidates")
    if not candidates:
        return []
    first = candidates[0]
    content = getattr(first, "content", None)
    if content is None and isinstance(first, dict):
        content = first.get("content")
    parts = getattr(content, "parts", None)
    if parts is None and isinstance(content, dict):
        parts = content.get("parts")
    return list(parts or [])
