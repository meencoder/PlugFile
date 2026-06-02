"""GeminiModel.create — Gemini function-calling -> tool-loop block shape.

These tests run with NO network and NO API key. A scripted fake client stands
in for `google-genai`: it returns a realistic Gemini response carrying a
function call on the first call, then a text answer on the second. That proves
the translation end-to-end through `run_tool_loop` with zero credentials and
without importing the SDK.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from agent_chassis import GeminiModel, run_tool_loop


def _gemini_response(parts):
    """Build a realistic Gemini response: candidates[0].content.parts."""
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))]
    )


def _function_call_part(name, args):
    return SimpleNamespace(function_call=SimpleNamespace(name=name, args=args), text=None)


def _text_part(text):
    return SimpleNamespace(function_call=None, text=text)


class _FakeModels:
    """Mimics `client.models` with a scripted generate_content."""

    def __init__(self):
        self.calls = 0
        self.received = []

    def generate_content(self, **kwargs):
        self.received.append(kwargs)
        self.calls += 1
        if self.calls == 1:
            # First turn: Gemini asks to call the `add` tool.
            return _gemini_response([_function_call_part("add", {"a": 2, "b": 3})])
        # Second turn: Gemini returns the final text answer.
        return _gemini_response([_text_part("the answer is 5")])


class FakeGeminiClient:
    """Stands in for `google.genai.Client` — no SDK, no key."""

    def __init__(self):
        self.models = _FakeModels()


def test_gemini_tool_loop_runs_one_tool_then_final_text():
    fake = FakeGeminiClient()

    def dispatch(name, args):
        assert name == "add"
        return str(args["a"] + args["b"])

    result = run_tool_loop(
        GeminiModel(client=fake),
        system="you are a calculator",
        tools=[
            {
                "name": "add",
                "description": "add two ints",
                "input_schema": {
                    "type": "object",
                    "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                    "required": ["a", "b"],
                },
            }
        ],
        dispatch=dispatch,
        user_content="add 2 and 3",
    )

    assert result.tool_calls == ["add"]
    assert result.turns == 2
    assert result.final_text == "the answer is 5"


def test_gemini_request_translation_carries_tools_and_system():
    """The first request must include the function declaration and system text."""
    fake = FakeGeminiClient()
    GeminiModel(client=fake).create(
        system="sys prompt",
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "add", "description": "d", "input_schema": {"type": "object"}}],
    )
    sent = fake.models.received[0]
    assert sent["config"]["system_instruction"] == "sys prompt"
    decls = sent["config"]["tools"][0]["function_declarations"]
    assert decls[0]["name"] == "add"
    assert sent["contents"][0]["role"] == "user"


def test_create_yields_tool_use_stop_reason_on_function_call():
    fake = FakeGeminiClient()
    resp = GeminiModel(client=fake).create(
        system="s", messages=[{"role": "user", "content": "go"}], tools=[{"name": "add"}]
    )
    assert resp.stop_reason == "tool_use"
    block = resp.content[0]
    assert block.type == "tool_use"
    assert block.name == "add"
    assert block.input == {"a": 2, "b": 3}
    assert block.id == "call_0"


@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="live smoke test — set GEMINI_API_KEY to run",
)
def test_gemini_live_smoke():  # pragma: no cover - network
    def dispatch(name, args):
        return str(args.get("a", 0) + args.get("b", 0))

    result = run_tool_loop(
        GeminiModel(),
        system="you are a calculator; use the add tool",
        tools=[
            {
                "name": "add",
                "description": "add two ints",
                "input_schema": {
                    "type": "object",
                    "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                    "required": ["a", "b"],
                },
            }
        ],
        dispatch=dispatch,
        user_content="What is 2 plus 3? Use the add tool.",
    )
    assert result.final_text
