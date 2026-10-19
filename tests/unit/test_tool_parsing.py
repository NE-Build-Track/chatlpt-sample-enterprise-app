"""Tool calls on the wire: buffered, streamed in fragments, and the turns we send back."""

import json

from chatlpt.adapters.engine import parse_completion
from chatlpt.adapters.openai_wire import ToolCallAssembler, parse_tool_calls, wire_turn
from chatlpt.contracts import ChatTurn, ToolCall


def test_buffered_tool_calls_are_parsed() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "generate_image", "arguments": json.dumps({"prompt": "x"})},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    kinds = [(c.kind, c.tool_call.name if c.tool_call else None) for c in parse_completion(data)]
    assert kinds == [("tool_call", "generate_image"), ("usage", None), ("done", None)]
    assert parse_tool_calls([{"function": {"name": "f", "arguments": "not json"}}])[0].arguments == {
        "_raw": "not json"
    }
    assert parse_tool_calls([{"function": {"arguments": "{}"}}]) == []  # no name, no call


def test_streamed_fragments_are_stitched_by_index() -> None:
    assembler = ToolCallAssembler()
    frames = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_9",
                                "type": "function",
                                "function": {"name": "generate_image", "arguments": ""},
                            }
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"prompt": "a '}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'fox"}'}}]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    for frame in frames:
        assembler.feed(frame)
    assert assembler.result() == [ToolCall(id="call_9", name="generate_image", arguments={"prompt": "a fox"})]


def test_wire_turns_carry_tool_calls_and_results() -> None:
    call = ToolCall(id="c1", name="generate_image", arguments={"prompt": "p"})
    assistant = wire_turn(ChatTurn(role="assistant", content="", tool_calls=(call,)))
    assert (
        assistant["content"] is None
        and assistant["tool_calls"][0]["function"]["arguments"] == '{"prompt": "p"}'
    )
    tool = wire_turn(ChatTurn(role="tool", content="{}", tool_call_id="c1"))
    assert tool == {"role": "tool", "content": "{}", "tool_call_id": "c1"}
    assert wire_turn(ChatTurn(role="user", content="hi")) == {"role": "user", "content": "hi"}
