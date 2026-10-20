"""The ChatBackend over the embedded livepeer-builder engine (docs/references/builder-engine.md).

Two implementations of the same port (D20): ``StreamingEngineChat`` uses the engine's ``jobs.stream``
and yields reply deltas as the runner emits them (docs/design-docs/streaming-through-the-engine.md);
``BufferedEngineChat`` uses ``jobs.run`` and yields the whole body at the end, for an engine without
streaming. The runtime picks the first when the engine offers ``jobs.stream``.
"""

import json
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from livepeer_builder import (
    ActorContext,
    BuilderEngine,
    CostSummary,
    JobCost,
    JobFailed,
    JobRequest,
    NoCapacity,
    NotProvisioned,
    OperationConflict,
    OperationExists,
    ProviderUnavailable,
)
from livepeer_builder.errors import EngineError
from livepeer_builder.errors import NotFound as EngineNotFound

from chatlpt.adapters.openai_wire import ToolCallAssembler, parse_tool_calls, wire_turn
from chatlpt.adapters.sse import SseDecoder
from chatlpt.contracts import (
    ChatParams,
    ChatTurn,
    ModelInfo,
    Money,
    NetworkTotals,
    ReplyChunk,
    TokenUsage,
    ToolSpec,
    WholesaleCost,
)
from chatlpt.errors import ChatUnavailable, Conflict, NotFound, ReplyFailed
from chatlpt.protocols import Clock

_LOG = logging.getLogger(__name__)
APPLICATION_ID = "chatlpt"
PERMISSIONS = frozenset({"discover", "jobs.run", "jobs.read", "costs.read"})
CHAT_PATH = "/v1/chat/completions"
MODELS_PATH = "/v1/models"
_UNAVAILABLE_KINDS = {"no_offering", "no_capacity", "not_provisioned", "refused", "unreachable", "payment"}


def actor_for(user_id: UUID) -> ActorContext:
    return ActorContext(actor_id=str(user_id), application_id=APPLICATION_ID, permissions=PERMISSIONS)


class BufferedReply:
    """The ReplyStream a buffered call produces: everything is known before the first chunk."""

    def __init__(
        self, job_id: UUID | None, orchestrator_url: str | None, chunks: Sequence[ReplyChunk]
    ) -> None:
        self._job_id = job_id
        self._orchestrator_url = orchestrator_url
        self._chunks = list(chunks)

    @property
    def job_id(self) -> UUID | None:
        return self._job_id

    @property
    def orchestrator_url(self) -> str | None:
        return self._orchestrator_url

    def __aiter__(self) -> AsyncIterator[ReplyChunk]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[ReplyChunk]:
        for chunk in self._chunks:
            yield chunk


class BufferedEngineChat:
    def __init__(
        self,
        engine: BuilderEngine,
        clock: Clock,
        *,
        app: str,
        max_attempts: int = 3,
        idle_timeout_s: float | None = None,
    ) -> None:
        self._engine = engine
        self._clock = clock
        self.app = app
        self._max_attempts = max_attempts
        self._idle_timeout_s = idle_timeout_s

    def ready(self) -> tuple[bool, str | None]:
        health = self._engine.health()
        if not health.ready:
            return False, "the engine is not ready"
        if not health.discovery_fresh:
            return False, "runner discovery is stale"
        candidates = self._engine.discovery.candidates(self.app)
        if not candidates:
            return False, f"no runner advertises {self.app} on the approved orchestrators"
        return True, None

    def _request(
        self,
        turns: Sequence[ChatTurn],
        params: ChatParams,
        operation_ref: str,
        *,
        stream: bool,
        tools: Sequence[ToolSpec] = (),
    ) -> JobRequest:
        payload: dict[str, Any] = {
            "messages": [wire_turn(t) for t in turns],
            "max_tokens": params.max_output_tokens,
            "temperature": float(params.temperature),  # the wire format; never money
            "stream": stream,
            "chat_template_kwargs": {"enable_thinking": params.include_reasoning},
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {"name": s.name, "description": s.description, "parameters": s.parameters},
                }
                for s in tools
            ]
            payload["tool_choice"] = "auto"
        if params.include_reasoning and params.thinking_token_budget is not None:
            payload["thinking_token_budget"] = params.thinking_token_budget
        if params.include_reasoning and params.reasoning_effort is not None:
            payload["reasoning_effort"] = params.reasoning_effort
        if params.continue_final_message:
            # vLLM continues the trailing assistant turn instead of starting a new one ("continue generating")
            payload["continue_final_message"] = True
            payload["add_generation_prompt"] = False
        return JobRequest(
            app=self.app,
            path=CHAT_PATH,
            method="POST",
            payload=payload,
            operation_ref=operation_ref,
            max_attempts=self._max_attempts,
            timeout_s=params.timeout_s,
            idle_timeout_s=self._idle_timeout_s if stream else None,
        )

    async def open_reply(
        self,
        user_id: UUID,
        turns: Sequence[ChatTurn],
        params: ChatParams,
        operation_ref: str,
        tools: Sequence[ToolSpec] = (),
    ) -> BufferedReply:
        request = self._request(turns, params, operation_ref, stream=False, tools=tools)
        result = await self._run(user_id, request)
        data = result.data if isinstance(result.data, dict) else {}
        attempt = result.job.attempts[-1] if result.job.attempts else None
        return BufferedReply(
            result.job.id, attempt.orchestrator_url if attempt else None, parse_completion(data)
        )

    async def model_info(self, user_id: UUID) -> ModelInfo:
        request = JobRequest(app=self.app, path=MODELS_PATH, method="GET", max_attempts=2, timeout_s=30)
        result = await self._run(user_id, request)
        data = result.data if isinstance(result.data, dict) else {}
        models_raw = data.get("data")
        models: list[Any] = models_raw if isinstance(models_raw, list) else []
        first: dict[str, Any] = models[0] if models and isinstance(models[0], dict) else {}
        max_len = first.get("max_model_len")
        if not isinstance(max_len, int) or max_len <= 0:
            raise ReplyFailed("the runner's model card has no max_model_len", payment_sent=True)
        return ModelInfo(
            app=self.app,
            model_id=str(first.get("id") or "unknown"),
            max_model_len=max_len,
            observed_at=self._clock.now(),
        )

    async def wholesale(self, user_id: UUID, job_id: UUID) -> WholesaleCost:
        try:
            cost = await self._engine.costs.for_job(actor_for(user_id), job_id)
        except EngineNotFound as exc:
            raise NotFound(f"job {job_id} not found") from exc
        except EngineError as exc:
            raise ChatUnavailable(str(exc)) from exc
        return wholesale_from(cost)

    async def network_totals(self, user_id: UUID, start: datetime, end: datetime) -> NetworkTotals:
        """The engine's cost summary for this user's jobs created in [start, end) (D29)."""
        try:
            summary = await self._engine.costs.summary(actor_for(user_id), start, end)
        except EngineError as exc:
            raise ChatUnavailable(str(exc)) from exc
        return network_totals_from(summary)

    async def report_usage(self, user_id: UUID, job_id: UUID, usage: TokenUsage) -> None:
        quantities = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "reasoning_tokens": usage.reasoning_tokens,
        }
        try:
            await self._engine.jobs.report_usage(actor_for(user_id), job_id, quantities)
        except EngineError as exc:
            raise ChatUnavailable(str(exc)) from exc

    async def _run(self, user_id: UUID, request: JobRequest) -> Any:
        try:
            return await self._engine.jobs.run(actor_for(user_id), request)
        except JobFailed as exc:
            raise failure_from(exc) from exc
        except (NoCapacity, NotProvisioned, ProviderUnavailable) as exc:
            raise ChatUnavailable(str(exc)) from exc
        except (OperationExists, OperationConflict) as exc:
            raise Conflict(str(exc)) from exc
        except EngineError as exc:
            raise ReplyFailed(str(exc), payment_sent=False) from exc


class StreamingReply:
    """The ReplyStream over the engine's ``JobStream``: SSE frames become reply chunks as they arrive."""

    def __init__(self, job_stream: Any, orchestrator_url: str | None) -> None:
        self._stream = job_stream
        self._orchestrator_url = orchestrator_url

    @property
    def job_id(self) -> UUID | None:
        job_id = self._stream.job.id
        return job_id if isinstance(job_id, UUID) else None

    @property
    def orchestrator_url(self) -> str | None:
        return self._orchestrator_url

    def __aiter__(self) -> AsyncIterator[ReplyChunk]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[ReplyChunk]:
        if not str(self._stream.content_type).startswith("text/event-stream"):
            # The runner answered with one body (no stream support, or an error document): parse it whole.
            body = b"".join([chunk async for chunk in self._stream])
            try:
                data = json.loads(body or b"{}")
            except ValueError:
                data = {}
            for chunk in parse_completion(data if isinstance(data, dict) else {}):
                yield chunk
            return
        decoder = SseDecoder()
        calls = ToolCallAssembler()
        finish_reason: str | None = None
        usage: TokenUsage | None = None
        try:
            async for raw in self._stream:
                for event in decoder.feed(raw):
                    for chunk in _delta_chunks(event):
                        yield chunk
                    calls.feed(event)
                    finish_reason = _finish_reason(event) or finish_reason
                    usage = parse_usage(event.get("usage")) or usage
        except JobFailed as exc:
            raise failure_from(exc) from exc
        for event in decoder.flush():
            for chunk in _delta_chunks(event):
                yield chunk
            calls.feed(event)
            finish_reason = _finish_reason(event) or finish_reason
            usage = parse_usage(event.get("usage")) or usage
        for call in calls.result():
            yield ReplyChunk(kind="tool_call", tool_call=call)
        if usage is not None:
            yield ReplyChunk(kind="usage", usage=usage)
        yield ReplyChunk(kind="done", finish_reason=finish_reason)


class StreamingEngineChat(BufferedEngineChat):
    """``jobs.stream`` per reply: the browser sees tokens as the runner produces them (D1, D20)."""

    async def open_reply(  # type: ignore[override]
        self,
        user_id: UUID,
        turns: Sequence[ChatTurn],
        params: ChatParams,
        operation_ref: str,
        tools: Sequence[ToolSpec] = (),
    ) -> StreamingReply:
        request = self._request(turns, params, operation_ref, stream=True, tools=tools)
        try:
            job_stream = await self._engine.jobs.stream(actor_for(user_id), request)
        except JobFailed as exc:
            raise failure_from(exc) from exc
        except (NoCapacity, NotProvisioned, ProviderUnavailable) as exc:
            raise ChatUnavailable(str(exc)) from exc
        except (OperationExists, OperationConflict) as exc:
            raise Conflict(str(exc)) from exc
        except EngineError as exc:
            raise ReplyFailed(str(exc), payment_sent=False) from exc
        attempts = job_stream.job.attempts
        orchestrator = attempts[-1].orchestrator_url if attempts else None
        return StreamingReply(job_stream, orchestrator)


def _delta_chunks(event: dict[str, Any]) -> list[ReplyChunk]:
    chunks: list[ReplyChunk] = []
    choices = event.get("choices")
    for choice in choices if isinstance(choices, list) else []:
        raw_delta = choice.get("delta") if isinstance(choice, dict) else None
        delta: dict[str, Any] = raw_delta if isinstance(raw_delta, dict) else {}
        reasoning = delta.get("reasoning") or delta.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            chunks.append(ReplyChunk(kind="reasoning", text=reasoning))
        content = delta.get("content")
        if isinstance(content, str) and content:
            chunks.append(ReplyChunk(kind="content", text=content))
    return chunks


def _finish_reason(event: dict[str, Any]) -> str | None:
    choices = event.get("choices")
    for choice in choices if isinstance(choices, list) else []:
        if isinstance(choice, dict) and choice.get("finish_reason"):
            return str(choice["finish_reason"])
    return None


def failure_from(exc: JobFailed) -> ChatUnavailable | ReplyFailed:
    failure = exc.job.failure
    job_id = exc.job.id if isinstance(exc.job.id, UUID) else None
    if failure is None:
        return ReplyFailed(str(exc), payment_sent=False, job_id=job_id)
    if failure.kind in _UNAVAILABLE_KINDS:
        return ChatUnavailable(failure.message)
    uncertain = failure.kind in ("timeout", "abandoned") or exc.job.state == "uncertain"
    detail = failure.message if not failure.body else f"{failure.message}: {failure.body[:300]}"
    return ReplyFailed(detail, payment_sent=failure.payment_sent, uncertain=uncertain, job_id=job_id)


def parse_completion(data: dict[str, Any]) -> list[ReplyChunk]:
    """An OpenAI chat completion body → reasoning, content, usage and done chunks."""
    choices_raw = data.get("choices")
    choices: list[Any] = choices_raw if isinstance(choices_raw, list) else []
    first: dict[str, Any] = choices[0] if choices and isinstance(choices[0], dict) else {}
    message_raw = first.get("message")
    message: dict[str, Any] = message_raw if isinstance(message_raw, dict) else {}
    chunks: list[ReplyChunk] = []
    reasoning = message.get("reasoning") or message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        chunks.append(ReplyChunk(kind="reasoning", text=reasoning))
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        chunks.append(ReplyChunk(kind="content", text=content.strip("\n")))
    for call in parse_tool_calls(message.get("tool_calls")):
        chunks.append(ReplyChunk(kind="tool_call", tool_call=call))
    usage = parse_usage(data.get("usage"))
    if usage is not None:
        chunks.append(ReplyChunk(kind="usage", usage=usage))
    finish = first.get("finish_reason")
    chunks.append(ReplyChunk(kind="done", finish_reason=str(finish) if finish is not None else None))
    return chunks


def parse_usage(raw: object) -> TokenUsage | None:
    if not isinstance(raw, dict):
        return None
    prompt, completion = raw.get("prompt_tokens"), raw.get("completion_tokens")
    if not isinstance(prompt, int) or not isinstance(completion, int):
        return None
    details_raw = raw.get("completion_tokens_details")
    details: dict[str, Any] = details_raw if isinstance(details_raw, dict) else {}
    prompt_raw = raw.get("prompt_tokens_details")
    prompt_details: dict[str, Any] = prompt_raw if isinstance(prompt_raw, dict) else {}
    reasoning = details.get("reasoning_tokens")
    cached = prompt_details.get("cached_tokens")
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        reasoning_tokens=reasoning if isinstance(reasoning, int) else 0,
        cached_prompt_tokens=cached if isinstance(cached, int) else 0,
    )


def wholesale_from(cost: JobCost) -> WholesaleCost:
    """The engine's JobCost → the network cost shown for one job (D29).

    ``none`` is the engine's "no attempt was paid": a settled $0 (D29), not "not yet known".
    """
    if cost.status == "none":
        return WholesaleCost(status="none", amount=Money(amount=Decimal(0), currency="USD"))
    if cost.status == "pending":
        return WholesaleCost.pending()
    classes = {attempt.cost_class for attempt in cost.attempts}
    status = (
        "delivered"
        if "delivered" in classes
        else "uncertain"
        if "uncertain" in classes
        else "failed_after_payment"
    )
    amount = None if cost.fees.fee_usd is None else Money(amount=Decimal(cost.fees.fee_usd), currency="USD")
    return WholesaleCost(status=status, amount=amount, updated_at=cost.updated_at)


def network_totals_from(summary: CostSummary) -> NetworkTotals:
    """Delivered spend, failed spend (failed after payment plus uncertain) and jobs still pending."""

    def usd(*classes: str) -> Money:
        total = sum(
            (Decimal(summary.by_class[c].fee_usd or 0) for c in classes if c in summary.by_class), Decimal(0)
        )
        return Money(amount=total, currency="USD")

    return NetworkTotals(
        delivered=usd("delivered"),
        failed=usd("failed_after_payment", "uncertain"),
        pending=summary.jobs_pending,
    )
