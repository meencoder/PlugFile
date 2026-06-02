"""Provider-agnostic Model abstraction — the seam that lets us 'rent the engine'.

Both apps depend on `Model`, never on a concrete SDK. Swapping Claude for
Gemini (or running both for evals) is a one-line change at the call site.

The interface mirrors the Anthropic Messages tool-use shape because that is
the shape the tool loop in `toolloop.py` consumes. Concrete adapters translate
each provider into that shape. SDKs are imported lazily so importing this
module never requires a provider package to be installed.
"""

from __future__ import annotations

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

    Stubbed deliberately: the translation from Gemini's function-calling
    response into the Anthropic-style block shape is tracked as backlog
    item CH-3 so it lands with its own tests rather than untested here.
    """

    def __init__(self, model: str = "gemini-2.5-pro", client: Any | None = None) -> None:
        self._model = model
        self._client = client

    def create(self, *, system, messages, tools=None, max_tokens=4096):  # type: ignore[no-untyped-def]
        raise NotImplementedError(
            "GeminiModel.create is tracked as backlog item CH-3 "
            "(translate Gemini function-calling into the tool-loop block shape)."
        )
