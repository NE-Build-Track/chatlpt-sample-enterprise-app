"""BufferedEngineChat over builder-core's FakeEngine: readiness, the paid call, model info, costs, errors."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from livepeer_builder import EngineError, EngineHealth, Fees, JobCost, NoCapacity, Runner
from livepeer_builder.testing import Fails, FakeEngine, Raises, Reply, runner

from chatlpt.adapters.engine import APPLICATION_ID, CHAT_PATH, MODELS_PATH, BufferedEngineChat, actor_for
from chatlpt.contracts import ChatParams, ChatTurn, TokenUsage
from chatlpt.errors import ChatUnavailable, Conflict, NotFound, ReplyFailed
from chatlpt.testing import FixedClock

APP = "blueclaw/chat/qwen3.8-27b"
NOW = datetime(2026, 10, 19, tzinfo=UTC)
PARAMS = ChatParams(system_prompt="sys", temperature=Decimal("0.7"), max_output_tokens=256)
HI = [ChatTurn(role="user", content="hi")]
COMPLETION = {
    "choices": [{"message": {"content": "hey"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
}
CHAT_RUNNER = runner(APP, url="https://r", orchestrator_url="https://o:1")
ANSWERED = Reply(data=COMPLETION)


def health(*, ready: bool = True, fresh: bool = True) -> EngineHealth:
    return EngineHealth(
        ready=ready,
        discovery_fresh=fresh,
        discovery_observed_at=NOW,
        discovery_error=None,
        cost_sync_at=None,
        cost_sync_error=None,
        running_jobs=0,
        allocation_mode="per_application",
        version="t",
    )


def engine_with(
    chat: Reply | Fails | Raises = ANSWERED,
    *,
    models: dict[str, Any] | None = None,
    runners: tuple[Runner, ...] = (CHAT_RUNNER,),
    costs: dict[UUID, JobCost | Raises] | None = None,
    ready: bool = True,
    fresh: bool = True,
) -> FakeEngine:
    replies: dict[tuple[str, str], Reply | Fails | Raises] = {(APP, CHAT_PATH): chat}
    if models is not None:
        replies[(APP, MODELS_PATH)] = Reply(data=models)
    return FakeEngine(replies=replies, runners=runners, costs=costs, health=health(ready=ready, fresh=fresh))


def backend(engine: FakeEngine) -> BufferedEngineChat:
    return BufferedEngineChat(engine, FixedClock(), app=APP)


def pending(job_id: UUID) -> JobCost:
    return JobCost(
        job_id=job_id, status="pending", fees=Fees(), attempts=(), first_observed_at=None, updated_at=None
    )


def test_actor_context_is_scoped_to_the_app() -> None:
    actor = actor_for(UUID(int=7))
    assert (
        actor.application_id == APPLICATION_ID
        and "jobs.run" in actor.permissions
        and actor.credential_kind == "actor"
    )


def test_ready_reports_each_reason() -> None:
    assert backend(engine_with()).ready() == (True, None)
    no_runner = backend(engine_with(runners=())).ready()
    assert no_runner[0] is False and "no runner" in (no_runner[1] or "")
    assert backend(engine_with(fresh=False)).ready() == (False, "runner discovery is stale")
    assert backend(engine_with(ready=False)).ready() == (False, "the engine is not ready")


async def test_open_reply_builds_the_job_and_yields_the_parsed_body() -> None:
    engine = engine_with()
    stream = await backend(engine).open_reply(UUID(int=1), HI, PARAMS, operation_ref="op-1")
    actor, request = engine.jobs.requests[0]
    assert actor.actor_id == str(UUID(int=1)) and request.app == APP and request.path == CHAT_PATH
    assert request.operation_ref == "op-1" and request.payload is not None
    assert (
        request.payload["messages"] == [{"role": "user", "content": "hi"}]
        and request.payload["stream"] is False
    )
    assert request.payload["chat_template_kwargs"] == {"enable_thinking": True}
    assert request.payload["max_tokens"] == 256
    kinds = [c.kind async for c in stream]
    assert kinds == ["content", "usage", "done"]
    assert stream.job_id is not None and stream.orchestrator_url == "https://o:1"  # from the job's attempt


async def test_model_info_reads_max_model_len() -> None:
    engine = engine_with(models={"object": "list", "data": [{"id": "Qwen3.8-27B", "max_model_len": 40960}]})
    info = await backend(engine).model_info(UUID(int=1))
    assert info.model_id == "Qwen3.8-27B" and info.max_model_len == 40960 and info.app == APP
    request = engine.jobs.requests[0][1]
    assert request.method == "GET" and request.path == MODELS_PATH
    with pytest.raises(ReplyFailed):
        await backend(engine_with(models={"data": [{"id": "x"}]})).model_info(UUID(int=1))


async def test_wholesale_maps_engine_errors() -> None:
    priced, missing, down = uuid4(), uuid4(), uuid4()
    chat = backend(engine_with(costs={priced: pending(priced), down: Raises(EngineError("down"))}))
    assert (await chat.wholesale(UUID(int=1), priced)).status == "pending"
    with pytest.raises(NotFound):
        await chat.wholesale(UUID(int=1), missing)
    with pytest.raises(ChatUnavailable):
        await chat.wholesale(UUID(int=1), down)


async def test_report_usage_reaches_the_engine_and_maps_its_errors() -> None:
    engine = engine_with()
    chat = backend(engine)
    reply = await chat.open_reply(UUID(int=1), HI, PARAMS, operation_ref="op")
    assert reply.job_id is not None
    await chat.report_usage(
        UUID(int=1), reply.job_id, TokenUsage(prompt_tokens=1, completion_tokens=2, reasoning_tokens=1)
    )
    assert engine.jobs.usage_reports == [
        (reply.job_id, {"prompt_tokens": 1, "completion_tokens": 2, "reasoning_tokens": 1})
    ]
    negative = TokenUsage(prompt_tokens=0, completion_tokens=0).model_copy(update={"prompt_tokens": -1})
    with pytest.raises(ChatUnavailable):  # the engine refuses negative quantities
        await chat.report_usage(UUID(int=1), reply.job_id, negative)
    with pytest.raises(ChatUnavailable):  # and a job it does not know
        await chat.report_usage(UUID(int=1), uuid4(), TokenUsage(prompt_tokens=1, completion_tokens=1))


async def test_run_maps_every_engine_exception() -> None:
    with pytest.raises(ChatUnavailable):
        await backend(engine_with(Raises(NoCapacity("busy")))).open_reply(UUID(int=1), HI, PARAMS, "a")
    with pytest.raises(ReplyFailed) as plain:
        await backend(engine_with(Raises(EngineError("odd")))).open_reply(UUID(int=1), HI, PARAMS, "c")
    assert plain.value.payment_sent is False
    paid_failure = Fails(message="500", body="trace", payment_sent=True)
    with pytest.raises(ReplyFailed) as paid:
        await backend(engine_with(paid_failure)).open_reply(UUID(int=1), HI, PARAMS, "d")
    assert paid.value.payment_sent and "trace" in str(paid.value)
    with pytest.raises(ChatUnavailable):
        await backend(engine_with(Fails(kind="no_offering", message="none"))).open_reply(
            UUID(int=1), HI, PARAMS, "e"
        )


async def test_a_repeated_operation_ref_is_a_conflict() -> None:
    chat = backend(engine_with())
    await chat.open_reply(UUID(int=1), HI, PARAMS, operation_ref="same")
    with pytest.raises(Conflict):  # the engine refuses to dispatch the same operation twice
        await chat.open_reply(UUID(int=1), HI, PARAMS, operation_ref="same")
