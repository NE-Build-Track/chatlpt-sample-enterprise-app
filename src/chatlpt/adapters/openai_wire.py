"""OpenAI chat-completion wire details: tool calls in and out, with no third-party code."""

import json
from typing import Any

from chatlpt.contracts import ChatTurn, ToolCall


class ToolCallAssembler:
    """Streamed tool calls arrive as fragments keyed by index; this stitches them back together."""

    def __init__(self) -> None:
        self._parts: dict[int, dict[str, Any]] = {}

    def feed(self, event: dict[str, Any]) -> None:
        choices = event.get("choices")
        for choice in choices if isinstance(choices, list) else []:
            delta_raw = choice.get("delta") if isinstance(choice, dict) else None
            delta: dict[str, Any] = delta_raw if isinstance(delta_raw, dict) else {}
            raw_calls = delta.get("tool_calls")
            for fragment_raw in raw_calls if isinstance(raw_calls, list) else []:
                if not isinstance(fragment_raw, dict):
                    continue
                fragment: dict[str, Any] = fragment_raw
                index = fragment.get("index", 0)
                part = self._parts.setdefault(int(index) if isinstance(index, int) else 0, {"arguments": ""})
                if fragment.get("id"):
                    part["id"] = fragment["id"]
                function_raw = fragment.get("function")
                function: dict[str, Any] = function_raw if isinstance(function_raw, dict) else {}
                if function.get("name"):
                    part["name"] = function["name"]
                if isinstance(function.get("arguments"), str):
                    part["arguments"] += function["arguments"]

    def result(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for index in sorted(self._parts):
            part = self._parts[index]
            call = _tool_call(part.get("id"), part.get("name"), part.get("arguments"), index)
            if call is not None:
                calls.append(call)
        return calls


def parse_tool_calls(raw: object) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for index, item_raw in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item_raw, dict):
            continue
        item: dict[str, Any] = item_raw
        function_raw = item.get("function")
        function: dict[str, Any] = function_raw if isinstance(function_raw, dict) else {}
        call = _tool_call(item.get("id"), function.get("name"), function.get("arguments"), index)
        if call is not None:
            calls.append(call)
    return calls


def _tool_call(call_id: object, name: object, arguments: object, index: int) -> ToolCall | None:
    if not isinstance(name, str) or not name:
        return None
    parsed: Any = arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments or "{}")
        except ValueError:
            parsed = {"_raw": arguments}
    if not isinstance(parsed, dict):
        parsed = {}
    return ToolCall(id=str(call_id) if call_id else f"call_{index}", name=name, arguments=parsed)


def wire_turn(turn: ChatTurn) -> dict[str, Any]:
    """A ChatTurn in the OpenAI messages shape, including tool calls and tool results."""
    message: dict[str, Any] = {"role": turn.role, "content": turn.content}
    if turn.tool_calls:
        message["tool_calls"] = [
            {
                "type": "function",
                "id": c.id,
                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
            }
            for c in turn.tool_calls
        ]
        if not turn.content:
            message["content"] = None
    if turn.role == "tool" and turn.tool_call_id:
        message["tool_call_id"] = turn.tool_call_id
    return message
