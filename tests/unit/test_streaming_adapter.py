"""The SSE decoder and the streaming engine adapter over a fake JobStream."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from livepeer_builder import JobRequest
from livepeer_builder.contracts import Attempt, Failure, Job
from livepeer_builder.errors import JobFailed

from chatlpt.adapters.engine import APPLICATION_ID, StreamingEngineChat
from chatlpt.adapters.sse import SseDecoder
from chatlpt.contracts import ChatParams, ChatTurn, TokenUsage
from chatlpt.errors import ReplyFailed
from chatlpt.testing import FixedClock

APP = "blueclaw/chat/qwen3.8-27b"
NOW = datetime(2026, 10, 19, tzinfo=UTC)
PARAMS = ChatParams(system_prompt="sys", temperature=Decimal("0.7"), max_output_tokens=64)


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


class FakeJobStream:
    def __init__(self, frames: list[bytes | JobFailed], *, content_type: str = "text/event-stream") -> None:
        self._frames = frames
        self.content_type = content_type
        attempt = Attempt(
            job_id=uuid4(),
            number=1,
            runner_url="https://r",
            orchestrator_url="https://orch.test:8935",
            allocation_id="a",
            sessions=(),
            payment_sent=True,
            outcome="in_flight",
            status_code=200,
            started_at=NOW,
            ended_at=None,
        )
        self.job = Job(
            id=uuid4(),
            actor_id="u",
            application_id=APPLICATION_ID,
            operation_ref=None,
            mode="immediate",
            app=APP,
            capability=None,
            model=None,
            state="running",
            attempts=(attempt,),
            failure=None,
            result=None,
            usage=None,
            created_at=NOW,
            completed_at=None,
        )
        self.status_code = 200

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[bytes]:
        for frame in self._frames:
            if isinstance(frame, JobFailed):
                raise frame
            yield frame


class FakeJobs:
    def __init__(self, stream: FakeJobStream) -> None:
        self._stream = stream
        self.requests: list[JobRequest] = []
        self.streaming = self

    async def stream(self, actor: Any, request: JobRequest) -> FakeJobStream:
        self.requests.append(request)
        return self._stream


class FakeEngine:
    def __init__(self, stream: FakeJobStream) -> None:
        self.jobs = FakeJobs(stream)


def backend(stream: FakeJobStream) -> StreamingEngineChat:
    return StreamingEngineChat(FakeEngine(stream), FixedClock(), app=APP, idle_timeout_s=45)  # type: ignore[arg-type]


async def test_streaming_reply_yields_deltas_then_usage_and_done() -> None:
    frames = [
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
    ]
    stream = FakeJobStream(frames)
    chat = backend(stream)
    reply = await chat.open_reply(
        UUID(int=3), [ChatTurn(role="user", content="hi")], PARAMS, operation_ref="op"
    )
    assert reply.job_id == stream.job.id and reply.orchestrator_url == "https://orch.test:8935"
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
    request = FakeEngine(stream).jobs.requests or chat._engine.jobs.requests  # type: ignore[attr-defined]
    sent = request[0]
    assert sent.payload is not None and sent.payload["stream"] is True
    assert sent.payload["stream_options"] == {"include_usage": True} and sent.idle_timeout_s == 45


async def test_streaming_reply_falls_back_to_a_whole_json_body() -> None:
    body = json.dumps(
        {
            "choices": [{"message": {"content": "one shot"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }
    )
    stream = FakeJobStream([body.encode()], content_type="application/json")
    reply = await backend(stream).open_reply(
        UUID(int=3), [ChatTurn(role="user", content="hi")], PARAMS, operation_ref="op"
    )
    kinds = [(c.kind, c.text) async for c in reply]
    assert kinds[0] == ("content", "one shot") and kinds[-1][0] == "done"


async def test_failure_mid_stream_surfaces_as_an_uncertain_reply() -> None:
    failed_job = FakeJobStream([]).job.model_copy(
        update={"state": "uncertain", "failure": Failure(kind="abandoned", message="gone", payment_sent=True)}
    )
    stream = FakeJobStream([sse(delta(content="partial")), JobFailed(failed_job)])
    reply = await backend(stream).open_reply(
        UUID(int=3), [ChatTurn(role="user", content="hi")], PARAMS, operation_ref="op"
    )
    received: list[str] = []

    async def drain() -> None:
        async for chunk in reply:
            received.append(chunk.text)

    with pytest.raises(ReplyFailed) as error:
        await drain()
    assert received == ["partial"] and error.value.uncertain and error.value.payment_sent


async def test_open_errors_map_like_the_buffered_adapter() -> None:
    class Refusing:
        @property
        def streaming(self) -> "Refusing":
            return self

        async def stream(self, actor: Any, request: JobRequest) -> FakeJobStream:
            raise JobFailed(
                FakeJobStream([]).job.model_copy(
                    update={"state": "failed", "failure": Failure(kind="no_offering", message="none")}
                )
            )

    class Engine:
        jobs = Refusing()

    chat = StreamingEngineChat(Engine(), FixedClock(), app=APP)  # type: ignore[arg-type]
    from chatlpt.errors import ChatUnavailable

    with pytest.raises(ChatUnavailable):
        await chat.open_reply(UUID(int=1), [ChatTurn(role="user", content="hi")], PARAMS, operation_ref="x")


def test_the_streaming_adapter_refuses_an_engine_that_cannot_stream() -> None:
    class Buffered:
        streaming = None

    class Engine:
        jobs = Buffered()

    with pytest.raises(ValueError, match="cannot stream"):
        StreamingEngineChat(Engine(), FixedClock(), app=APP)  # type: ignore[arg-type]
