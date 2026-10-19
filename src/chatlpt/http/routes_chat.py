"""Conversation and reply routes. A reply is a server-sent event stream.

See ARCHITECTURE.md#a-reply-end-to-end.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from chatlpt.contracts import (
    Conversation,
    Message,
    ModelInfo,
    NewMessage,
    PriceTable,
    ReplyEvent,
    UpdateConversation,
    UsageTotals,
    User,
)
from chatlpt.errors import InvalidRequest
from chatlpt.http.sessions import csrf_guard
from chatlpt.runtime import Application


class ConversationOut(BaseModel):
    conversation: Conversation
    messages: list[Message]
    totals: UsageTotals


class ModelOut(BaseModel):
    app: str
    chat_available: bool
    reason: str | None
    images_available: bool = False
    image_app: str | None = None
    model: ModelInfo | None
    prices: PriceTable


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


def chat_router(app: Application, current_user: Callable[[Request], Awaitable[User]]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["chat"], dependencies=[Depends(csrf_guard)])
    Current = Annotated[User, Depends(current_user)]

    @router.get("/model", response_model=ModelOut)
    async def model(user: Current) -> ModelOut:
        available, reason = (False, "engine not configured") if app.backend is None else app.backend.ready()
        return ModelOut(
            app=app.settings.chat_app,
            chat_available=available,
            reason=reason,
            model=await app.context.model(app.settings.chat_app),
            prices=app.billing_prices(),
            images_available=app.images.available,
            image_app=app.settings.image_app if app.settings.tools_enabled else None,
        )

    @router.get("/conversations", response_model=list[Conversation])
    async def list_conversations(user: Current) -> list[Conversation]:
        return await app.conversations.list_for(user)

    @router.post("/conversations", response_model=Conversation, status_code=201)
    async def create_conversation(user: Current) -> Conversation:
        return await app.conversations.create(user)

    @router.get("/conversations/{conversation_id}", response_model=ConversationOut)
    async def get_conversation(conversation_id: UUID, user: Current) -> ConversationOut:
        conversation = await app.conversations.get(user, conversation_id)
        return ConversationOut(
            conversation=conversation,
            messages=await app.conversations.messages(user, conversation_id),
            totals=await app.store.conversation_totals(conversation_id),
        )

    @router.patch("/conversations/{conversation_id}", response_model=Conversation)
    async def update(conversation_id: UUID, body: UpdateConversation, user: Current) -> Conversation:
        if body.title is None and body.thinking is None:
            raise InvalidRequest("nothing to update")
        conversation = await app.conversations.get(user, conversation_id)
        if body.title is not None:
            conversation = await app.conversations.rename(user, conversation_id, body.title)
        if body.thinking is not None:
            conversation = await app.conversations.set_thinking(user, conversation_id, body.thinking)
        return conversation

    @router.delete("/conversations/{conversation_id}", status_code=204)
    async def delete(conversation_id: UUID, user: Current) -> None:
        await app.conversations.delete(user, conversation_id)

    @router.post("/conversations/{conversation_id}/messages")
    async def send(conversation_id: UUID, body: NewMessage, user: Current) -> StreamingResponse:
        await app.conversations.get(user, conversation_id)  # 404 before the stream starts
        queue = app.chat.start_reply(user, conversation_id, body)

        async def events() -> AsyncIterator[bytes]:
            while (event := await queue.get()) is not None:
                yield sse(event)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/conversations/{conversation_id}/messages/{message_id}/continue")
    async def continue_reply(conversation_id: UUID, message_id: UUID, user: Current) -> StreamingResponse:
        await app.conversations.get(user, conversation_id)  # 404 before the stream starts
        queue = app.chat.start_continue(user, conversation_id, message_id)

        async def events() -> AsyncIterator[bytes]:
            while (event := await queue.get()) is not None:
                yield sse(event)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/images/{image_id}", include_in_schema=False)
    async def image(image_id: UUID, user: Current) -> FileResponse:
        found, path = await app.images.open(user, image_id)
        await app.conversations.get(user, found.conversation_id)  # the owner only; others get 404
        return FileResponse(
            path, media_type=found.content_type, headers={"Cache-Control": "private, max-age=86400"}
        )

    @router.get("/usage/me", response_model=UsageTotals)
    async def my_usage(user: Current) -> UsageTotals:
        start, end = month_bounds(app.clock.now().astimezone(UTC))
        return await app.store.totals(user.id, start, end)

    return router


def sse(event: ReplyEvent) -> bytes:
    data = json.dumps(event.model_dump(mode="json", exclude_none=True))
    return f"event: {event.type}\ndata: {data}\n\n".encode()
