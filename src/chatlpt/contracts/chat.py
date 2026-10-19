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


class Conversation(Contract):
    id: UUID
    user_id: UUID
    title: str
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


class RenameConversation(Contract):
    title: str = Field(min_length=1, max_length=200)


ReplyEventType = Literal["start", "reasoning", "content", "usage", "done", "error"]


class ReplyEvent(Contract):
    """What the browser receives over server-sent events while a reply is produced."""

    type: ReplyEventType
    user_message: Message | None = None  # on start
    message: Message | None = None  # on start (the streaming placeholder) and done (final)
    text: str = ""  # on reasoning / content
    error: str | None = None  # on error
    retry_after_s: int | None = None
