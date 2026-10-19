"""Providers layer: the ports services call. Implementations live in adapters/ and store/.

Imports only ``contracts`` and ``errors``. See ARCHITECTURE.md#layers.
"""

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from chatlpt.contracts import (
    ChatParams,
    ChatTurn,
    Conversation,
    GeneratedImage,
    ImagePriceTable,
    Message,
    ModelInfo,
    OAuthIdentity,
    OAuthProviderName,
    PriceTable,
    ReplyChunk,
    ThinkingLevel,
    TokenUsage,
    ToolSpec,
    UsageRecord,
    UsageTotals,
    User,
    WholesaleCost,
)

# -- time -------------------------------------------------------------------------------------------


class Clock(Protocol):
    def now(self) -> datetime: ...  # timezone-aware UTC


# -- identity ---------------------------------------------------------------------------------------


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, hashed: str) -> bool: ...


class OAuthProvider(Protocol):
    """One configured provider. The HTTP layer owns the redirect; this owns the protocol exchange."""

    name: OAuthProviderName

    def authorization_url(self, redirect_uri: str, state: str, nonce: str) -> str: ...

    async def exchange(self, redirect_uri: str, code: str, nonce: str) -> OAuthIdentity: ...


class UserStore(Protocol):
    async def create_user(self, user: User, password_hash: str | None) -> None: ...  # raises Conflict

    async def user_by_id(self, user_id: UUID) -> User | None: ...

    async def user_by_email(self, email: str) -> User | None: ...

    async def password_hash(self, user_id: UUID) -> str | None: ...

    async def set_password_hash(self, user_id: UUID, password_hash: str) -> None: ...

    async def link_identity(self, user_id: UUID, identity: OAuthIdentity) -> None: ...

    async def user_by_identity(self, provider: OAuthProviderName, subject: str) -> User | None: ...

    async def set_disabled(self, user_id: UUID, disabled: bool) -> None: ...

    async def set_admin(self, user_id: UUID, is_admin: bool) -> None: ...

    async def list_users(self) -> list[User]: ...


# -- conversations ----------------------------------------------------------------------------------


class ConversationStore(Protocol):
    async def create_conversation(self, conversation: Conversation) -> None: ...

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None: ...

    async def list_conversations(self, user_id: UUID, limit: int = 100) -> list[Conversation]: ...

    async def rename_conversation(self, conversation_id: UUID, title: str, updated_at: datetime) -> None: ...

    async def touch_conversation(self, conversation_id: UUID, updated_at: datetime) -> None: ...

    async def set_thinking(self, conversation_id: UUID, thinking: ThinkingLevel) -> None: ...

    async def delete_conversation(self, conversation_id: UUID) -> None: ...  # messages go; usage stays

    async def add_message(self, message: Message) -> None: ...

    async def update_message(self, message: Message) -> None: ...

    async def get_message(self, message_id: UUID) -> Message | None: ...

    async def list_messages(self, conversation_id: UUID) -> list[Message]: ...


# -- the two books ----------------------------------------------------------------------------------


class UsageLedger(Protocol):
    async def record(self, record: UsageRecord) -> None: ...

    async def update_wholesale(self, message_id: UUID, wholesale: WholesaleCost) -> None: ...

    # paid jobs whose wholesale cost is still "pending" or "none" (the engine's "not yet known"), plus
    # those filled since ``settling_since``: the engine corrects a cost as more usage rows arrive
    async def pending_wholesale(
        self, limit: int = 100, settling_since: datetime | None = None
    ) -> list[UsageRecord]: ...

    async def totals(self, user_id: UUID | None, start: datetime, end: datetime) -> UsageTotals: ...

    async def totals_by_user(self, start: datetime, end: datetime) -> list[UsageTotals]: ...

    async def conversation_totals(self, conversation_id: UUID) -> UsageTotals: ...


class PriceSource(Protocol):
    def table(self) -> PriceTable: ...


# -- the model, through the engine -------------------------------------------------------------------


class ReplyStream(Protocol):
    """A reply as it arrives. ``job_id`` is known once the engine accepted the job."""

    @property
    def job_id(self) -> UUID | None: ...

    @property
    def orchestrator_url(self) -> str | None: ...

    def __aiter__(self) -> AsyncIterator[ReplyChunk]: ...


class ChatBackend(Protocol):
    """Everything the app asks of the model. Today buffered (v0.1.0), later streamed (D20)."""

    app: str  # the runner app, for example blueclaw/chat/qwen3.8-27b

    async def open_reply(
        self,
        user_id: UUID,
        turns: Sequence[ChatTurn],
        params: ChatParams,
        operation_ref: str,
        tools: Sequence[ToolSpec] = (),
    ) -> ReplyStream: ...

    async def model_info(self, user_id: UUID) -> ModelInfo: ...  # billed; cache it

    async def wholesale(self, user_id: UUID, job_id: UUID) -> WholesaleCost: ...

    async def report_usage(self, user_id: UUID, job_id: UUID, usage: TokenUsage) -> None: ...

    def ready(self) -> tuple[bool, str | None]: ...  # (chat available, reason when not)


class ImageResult(Protocol):
    """What one image job produced."""

    @property
    def url(self) -> str: ...

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def seed(self) -> int | None: ...

    @property
    def content_type(self) -> str: ...

    @property
    def flagged(self) -> bool: ...  # the safety checker flagged it (the bytes are black)

    @property
    def job_id(self) -> UUID | None: ...

    @property
    def orchestrator_url(self) -> str | None: ...


class ImageBackend(Protocol):
    """The image app, through the engine (D25)."""

    app: str

    async def generate(
        self, user_id: UUID, prompt: str, image_size: str, operation_ref: str
    ) -> ImageResult: ...

    def ready(self) -> tuple[bool, str | None]: ...


class ImageFiles(Protocol):
    """Where generated images live: fetched from the runner's temporary URL, kept on our volume."""

    async def fetch(self, url: str) -> bytes: ...

    def save(self, image_id: UUID, content_type: str, data: bytes) -> str: ...  # returns the relative path

    def path(self, relative: str) -> str: ...  # absolute path for serving

    def delete(self, relative: str) -> None: ...


class ImagePriceSource(Protocol):
    def table(self) -> ImagePriceTable: ...


class ImageRepo(Protocol):
    async def add_image(self, image: GeneratedImage, path: str) -> None: ...

    async def get_image(self, image_id: UUID) -> tuple[GeneratedImage, str] | None: ...  # with its path

    async def images_for_messages(self, message_ids: Sequence[UUID]) -> dict[UUID, list[GeneratedImage]]: ...

    async def images_older_than(self, cutoff: datetime) -> list[tuple[GeneratedImage, str]]: ...

    async def mark_image_expired(self, image_id: UUID) -> None: ...


class ModelMetadataSource(Protocol):
    """What the runner said about the model in its discovery entry, if anything (free; D14)."""

    def model_from_discovery(self, app: str) -> ModelInfo | None: ...


class ModelInfoCache(Protocol):
    async def get_model_info(self, app: str) -> ModelInfo | None: ...

    async def put_model_info(self, info: ModelInfo) -> None: ...


class AppStore(UserStore, ConversationStore, UsageLedger, ModelInfoCache, ImageRepo, Protocol):
    """Every app-owned record, behind one interface. SQL implementation: chatlpt.store."""

    async def close(self) -> None: ...
