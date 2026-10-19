"""BufferedEngineChat against a duck-typed engine: readiness, the paid call, model info, costs, errors."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from livepeer_builder import ActorContext, EngineHealth, JobRequest, JobResult, NoCapacity, OperationExists
from livepeer_builder.contracts import Attempt, Failure, Job, Runner
from livepeer_builder.contracts.costs import Fees, JobCost
from livepeer_builder.errors import EngineError, JobFailed
from livepeer_builder.errors import NotFound as EngineNotFound

from chatlpt.adapters.engine import APPLICATION_ID, BufferedEngineChat, actor_for
from chatlpt.contracts import ChatParams, ChatTurn, TokenUsage
from chatlpt.errors import ChatUnavailable, Conflict, NotFound, ReplyFailed
from chatlpt.testing import FixedClock

APP = "blueclaw/chat/qwen3.8-27b"
NOW = datetime(2026, 10, 19, tzinfo=UTC)
PARAMS = ChatParams(system_prompt="sys", temperature=Decimal("0.7"), max_output_tokens=256)


def job(
    *, state: str = "succeeded", failure: Failure | None = None, orchestrator: str | None = "https://o:1"
) -> Job:
    attempt = Attempt(
        job_id=uuid4(),
        number=1,
        runner_url="https://r",
        orchestrator_url=orchestrator,
        allocation_id="alloc",
        sessions=(),
        payment_sent=True,
        outcome="succeeded",
        status_code=200,
        started_at=NOW,
        ended_at=NOW,
    )
    return Job(
        id=uuid4(),
        actor_id="u",
        application_id=APPLICATION_ID,
        operation_ref=None,
        mode="immediate",
        app=APP,
        capability=None,
        model=None,
        state=state,
        attempts=(attempt,),
        failure=failure,  # type: ignore[arg-type]
        result=None,
        usage=None,
        created_at=NOW,
        completed_at=NOW,
    )


def result(data: dict[str, Any]) -> JobResult:
    return JobResult(job=job(), status_code=200, content=b"{}", content_type="application/json", data=data)


class FakeJobs:
    def __init__(self) -> None:
        self.requests: list[tuple[ActorContext, JobRequest]] = []
        self.outcome: Any = result(
            {
                "choices": [{"message": {"content": "hey"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            }
        )
        self.reported: list[dict[str, int]] = []

    async def run(self, actor: ActorContext, request: JobRequest) -> JobResult:
        self.requests.append((actor, request))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome  # type: ignore[no-any-return]

    async def report_usage(self, actor: ActorContext, job_id: UUID, quantities: dict[str, int]) -> None:
        self.reported.append(quantities)
        if quantities.get("prompt_tokens") == -1:
            raise EngineError("boom")


class FakeCosts:
    def __init__(self) -> None:
        self.cost: Any = JobCost(
            job_id=uuid4(),
            status="pending",
            fees=Fees(),
            attempts=(),
            first_observed_at=None,
            updated_at=None,
        )

    async def for_job(self, actor: ActorContext, job_id: UUID) -> JobCost:
        if isinstance(self.cost, BaseException):
            raise self.cost
        return self.cost  # type: ignore[no-any-return]


class FakeDiscovery:
    def __init__(self) -> None:
        self.runners: list[Runner] = [
            Runner(
                url="https://r",
                app=APP,
                runner_id=None,
                mode="single-shot",
                orchestrator_url="https://o:1",
                capacity=1,
                capacity_available=1,
                rate=None,
            )
        ]

    def candidates(self, app: str) -> list[Runner]:
        return [r for r in self.runners if r.app == app]


class FakeEngine:
    def __init__(self) -> None:
        self.jobs = FakeJobs()
        self.costs = FakeCosts()
        self.discovery = FakeDiscovery()
        self.ready = True
        self.fresh = True

    def health(self) -> EngineHealth:
        return EngineHealth(
            ready=self.ready,
            discovery_fresh=self.fresh,
            discovery_observed_at=NOW,
            discovery_error=None,
            cost_sync_at=None,
            cost_sync_error=None,
            running_jobs=0,
            allocation_mode="per_application",
            version="t",
        )


@pytest.fixture
def engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def backend(engine: FakeEngine) -> BufferedEngineChat:
    return BufferedEngineChat(engine, FixedClock(), app=APP)  # type: ignore[arg-type]


def test_actor_context_is_scoped_to_the_app(backend: BufferedEngineChat) -> None:
    actor = actor_for(UUID(int=7))
    assert (
        actor.application_id == APPLICATION_ID
        and "jobs.run" in actor.permissions
        and actor.credential_kind == "actor"
    )


def test_ready_reports_each_reason(backend: BufferedEngineChat, engine: FakeEngine) -> None:
    assert backend.ready() == (True, None)
    engine.discovery.runners = []
    assert backend.ready()[0] is False and "no runner" in (backend.ready()[1] or "")
    engine.fresh = False
    assert backend.ready() == (False, "runner discovery is stale")
    engine.ready = False
    assert backend.ready() == (False, "the engine is not ready")


async def test_open_reply_builds_the_job_and_yields_the_parsed_body(
    backend: BufferedEngineChat, engine: FakeEngine
) -> None:
    stream = await backend.open_reply(
        UUID(int=1), [ChatTurn(role="user", content="hi")], PARAMS, operation_ref="op-1"
    )
    actor, request = engine.jobs.requests[0]
    assert (
        actor.actor_id == str(UUID(int=1)) and request.app == APP and request.path == "/v1/chat/completions"
    )
    assert request.operation_ref == "op-1" and request.payload is not None
    assert (
        request.payload["messages"] == [{"role": "user", "content": "hi"}]
        and request.payload["stream"] is False
    )
    assert (
        request.payload["chat_template_kwargs"] == {"enable_thinking": True}
        and request.payload["max_tokens"] == 256
    )
    kinds = [c.kind async for c in stream]
    assert kinds == ["content", "usage", "done"]
    assert stream.job_id is not None and stream.orchestrator_url == "https://o:1"


async def test_model_info_reads_max_model_len(backend: BufferedEngineChat, engine: FakeEngine) -> None:
    engine.jobs.outcome = result({"object": "list", "data": [{"id": "Qwen3.8-27B", "max_model_len": 40960}]})
    info = await backend.model_info(UUID(int=1))
    assert info.model_id == "Qwen3.8-27B" and info.max_model_len == 40960 and info.app == APP
    assert engine.jobs.requests[0][1].method == "GET" and engine.jobs.requests[0][1].path == "/v1/models"
    engine.jobs.outcome = result({"data": [{"id": "x"}]})
    with pytest.raises(ReplyFailed):
        await backend.model_info(UUID(int=1))


async def test_wholesale_and_report_usage_map_engine_errors(
    backend: BufferedEngineChat, engine: FakeEngine
) -> None:
    assert (await backend.wholesale(UUID(int=1), uuid4())).status == "pending"
    engine.costs.cost = EngineNotFound("nope")
    with pytest.raises(NotFound):
        await backend.wholesale(UUID(int=1), uuid4())
    engine.costs.cost = EngineError("down")
    with pytest.raises(ChatUnavailable):
        await backend.wholesale(UUID(int=1), uuid4())
    await backend.report_usage(
        UUID(int=1), uuid4(), TokenUsage(prompt_tokens=1, completion_tokens=2, reasoning_tokens=1)
    )
    assert engine.jobs.reported == [{"prompt_tokens": 1, "completion_tokens": 2, "reasoning_tokens": 1}]
    with pytest.raises(ChatUnavailable):
        await backend.report_usage(
            UUID(int=1),
            uuid4(),
            TokenUsage(prompt_tokens=-1 + 1, completion_tokens=0).model_copy(update={"prompt_tokens": -1}),
        )


async def test_run_maps_every_engine_exception(backend: BufferedEngineChat, engine: FakeEngine) -> None:
    turns = [ChatTurn(role="user", content="hi")]
    engine.jobs.outcome = NoCapacity("busy")
    with pytest.raises(ChatUnavailable):
        await backend.open_reply(UUID(int=1), turns, PARAMS, operation_ref="a")
    engine.jobs.outcome = OperationExists(job())
    with pytest.raises(Conflict):
        await backend.open_reply(UUID(int=1), turns, PARAMS, operation_ref="b")
    engine.jobs.outcome = EngineError("odd")
    with pytest.raises(ReplyFailed) as plain:
        await backend.open_reply(UUID(int=1), turns, PARAMS, operation_ref="c")
    assert plain.value.payment_sent is False
    engine.jobs.outcome = JobFailed(
        job(
            state="failed",
            failure=Failure(kind="runner_error", message="500", body="trace", payment_sent=True),
        )
    )
    with pytest.raises(ReplyFailed) as paid:
        await backend.open_reply(UUID(int=1), turns, PARAMS, operation_ref="d")
    assert paid.value.payment_sent and "trace" in str(paid.value)
    engine.jobs.outcome = JobFailed(job(state="failed", failure=None))
    with pytest.raises(ReplyFailed):
        await backend.open_reply(UUID(int=1), turns, PARAMS, operation_ref="e")
