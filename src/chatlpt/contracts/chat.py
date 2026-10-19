"""Chat contracts: conversations, messages and the reply stream (docs/product-specs/chatlpt.md#chat)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from chatlpt.contracts.billing import TokenUsage, WholesaleCost
from chatlpt.contracts.common import Contract, Money

Role = Literal["system", "user", "assistant"]
ReplyState = Literal["streaming", "complete", "failed", "uncertain"]
ThinkingLevel = Literal["off", "low", "medium", "high"]  # per conversation (D24)


class Conversation(Contract):
    id: UUID
    user_id: UUID
    title: str
    thinking: ThinkingLevel = "medium"
    created_at: datetime
    updated_at: datetime


class Message(Contract):
    id: UUID
    conversation_id: UUID
    role: Role
    content: str
    reasoning: str | None = None
    state: ReplyState = "complete"
    job_id: UUID | None = None
    orchestrator_url: str | None = None
    usage: TokenUsage | None = None
    retail: Money | None = None
    wholesale: WholesaleCost | None = None
    finish_reason: str | None = None  # the runner's own: "stop", "length" (cut off at the output limit), ...
    continues_message_id: UUID | None = None  # a "continue generating" segment of that assistant message
    dropped_turns: int | None = None  # earlier turns left out to fit the model's context window
    error: str | None = None
    created_at: datetime


class ChatTurn(Contract):
    """One message as the model sees it."""

    role: Role
    content: str


class ChatParams(Contract):
    """Model parameters for one reply. Defaults come from settings; the context window is derived (D14)."""

    system_prompt: str
    temperature: Decimal = Field(ge=0, le=2)
    max_output_tokens: int = Field(ge=1)
    include_reasoning: bool = True
    thinking_token_budget: int | None = Field(default=None, ge=1)
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    continue_final_message: bool = False  # the last turn is a partial assistant answer to continue (D24)
    timeout_s: float = Field(default=300.0, gt=0, le=3600)


class ModelInfo(Contract):
    """What the runner says about itself (``GET /v1/models``)."""

    app: str
    model_id: str
    max_model_len: int = Field(ge=1)
    observed_at: datetime


ChunkKind = Literal["content", "reasoning", "usage", "done"]


class ReplyChunk(Contract):
    """One unit of a reply as it arrives. The buffered adapter emits one of each kind at the end."""

    kind: ChunkKind
    text: str = ""
    usage: TokenUsage | None = None
    finish_reason: str | None = None


class NewMessage(Contract):
    content: str = Field(min_length=1, max_length=32_000)


class UpdateConversation(Contract):
    """PATCH body: either field may be omitted."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    thinking: ThinkingLevel | None = None


ReplyEventType = Literal["start", "reasoning", "content", "usage", "done", "error"]


class ReplyEvent(Contract):
    """What the browser receives over server-sent events while a reply is produced."""

    type: ReplyEventType
    user_message: Message | None = None  # on start
    dropped_turns: int = 0  # on start: earlier turns left out to fit the context window
    message: Message | None = None  # on start (the streaming placeholder) and done (final)
    text: str = ""  # on reasoning / content
    error: str | None = None  # on error
    retry_after_s: int | None = None
