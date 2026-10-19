"""The ChatBackend over the embedded livepeer-builder engine (docs/references/builder-engine.md).

``BufferedEngineChat`` is the v0.1.0 implementation (D20): one ``jobs.run`` per reply, the whole body
yielded as a few chunks. The streaming implementation replaces this file when the engine's
``jobs.stream`` lands (docs/design-docs/streaming-through-the-engine.md). Nothing else changes.
"""

import logging
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from livepeer_builder import (
    ActorContext,
    BuilderEngine,
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

from chatlpt.contracts import ChatParams, ChatTurn, ModelInfo, Money, ReplyChunk, TokenUsage, WholesaleCost
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
    def __init__(self, engine: BuilderEngine, clock: Clock, *, app: str, max_attempts: int = 3) -> None:
        self._engine = engine
        self._clock = clock
        self.app = app
        self._max_attempts = max_attempts

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

    async def open_reply(
        self, user_id: UUID, turns: Sequence[ChatTurn], params: ChatParams, operation_ref: str
    ) -> BufferedReply:
        payload: dict[str, Any] = {
            "messages": [{"role": t.role, "content": t.content} for t in turns],
            "max_tokens": params.max_output_tokens,
            "temperature": float(params.temperature),  # the wire format; never money
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": params.include_reasoning},
        }
        request = JobRequest(
            app=self.app,
            path=CHAT_PATH,
            method="POST",
            payload=payload,
            operation_ref=operation_ref,
            max_attempts=self._max_attempts,
            timeout_s=params.timeout_s,
        )
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


def failure_from(exc: JobFailed) -> ChatUnavailable | ReplyFailed:
    failure = exc.job.failure
    if failure is None:
        return ReplyFailed(str(exc), payment_sent=False)
    if failure.kind in _UNAVAILABLE_KINDS:
        return ChatUnavailable(failure.message)
    uncertain = failure.kind == "timeout" or exc.job.state == "uncertain"
    detail = failure.message if not failure.body else f"{failure.message}: {failure.body[:300]}"
    return ReplyFailed(detail, payment_sent=failure.payment_sent, uncertain=uncertain)


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
    """The engine's JobCost → the wholesale book entry. ``none`` never means free."""
    if cost.status == "none":
        return WholesaleCost(status="none")
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
