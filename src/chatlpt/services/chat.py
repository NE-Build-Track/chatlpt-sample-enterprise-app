"""A reply, end to end (ARCHITECTURE.md#a-reply-end-to-end), "continue generating" (D24) and images (D25).

Builds the turns within the derived context window, opens the backend stream, forwards events to the
caller while accumulating the reply, and on completion writes both books. The consumption runs in
its own task, so a browser that leaves mid-reply does not lose a paid answer. A continuation is a
new assistant message that extends a reply the runner cut off at the output limit: the partial
answer goes back as the final turn and the model continues it. When the model calls the
``generate_image`` tool, the app runs the image, feeds the result back, and the model captions it:
two assistant messages, one of them a ``tool_call`` message carrying the image.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from chatlpt.contracts import (
    ChatParams,
    ChatTurn,
    Conversation,
    GeneratedImage,
    Message,
    NewMessage,
    ReplyEvent,
    ThinkingLevel,
    TokenUsage,
    ToolCall,
    ToolSpec,
    UsageRecord,
    User,
    WholesaleCost,
)
from chatlpt.errors import AppError, ChatUnavailable, InvalidRequest, NotFound, ReplyFailed
from chatlpt.protocols import ChatBackend, Clock, ConversationStore, UsageLedger
from chatlpt.services.billing import BillingService
from chatlpt.services.context import TURN_OVERHEAD_TOKENS, ContextService
from chatlpt.services.conversations import NEW_TITLE, ConversationService, title_from
from chatlpt.services.history import GENERATE_IMAGE, chain_text, turns_from
from chatlpt.services.images import ImageService
from chatlpt.services.wholesale import WholesaleSync
from chatlpt.utils import estimate_tokens, new_id

_LOG = logging.getLogger(__name__)
ReplyQueue = asyncio.Queue[ReplyEvent | None]
MIN_OUTPUT_TOKENS = 256
# reasoning_effort on the wire, probed on all three Qwen hosts on 2026-10-19: "low" and "medium" work
# everywhere, "high" is rejected everywhere, "xhigh" (the parser's default) works on one host only. High
# therefore sends no effort, which every host treats as its default, and relies on the larger budget.
REASONING_EFFORT: dict[ThinkingLevel, Literal["low", "medium"] | None] = {
    "off": None,
    "low": "low",
    "medium": "medium",
    "high": None,
}
ThinkingBudgets = dict[ThinkingLevel, int]


class ChatService:
    def __init__(
        self,
        store: ConversationStore,
        ledger: UsageLedger,
        conversations: ConversationService,
        backend: ChatBackend | None,
        context: ContextService,
        billing: BillingService,
        clock: Clock,
        *,
        images: ImageService,
        params: ChatParams,
        thinking_budgets: ThinkingBudgets,
        history_turn_limit: int,
        wholesale_settle_window: timedelta = timedelta(minutes=10),
    ) -> None:
        self._store = store
        self._ledger = ledger
        self._conversations = conversations
        self._backend = backend
        self._context = context
        self._billing = billing
        self._clock = clock
        self._images = images
        self._params = params
        self._budgets = thinking_budgets
        self._history_limit = history_turn_limit
        self._wholesale = WholesaleSync(ledger, backend, clock, settle_window=wholesale_settle_window)
        self._tasks: set[asyncio.Task[None]] = set()

    # -- entry points -------------------------------------------------------------------------------

    def start_reply(self, user: User, conversation_id: UUID, request: NewMessage) -> ReplyQueue:
        """Start producing a reply; events arrive on the queue, ``None`` last. Work outlives the reader."""
        return self._detach(self.reply(user, conversation_id, request))

    def start_continue(self, user: User, conversation_id: UUID, message_id: UUID) -> ReplyQueue:
        """Continue a reply the runner cut off; same event stream, a new assistant segment."""
        return self._detach(self.continue_reply(user, conversation_id, message_id))

    def params_for(self, thinking: ThinkingLevel) -> ChatParams:
        """The conversation's thinking level applied to the configured defaults (D24)."""
        if thinking == "off":
            return self._params.model_copy(
                update={"include_reasoning": False, "thinking_token_budget": None, "reasoning_effort": None}
            )
        return self._params.model_copy(
            update={
                "include_reasoning": True,
                "thinking_token_budget": self._budgets[thinking],
                "reasoning_effort": REASONING_EFFORT[thinking],
            }
        )

    async def reply(
        self, user: User, conversation_id: UUID, request: NewMessage
    ) -> AsyncIterator[ReplyEvent]:
        backend = self._ready()
        conversation = await self._conversations.get(user, conversation_id)
        history = await self._store.list_messages(conversation.id)
        now = self._clock.now()
        user_message = Message(
            id=new_id(), conversation_id=conversation.id, role="user", content=request.content, created_at=now
        )
        await self._store.add_message(user_message)
        if conversation.title == NEW_TITLE and not any(m.role == "user" for m in history):
            await self._store.rename_conversation(conversation.id, title_from(request.content), now)
        placeholder = self._placeholder(conversation, after=now)
        turns = [*turns_from(history), ChatTurn(role="user", content=request.content)]
        params = self.params_for(conversation.thinking)
        async for event in self._produce(
            user, backend, placeholder, turns, params, user_message=user_message, conversation=conversation
        ):
            yield event

    async def continue_reply(
        self, user: User, conversation_id: UUID, message_id: UUID
    ) -> AsyncIterator[ReplyEvent]:
        backend = self._ready()
        conversation = await self._conversations.get(user, conversation_id)
        history = await self._store.list_messages(conversation.id)
        target = next((m for m in history if m.id == message_id), None)
        if target is None or target.role != "assistant":
            raise NotFound("message not found")
        last = next((m for m in reversed(history) if m.role == "assistant"), None)
        if last is None or (last.id != target.id and last.continues_message_id != target.id):
            raise InvalidRequest("only the latest reply can be continued")
        if last.finish_reason != "length" or last.state != "complete":
            raise InvalidRequest("this reply was not cut off at the output limit")
        partial = chain_text(history, target.id)
        if not partial.strip():
            raise InvalidRequest("there is no answer text to continue; ask again instead")
        placeholder = self._placeholder(conversation, after=self._clock.now(), continues=target.id)
        # history up to the question, then the partial answer as the final turn the model continues
        before = history[: history.index(target)]
        turns = [*turns_from(before), ChatTurn(role="assistant", content=partial)]
        params = self.params_for(conversation.thinking).model_copy(
            update={"continue_final_message": True, "include_reasoning": False, "reasoning_effort": None}
        )
        async for event in self._produce(
            user,
            backend,
            placeholder,
            turns,
            params,
            user_message=None,
            conversation=conversation,
            allow_tools=False,
        ):
            yield event

    # -- the pipeline -------------------------------------------------------------------------------

    def _ready(self) -> ChatBackend:
        if self._backend is None:
            raise ChatUnavailable("chat is not configured: the engine has no signer (LPB_SIGNER_URL)")
        available, reason = self._backend.ready()
        if not available:
            raise ChatUnavailable(reason or "the model is not available right now")
        return self._backend

    def _placeholder(
        self, conversation: Conversation, *, after: datetime, continues: UUID | None = None
    ) -> Message:
        created = max(self._clock.now(), after + timedelta(microseconds=1))  # always after what it answers
        return Message(
            id=new_id(),
            conversation_id=conversation.id,
            role="assistant",
            content="",
            state="streaming",
            continues_message_id=continues,
            created_at=created,
        )

    async def _produce(
        self,
        user: User,
        backend: ChatBackend,
        placeholder: Message,
        turns: list[ChatTurn],
        params: ChatParams,
        *,
        user_message: Message | None,
        conversation: Conversation | None = None,
        allow_tools: bool = True,
    ) -> AsyncIterator[ReplyEvent]:
        window = await self._context.window(user.id, backend.app)
        recent = turns[-self._history_limit :]
        # Reserve room for the answer, but never more than half the window: history matters too.
        reserve = min(params.max_output_tokens, max(MIN_OUTPUT_TOKENS, window // 2))
        fitted, dropped = ContextService.fit(params.system_prompt, recent, window=window, reserve=reserve)
        dropped += max(0, len(turns) - self._history_limit)
        # vLLM rejects prompt + max_tokens above the window, so cap the answer by what the prompt left.
        prompt_estimate = sum(estimate_tokens(t.content) + TURN_OVERHEAD_TOKENS for t in fitted)
        effective_max = max(MIN_OUTPUT_TOKENS, min(params.max_output_tokens, window - prompt_estimate - 64))
        params = params.model_copy(update={"max_output_tokens": effective_max})
        tools: list[ToolSpec] = [GENERATE_IMAGE] if allow_tools and self._images.available else []
        if tools and not params.include_reasoning:
            # the tool decision was unreliable with thinking off (evidence 2026-10-19): think a little
            params = self.params_for("low").model_copy(update={"max_output_tokens": effective_max})
        placeholder = placeholder.model_copy(update={"dropped_turns": dropped or None})
        await self._store.add_message(placeholder)
        yield ReplyEvent(type="start", user_message=user_message, message=placeholder, dropped_turns=dropped)

        content: list[str] = []
        reasoning: list[str] = []
        calls: list[ToolCall] = []
        usage: TokenUsage | None = None
        finish_reason: str | None = None
        try:
            stream = await backend.open_reply(
                user.id, fitted, params, operation_ref=str(placeholder.id), tools=tools
            )
            async for chunk in stream:
                if chunk.kind == "content" and chunk.text:
                    content.append(chunk.text)
                    yield ReplyEvent(type="content", text=chunk.text)
                elif chunk.kind == "reasoning" and chunk.text:
                    reasoning.append(chunk.text)
                    yield ReplyEvent(type="reasoning", text=chunk.text)
                elif chunk.kind == "tool_call" and chunk.tool_call is not None:
                    calls.append(chunk.tool_call)
                elif chunk.kind == "usage" and chunk.usage is not None:
                    usage = chunk.usage
                elif chunk.kind == "done":
                    finish_reason = chunk.finish_reason
        except ReplyFailed as error:
            failed = placeholder.model_copy(
                update={
                    "content": "".join(content),  # whatever arrived before the failure stays visible
                    "reasoning": "".join(reasoning) or None,
                    "state": "uncertain" if error.uncertain else "failed",
                    "error": str(error),
                    "wholesale": WholesaleCost.pending() if error.payment_sent else None,
                }
            )
            await self._store.update_message(failed)
            _LOG.warning(
                "reply failed",
                extra={
                    "event": "chat.reply_failed",
                    "message_id": str(failed.id),
                    "payment_sent": error.payment_sent,
                },
            )
            raise
        except ChatUnavailable:
            await self._store.update_message(
                placeholder.model_copy(update={"state": "failed", "error": "unavailable"})
            )
            raise

        image_calls = [c for c in calls if c.name == GENERATE_IMAGE.name and c.arguments.get("prompt")]
        if image_calls and conversation is not None:
            placeholder = placeholder.model_copy(
                update={"kind": "tool_call", "tool_calls": tuple(image_calls)}
            )
            await self._store.update_message(placeholder)
            yield ReplyEvent(type="tool_call", message=placeholder)
            images: list[GeneratedImage] = []
            try:
                for call in image_calls[:2]:  # at most two pictures per turn
                    image = await self._images.generate(
                        user,
                        conversation,
                        placeholder.id,
                        str(call.arguments["prompt"]),
                        str(call.arguments.get("image_size") or "") or None,
                    )
                    images.append(image)
                    yield ReplyEvent(type="image", image=image)
            except AppError as error:
                failed = placeholder.model_copy(
                    update={"state": "failed", "error": str(error), "images": tuple(images)}
                )
                await self._store.update_message(failed)
                raise
            placeholder = placeholder.model_copy(update={"images": tuple(images)})
        final = await self._finish(
            user,
            backend,
            placeholder,
            "".join(content),
            "".join(reasoning),
            usage,
            stream.job_id,
            stream.orchestrator_url,
            finish_reason,
        )
        yield ReplyEvent(type="done", message=final)
        if image_calls and conversation is not None:
            # the model captions what it drew: tool results back, no tools this time
            results = [
                ChatTurn(
                    role="tool",
                    tool_call_id=call.id,
                    content=json.dumps(
                        {
                            "status": "done",
                            "width": image.width,
                            "height": image.height,
                            "seed": image.seed,
                            "note": "The image is already displayed to the user above your reply. Do not add "
                            "image links or Markdown images; describe what you drew in a sentence or two.",
                        }
                    ),
                )
                for call, image in zip(image_calls, final.images, strict=False)
            ]
            follow_up = [
                *turns,
                ChatTurn(role="assistant", content="", tool_calls=tuple(image_calls)),
                *results,
            ]
            caption = self._placeholder(conversation, after=final.created_at)
            async for event in self._produce(
                user,
                backend,
                caption,
                follow_up,
                params,
                user_message=None,
                conversation=conversation,
                allow_tools=False,
            ):
                yield event

    def _detach(self, events: AsyncIterator[ReplyEvent]) -> ReplyQueue:
        queue: ReplyQueue = asyncio.Queue()
        task = asyncio.create_task(self._drive(events, queue))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return queue

    async def _drive(self, events: AsyncIterator[ReplyEvent], queue: ReplyQueue) -> None:
        try:
            async for event in events:
                queue.put_nowait(event)
        except AppError as error:
            retry = getattr(error, "retry_after_s", None)
            queue.put_nowait(ReplyEvent(type="error", error=str(error), retry_after_s=retry))
        except Exception:
            _LOG.exception("reply crashed", extra={"event": "chat.reply_crashed"})
            queue.put_nowait(ReplyEvent(type="error", error="the reply failed unexpectedly"))
        finally:
            queue.put_nowait(None)

    async def _finish(
        self,
        user: User,
        backend: ChatBackend,
        placeholder: Message,
        content: str,
        reasoning: str,
        usage: TokenUsage | None,
        job_id: UUID | None,
        orchestrator_url: str | None,
        finish_reason: str | None = None,
    ) -> Message:
        now = self._clock.now()
        thinking = bool(reasoning) or (usage is not None and usage.reasoning_tokens > 0)
        retail = None if usage is None else self._billing.retail(usage, thinking=thinking)
        wholesale = WholesaleCost.pending() if job_id is not None else WholesaleCost(status="none")
        final = placeholder.model_copy(
            update={
                "content": content,
                "reasoning": reasoning or None,
                "state": "complete",
                "job_id": job_id,
                "orchestrator_url": orchestrator_url,
                "usage": usage,
                "retail": retail,
                "finish_reason": finish_reason,
                "wholesale": wholesale.model_copy(update={"orchestrator_url": orchestrator_url}),
            }
        )
        await self._store.update_message(final)
        await self._store.touch_conversation(final.conversation_id, now)
        if usage is not None and retail is not None:
            await self._ledger.record(
                UsageRecord(
                    message_id=final.id,
                    user_id=user.id,
                    conversation_id=final.conversation_id,
                    job_id=job_id,
                    usage=usage,
                    retail=retail,
                    wholesale=final.wholesale or wholesale,
                    created_at=now,
                )
            )
            if job_id is not None:
                try:
                    await backend.report_usage(user.id, job_id, usage)
                except AppError as error:  # the engine's record is a courtesy copy; ours is authoritative
                    _LOG.warning(
                        "usage not reported", extra={"event": "chat.report_usage_failed", "error": str(error)}
                    )
        _LOG.info(
            "reply complete",
            extra={
                "event": "chat.reply_complete",
                "message_id": str(final.id),
                "job_id": None if job_id is None else str(job_id),
                "prompt_tokens": None if usage is None else usage.prompt_tokens,
                "completion_tokens": None if usage is None else usage.completion_tokens,
                "finish_reason": finish_reason,
                "continues": None if final.continues_message_id is None else str(final.continues_message_id),
            },
        )
        return final

    async def sync_wholesale(self) -> int:
        """Fill wholesale costs that arrived (docs: services/wholesale.py). Returns the number filled."""
        return await self._wholesale.sync_once()

    async def drain(self) -> None:
        """Wait for in-flight replies (shutdown)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
