"""A reply, end to end (ARCHITECTURE.md#a-reply-end-to-end).

Builds the turns within the derived context window, opens the backend stream, forwards events to the
caller while accumulating the reply, and on completion writes both books. The consumption runs in
its own task, so a browser that leaves mid-reply does not lose a paid answer.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID

from chatlpt.contracts import (
    ChatParams,
    ChatTurn,
    Message,
    NewMessage,
    ReplyEvent,
    TokenUsage,
    UsageRecord,
    User,
    WholesaleCost,
)
from chatlpt.errors import AppError, ChatUnavailable, ReplyFailed
from chatlpt.protocols import ChatBackend, Clock, ConversationStore, UsageLedger
from chatlpt.services.billing import BillingService
from chatlpt.services.context import ContextService
from chatlpt.services.conversations import NEW_TITLE, ConversationService, title_from
from chatlpt.utils import new_id

_LOG = logging.getLogger(__name__)
ReplyQueue = asyncio.Queue[ReplyEvent | None]


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
        params: ChatParams,
        history_turn_limit: int,
        wholesale_settle_window: timedelta = timedelta(minutes=10),
    ) -> None:
        self._settle_window = wholesale_settle_window
        self._store = store
        self._ledger = ledger
        self._conversations = conversations
        self._backend = backend
        self._context = context
        self._billing = billing
        self._clock = clock
        self._params = params
        self._history_limit = history_turn_limit
        self._tasks: set[asyncio.Task[None]] = set()

    def start_reply(self, user: User, conversation_id: UUID, request: NewMessage) -> ReplyQueue:
        """Start producing a reply; events arrive on the queue, ``None`` last. Work outlives the reader."""
        queue: ReplyQueue = asyncio.Queue()
        task = asyncio.create_task(self._drive(user, conversation_id, request, queue))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return queue

    async def _drive(self, user: User, conversation_id: UUID, request: NewMessage, queue: ReplyQueue) -> None:
        try:
            async for event in self.reply(user, conversation_id, request):
                queue.put_nowait(event)
        except AppError as error:
            retry = getattr(error, "retry_after_s", None)
            queue.put_nowait(ReplyEvent(type="error", error=str(error), retry_after_s=retry))
        except Exception:
            _LOG.exception("reply crashed", extra={"event": "chat.reply_crashed"})
            queue.put_nowait(ReplyEvent(type="error", error="the reply failed unexpectedly"))
        finally:
            queue.put_nowait(None)

    async def reply(
        self, user: User, conversation_id: UUID, request: NewMessage
    ) -> AsyncIterator[ReplyEvent]:
        if self._backend is None:
            raise ChatUnavailable("chat is not configured: the engine has no signer (LPB_SIGNER_URL)")
        available, reason = self._backend.ready()
        if not available:
            raise ChatUnavailable(reason or "the model is not available right now")
        conversation = await self._conversations.get(user, conversation_id)
        history = await self._store.list_messages(conversation.id)
        now = self._clock.now()
        user_message = Message(
            id=new_id(), conversation_id=conversation.id, role="user", content=request.content, created_at=now
        )
        await self._store.add_message(user_message)
        if conversation.title == NEW_TITLE and not any(m.role == "user" for m in history):
            await self._store.rename_conversation(conversation.id, title_from(request.content), now)
        placeholder = Message(
            id=new_id(),
            conversation_id=conversation.id,
            role="assistant",
            content="",
            state="streaming",
            created_at=max(self._clock.now(), now + timedelta(microseconds=1)),  # always after the question
        )
        await self._store.add_message(placeholder)
        yield ReplyEvent(type="start", user_message=user_message, message=placeholder)

        turns = [
            ChatTurn(role=m.role, content=m.content) for m in history if m.role != "system" and m.content
        ]
        turns.append(ChatTurn(role="user", content=request.content))
        window = await self._context.window(user.id, self._backend.app)
        fitted = ContextService.fit(
            self._params.system_prompt,
            turns[-self._history_limit :],
            window=window,
            reserve=self._params.max_output_tokens,
        )

        content: list[str] = []
        reasoning: list[str] = []
        usage: TokenUsage | None = None
        finish_reason: str | None = None
        try:
            stream = await self._backend.open_reply(
                user.id, fitted, self._params, operation_ref=str(placeholder.id)
            )
            async for chunk in stream:
                if chunk.kind == "content" and chunk.text:
                    content.append(chunk.text)
                    yield ReplyEvent(type="content", text=chunk.text)
                elif chunk.kind == "reasoning" and chunk.text:
                    reasoning.append(chunk.text)
                    yield ReplyEvent(type="reasoning", text=chunk.text)
                elif chunk.kind == "usage" and chunk.usage is not None:
                    usage = chunk.usage
                elif chunk.kind == "done":
                    finish_reason = chunk.finish_reason
        except ReplyFailed as error:
            failed = placeholder.model_copy(
                update={
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

        final = await self._finish(
            user,
            placeholder,
            "".join(content),
            "".join(reasoning),
            usage,
            stream.job_id,
            stream.orchestrator_url,
            finish_reason,
        )
        yield ReplyEvent(type="done", message=final)

    async def _finish(
        self,
        user: User,
        placeholder: Message,
        content: str,
        reasoning: str,
        usage: TokenUsage | None,
        job_id: UUID | None,
        orchestrator_url: str | None,
        finish_reason: str | None = None,
    ) -> Message:
        now = self._clock.now()
        retail = (
            None
            if usage is None
            else self._billing.retail(usage, thinking=bool(reasoning) or usage.reasoning_tokens > 0)
        )
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
            if job_id is not None and self._backend is not None:
                try:
                    await self._backend.report_usage(user.id, job_id, usage)
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
            },
        )
        return final

    async def sync_wholesale(self) -> int:
        """Ask the engine for every pending wholesale cost and fill the ones that arrived.

        Returns the number filled.
        """
        if self._backend is None:
            return 0
        filled = 0
        since = self._clock.now() - self._settle_window
        for record in await self._ledger.pending_wholesale(settling_since=since):
            if record.job_id is None:
                continue
            try:
                cost = await self._backend.wholesale(record.user_id, record.job_id)
            except AppError as error:
                _LOG.warning(
                    "wholesale lookup failed",
                    extra={"event": "billing.wholesale_failed", "error": str(error)},
                )
                continue
            if cost.status in ("pending", "none"):
                continue  # "none" is the engine's "not yet known" for a paid job; never a zero
            if cost.status == record.wholesale.status and cost.amount == record.wholesale.amount:
                continue  # settled and unchanged
            filled_cost = cost.model_copy(
                update={
                    "updated_at": self._clock.now(),
                    "orchestrator_url": record.wholesale.orchestrator_url,
                }
            )
            await self._ledger.update_wholesale(record.message_id, filled_cost)
            filled += 1
        return filled

    async def drain(self) -> None:
        """Wait for in-flight replies (shutdown)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
