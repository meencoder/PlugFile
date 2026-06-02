"""Generic LLM tool-use loop.

Extracted as a reusable pattern from plugfile's hand-rolled loop. The app
supplies the system prompt, the tool schemas, and a `dispatch` callable that
maps (tool_name, args) -> JSON-string result. The chassis owns the loop
mechanics; the app owns what the tools actually do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .model import Model

Dispatch = Callable[[str, dict[str, Any]], str]


@dataclass
class ToolLoopResult:
    final_text: str
    tool_calls: list[str] = field(default_factory=list)
    turns: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)


def run_tool_loop(
    model: Model,
    *,
    system: str,
    tools: list[dict[str, Any]],
    dispatch: Dispatch,
    user_content: str,
    max_turns: int = 12,
) -> ToolLoopResult:
    """Drive a provider through tool calls until it stops requesting tools.

    Returns the final assistant text plus a record of which tools were used
    (handy for the eval harness and for audit/trust surfaces).
    """
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
    tool_calls: list[str] = []

    for turn in range(1, max_turns + 1):
        resp = model.create(system=system, messages=messages, tools=tools)
        if getattr(resp, "stop_reason", None) != "tool_use":
            text = "".join(
                getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
            )
            return ToolLoopResult(final_text=text, tool_calls=tool_calls, turns=turn, messages=messages)

        results = []
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use":
                tool_calls.append(block.name)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": dispatch(block.name, block.input),
                    }
                )
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"tool loop did not converge within {max_turns} turns")
