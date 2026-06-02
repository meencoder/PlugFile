from __future__ import annotations

from types import SimpleNamespace

from agent_chassis import run_tool_loop


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_block(name, args, _id):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=_id)


class FakeModel:
    """Scripted model: first asks for a tool, then returns final text."""

    def __init__(self):
        self._calls = 0

    def create(self, *, system, messages, tools=None, max_tokens=4096):
        self._calls += 1
        if self._calls == 1:
            return SimpleNamespace(stop_reason="tool_use", content=[_tool_block("add", {"a": 2, "b": 3}, "t1")])
        return SimpleNamespace(stop_reason="end_turn", content=[_text_block("the answer is 5")])


def test_run_tool_loop_dispatches_then_returns_final_text():
    def dispatch(name, args):
        assert name == "add"
        return str(args["a"] + args["b"])

    result = run_tool_loop(
        FakeModel(),
        system="sys",
        tools=[{"name": "add"}],
        dispatch=dispatch,
        user_content="add 2 and 3",
    )
    assert result.final_text == "the answer is 5"
    assert result.tool_calls == ["add"]
    assert result.turns == 2
