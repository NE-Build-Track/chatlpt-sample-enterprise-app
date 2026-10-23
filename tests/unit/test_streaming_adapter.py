"""The SSE decoder and the streaming engine adapter over builder-core's FakeEngine."""

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from livepeer_builder.testing import Fails, FakeEngine, Reply, runner

from chatlpt.adapters.engine import CHAT_PATH, StreamingEngineChat, actor_for
from chatlpt.adapters.sse import SseDecoder
from chatlpt.contracts import ChatParams, ChatTurn, TokenUsage
from chatlpt.errors import ChatUnavailable, ReplyFailed
from chatlpt.testing import FixedClock

APP = "blueclaw/chat/qwen3.8-27b"
PARAMS = ChatParams(system_prompt="sys", temperature=Decimal("0.7"), max_output_tokens=64)
HI = [ChatTurn(role="user", content="hi")]
USER = UUID(int=3)


def sse(obj: dict[str, Any]) -> bytes:
    return b"data: " + json.dumps(obj).encode() + b"\n\n"


def delta(**fields: Any) -> dict[str, Any]:
    return {"choices": [{"index": 0, "delta": fields, "finish_reason": None}]}


def test_decoder_handles_split_frames_crlf_and_done() -> None:
    decoder = SseDecoder()
    first = sse(delta(content="Hel"))
    assert decoder.feed(first[:7]) == []  # half a frame buffers
    assert decoder.feed(first[7:]) == [delta(content="Hel")]
    assert decoder.feed(b'data: {"a": 1}\r\n\r\n: comment\n\n') == [{"a": 1}]
    assert decoder.feed(b"data: [DONE]\n\n") == [] and decoder.done
    assert decoder.feed(b'data: not json\n\ndata: {"b": 2}') == []
    assert decoder.flush() == [{"b": 2}] and decoder.flush() == []


def streaming_engine(*chunks: bytes | Fails, content_type: str = "text/event-stream") -> FakeEngine:
    reply = Reply(chunks=chunks, content_type=content_type)
    return FakeEngine(
        replies={(APP, CHAT_PATH): reply},
        runners=[runner(APP, url="https://r", orchestrator_url="https://orch.test:8935")],
        streaming=True,
    )


def backend(engine: FakeEngine) -> StreamingEngineChat:
    return StreamingEngineChat(engine, FixedClock(), app=APP, idle_timeout_s=45)


async def test_streaming_reply_yields_deltas_then_usage_and_done() -> None:
    engine = streaming_engine(
        sse(delta(reasoning="think ")),
        sse(delta(content="Hello")),
        sse(delta(content=", world")),
        sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
        sse(
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": 4,
                    "completion_tokens_details": {"reasoning_tokens": 1},
                },
            }
        ),
        b"data: [DONE]\n\n",
    )
    reply = await backend(engine).open_reply(USER, HI, PARAMS, operation_ref="op")
    [job] = await engine.jobs.list_jobs(actor_for(USER))
    assert reply.job_id == job.id and reply.orchestrator_url == "https://orch.test:8935"
    chunks = [c async for c in reply]
    assert [(c.kind, c.text) for c in chunks[:3]] == [
        ("reasoning", "think "),
        ("content", "Hello"),
        ("content", ", world"),
    ]
    assert chunks[-2].kind == "usage" and chunks[-2].usage == TokenUsage(
        prompt_tokens=9, completion_tokens=4, reasoning_tokens=1
    )
    assert chunks[-1].kind == "done" and chunks[-1].finish_reason == "stop"
    sent = engine.jobs.requests[0][1]
    assert sent.payload is not None and sent.payload["stream"] is True
    assert sent.payload["stream_options"] == {"include_usage": True} and sent.idle_timeout_s == 45


async def test_streaming_reply_falls_back_to_a_whole_json_body() -> None:
    body = json.dumps(
        {
            "choices": [{"message": {"content": "one shot"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }
    )
    engine = streaming_engine(body.encode(), content_type="application/json")
    reply = await backend(engine).open_reply(USER, HI, PARAMS, operation_ref="op")
    kinds = [(c.kind, c.text) async for c in reply]
    assert kinds[0] == ("content", "one shot") and kinds[-1][0] == "done"


async def test_failure_mid_stream_surfaces_as_an_uncertain_reply() -> None:
    engine = streaming_engine(sse(delta(content="partial")), Fails(kind="abandoned", message="gone"))
    reply = await backend(engine).open_reply(USER, HI, PARAMS, operation_ref="op")
    received: list[str] = []

    async def drain() -> None:
        async for chunk in reply:
            received.append(chunk.text)

    with pytest.raises(ReplyFailed) as error:
        await drain()
    assert received == ["partial"] and error.value.uncertain and error.value.payment_sent


async def test_open_errors_map_like_the_buffered_adapter() -> None:
    engine = FakeEngine(replies={(APP, CHAT_PATH): Fails(kind="no_offering", message="none")}, streaming=True)
    with pytest.raises(ChatUnavailable):
        await backend(engine).open_reply(UUID(int=1), HI, PARAMS, operation_ref="x")


def test_the_streaming_adapter_refuses_an_engine_that_cannot_stream() -> None:
    with pytest.raises(ValueError, match="cannot stream"):
        StreamingEngineChat(FakeEngine(streaming=False), FixedClock(), app=APP)
