"""In-memory fakes for every port: a clock, the store, a hasher, a price table and a scripted backend."""

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from chatlpt.contracts import (
    ChatParams,
    ChatTurn,
    Conversation,
    GeneratedImage,
    ImagePriceTable,
    Message,
    ModelInfo,
    Money,
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
from chatlpt.errors import AppError, Conflict


class FixedClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 10, 19, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **kwargs: int) -> None:
        self.current += timedelta(**kwargs)


class PlainHasher:
    def hash(self, password: str) -> str:
        return f"plain:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"plain:{password}"


class StaticPrices:
    def __init__(self, table: PriceTable | None = None) -> None:
        self._table = table or PriceTable(
            model="Qwen3.8-27B",
            vendor="test",
            region="test",
            currency="USD",
            input_per_m=Decimal("0.50"),
            output_per_m=Decimal("3.00"),
            cached_input_per_m=Decimal("0.10"),
            thinking_output_per_m=None,
            source_url="https://example.test/prices",
            observed_at=datetime(2026, 10, 19, tzinfo=UTC),
        )

    def table(self) -> PriceTable:
        return self._table


class ScriptedReply:
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


class ScriptedBackend:
    """Replies with scripted chunks; records every call. ``fail_with`` raises instead of replying."""

    def __init__(self, *, app: str = "blueclaw/chat/qwen3.8-27b", max_model_len: int = 32768) -> None:
        self.app = app
        self.max_model_len = max_model_len
        self.script: list[ReplyChunk] = [
            ReplyChunk(kind="content", text="Hello from the network."),
            ReplyChunk(kind="usage", usage=TokenUsage(prompt_tokens=12, completion_tokens=6)),
            ReplyChunk(kind="done", finish_reason="stop"),
        ]
        self.fail_with: AppError | None = None
        self.available: tuple[bool, str | None] = (True, None)
        self.calls: list[tuple[UUID, list[ChatTurn], ChatParams, str]] = []
        self.reported: list[tuple[UUID, TokenUsage]] = []
        self.costs: dict[UUID, WholesaleCost] = {}
        self.job_ids: list[UUID] = []
        self.model_info_calls = 0
        self.tools_offered: list[list[ToolSpec]] = []
        self.scripts: list[list[ReplyChunk]] = []  # per-call scripts, consumed before ``script``

    def ready(self) -> tuple[bool, str | None]:
        return self.available

    async def open_reply(
        self,
        user_id: UUID,
        turns: Sequence[ChatTurn],
        params: ChatParams,
        operation_ref: str,
        tools: Sequence[ToolSpec] = (),
    ) -> ScriptedReply:
        self.calls.append((user_id, list(turns), params, operation_ref))
        self.tools_offered.append(list(tools))
        if self.fail_with is not None:
            raise self.fail_with
        job_id = UUID(int=len(self.calls))
        self.job_ids.append(job_id)
        script = self.scripts.pop(0) if self.scripts else self.script
        return ScriptedReply(job_id, "https://orch.test:8935", script)

    async def model_info(self, user_id: UUID) -> ModelInfo:
        self.model_info_calls += 1
        return ModelInfo(
            app=self.app,
            model_id="Qwen3.8-27B",
            max_model_len=self.max_model_len,
            observed_at=datetime.now(UTC),
        )

    async def wholesale(self, user_id: UUID, job_id: UUID) -> WholesaleCost:
        return self.costs.get(job_id, WholesaleCost.pending())

    async def report_usage(self, user_id: UUID, job_id: UUID, usage: TokenUsage) -> None:
        self.reported.append((job_id, usage))


class StaticImagePrices:
    def __init__(self, table: ImagePriceTable | None = None) -> None:
        self._table = table or ImagePriceTable(
            model="fal-ai/flux/schnell",
            vendor="test",
            region="test",
            currency="USD",
            unit="megapixel",
            price_per_unit=Decimal("0.003"),
            rounding="up to the nearest megapixel",
            source_url="https://example.test/flux",
            observed_at=datetime(2026, 10, 19, tzinfo=UTC),
        )

    def table(self) -> ImagePriceTable:
        return self._table


class ScriptedImageResult:
    def __init__(self, job_id: UUID, *, width: int = 1024, height: int = 768, flagged: bool = False) -> None:
        self.url = f"https://images.test/{job_id}.jpg"
        self.width = width
        self.height = height
        self.seed = 42
        self.content_type = "image/jpeg"
        self.flagged = flagged
        self.job_id = job_id
        self.orchestrator_url = "https://ai1.test:8936"


class ScriptedImageBackend:
    """Generates scripted images; records every call. ``fail_with`` raises instead."""

    def __init__(self, *, app: str = "comfystream/fal-flux-schnell") -> None:
        self.app = app
        self.calls: list[tuple[UUID, str, str, str]] = []
        self.fail_with: AppError | None = None
        self.available: tuple[bool, str | None] = (True, None)
        self.size: tuple[int, int] = (1024, 768)
        self.flagged = False

    def ready(self) -> tuple[bool, str | None]:
        return self.available

    async def generate(
        self, user_id: UUID, prompt: str, image_size: str, operation_ref: str
    ) -> ScriptedImageResult:
        self.calls.append((user_id, prompt, image_size, operation_ref))
        if self.fail_with is not None:
            raise self.fail_with
        job_id = UUID(int=1000 + len(self.calls))
        return ScriptedImageResult(job_id, width=self.size[0], height=self.size[1], flagged=self.flagged)


class MemoryImageFiles:
    """Image bytes in a dictionary; ``fetch`` returns a fixed JPEG-like payload."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.fetched: list[str] = []
        self.fail_fetch: bool = False

    async def fetch(self, url: str) -> bytes:
        self.fetched.append(url)
        if self.fail_fetch:
            raise AppError("fetch failed")
        return b"\xff\xd8\xff" + url.encode()

    def save(self, image_id: UUID, content_type: str, data: bytes) -> str:
        relative = f"{image_id}.jpg"
        self.files[relative] = data
        return relative

    def path(self, relative: str) -> str:
        return f"/memory/{relative}"

    def delete(self, relative: str) -> None:
        self.files.pop(relative, None)


class MemoryStore:
    """The AppStore in dictionaries. Passes the same contract tests as SqlStore (tests/store)."""

    def __init__(self) -> None:
        self.images: dict[UUID, tuple[GeneratedImage, str]] = {}
        self.users: dict[UUID, User] = {}
        self.hashes: dict[UUID, str] = {}
        self.identities: dict[tuple[str, str], UUID] = {}
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: dict[UUID, Message] = {}
        self.records: dict[UUID, UsageRecord] = {}
        self.models: dict[str, ModelInfo] = {}

    async def close(self) -> None:
        return None

    # users
    async def create_user(self, user: User, password_hash: str | None) -> None:
        if any(u.email == user.email for u in self.users.values()):
            raise Conflict("an account with that email already exists")
        self.users[user.id] = user
        if password_hash is not None:
            self.hashes[user.id] = password_hash

    async def user_by_id(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def user_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email.lower()), None)

    async def password_hash(self, user_id: UUID) -> str | None:
        return self.hashes.get(user_id)

    async def set_password_hash(self, user_id: UUID, password_hash: str) -> None:
        self.hashes[user_id] = password_hash

    async def link_identity(self, user_id: UUID, identity: OAuthIdentity) -> None:
        self.identities[(identity.provider, identity.subject)] = user_id

    async def user_by_identity(self, provider: OAuthProviderName, subject: str) -> User | None:
        user_id = self.identities.get((provider, subject))
        return None if user_id is None else self.users.get(user_id)

    async def set_disabled(self, user_id: UUID, disabled: bool) -> None:
        self.users[user_id] = self.users[user_id].model_copy(update={"disabled": disabled})

    async def set_admin(self, user_id: UUID, is_admin: bool) -> None:
        self.users[user_id] = self.users[user_id].model_copy(update={"is_admin": is_admin})

    async def set_email_verified(self, user_id: UUID, verified: bool) -> None:
        self.users[user_id] = self.users[user_id].model_copy(update={"email_verified": verified})

    async def claim_email(
        self, retired_id: UUID, placeholder_email: str, new_user: User, identity: OAuthIdentity
    ) -> None:
        retired = {"disabled": True, "is_admin": False, "email": placeholder_email}
        self.users[retired_id] = self.users[retired_id].model_copy(update=retired)
        self.hashes.pop(retired_id, None)
        await self.create_user(new_user, None)
        await self.link_identity(new_user.id, identity)

    async def list_users(self) -> list[User]:
        return sorted(self.users.values(), key=lambda u: u.created_at)

    # conversations
    async def create_conversation(self, conversation: Conversation) -> None:
        self.conversations[conversation.id] = conversation

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def list_conversations(self, user_id: UUID, limit: int = 100) -> list[Conversation]:
        mine = [c for c in self.conversations.values() if c.user_id == user_id]
        return sorted(mine, key=lambda c: c.updated_at, reverse=True)[:limit]

    async def rename_conversation(self, conversation_id: UUID, title: str, updated_at: datetime) -> None:
        c = self.conversations[conversation_id]
        self.conversations[conversation_id] = c.model_copy(update={"title": title, "updated_at": updated_at})

    async def touch_conversation(self, conversation_id: UUID, updated_at: datetime) -> None:
        c = self.conversations[conversation_id]
        self.conversations[conversation_id] = c.model_copy(update={"updated_at": updated_at})

    async def set_thinking(self, conversation_id: UUID, thinking: ThinkingLevel) -> None:
        c = self.conversations[conversation_id]
        self.conversations[conversation_id] = c.model_copy(update={"thinking": thinking})

    async def delete_conversation(self, conversation_id: UUID) -> None:
        self.conversations.pop(conversation_id, None)
        for message_id in [m.id for m in self.messages.values() if m.conversation_id == conversation_id]:
            del self.messages[message_id]

    async def add_message(self, message: Message) -> None:
        self.messages[message.id] = message

    async def update_message(self, message: Message) -> None:
        self.messages[message.id] = message

    async def get_message(self, message_id: UUID) -> Message | None:
        message = self.messages.get(message_id)
        if message is None:
            return None
        images = await self.images_for_messages([message_id])
        return message.model_copy(update={"images": tuple(images.get(message_id, []))})

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        mine = [m for m in self.messages.values() if m.conversation_id == conversation_id]
        images = await self.images_for_messages([m.id for m in mine])
        return sorted(
            (m.model_copy(update={"images": tuple(images.get(m.id, []))}) for m in mine),
            key=lambda m: (m.created_at, str(m.id)),
        )

    # images
    async def add_image(self, image: GeneratedImage, path: str) -> None:
        self.images[image.id] = (image, path)

    async def get_image(self, image_id: UUID) -> tuple[GeneratedImage, str] | None:
        return self.images.get(image_id)

    async def images_for_messages(self, message_ids: Sequence[UUID]) -> dict[UUID, list[GeneratedImage]]:
        wanted = set(message_ids)
        grouped: dict[UUID, list[GeneratedImage]] = {}
        for image, _ in sorted(self.images.values(), key=lambda x: x[0].created_at):
            if image.message_id in wanted:
                grouped.setdefault(image.message_id, []).append(image)
        return grouped

    async def images_older_than(self, cutoff: datetime) -> list[tuple[GeneratedImage, str]]:
        return [(i, p) for i, p in self.images.values() if i.created_at < cutoff and not i.expired]

    async def mark_image_expired(self, image_id: UUID) -> None:
        image, path = self.images[image_id]
        self.images[image_id] = (image.model_copy(update={"expired": True}), path)

    # ledger
    async def record(self, record: UsageRecord) -> None:
        self.records[record.message_id] = record

    async def update_wholesale(self, message_id: UUID, wholesale: WholesaleCost) -> None:
        record = self.records[message_id]
        self.records[message_id] = record.model_copy(update={"wholesale": wholesale})
        if message_id in self.messages:
            self.messages[message_id] = self.messages[message_id].model_copy(update={"wholesale": wholesale})
        if message_id in self.images:
            image, path = self.images[message_id]
            self.images[message_id] = (image.model_copy(update={"wholesale": wholesale}), path)

    async def pending_wholesale(
        self, limit: int = 100, settling_since: datetime | None = None
    ) -> list[UsageRecord]:
        def unsettled(x: UsageRecord) -> bool:
            if x.wholesale.status in ("pending", "none"):
                return True
            updated = x.wholesale.updated_at
            return settling_since is not None and updated is not None and updated >= settling_since

        pending = [x for x in self.records.values() if unsettled(x) and x.job_id is not None]
        return sorted(pending, key=lambda x: x.created_at)[:limit]

    async def totals(self, user_id: UUID | None, start: datetime, end: datetime) -> UsageTotals:
        items = [
            x
            for x in self.records.values()
            if start <= x.created_at < end and (user_id is None or x.user_id == user_id)
        ]
        return totals_of(user_id, start, end, items)

    async def totals_by_user(self, start: datetime, end: datetime) -> list[UsageTotals]:
        items = [x for x in self.records.values() if start <= x.created_at < end]
        users = sorted({x.user_id for x in items}, key=str)
        return [totals_of(u, start, end, [x for x in items if x.user_id == u]) for u in users]

    async def conversation_totals(self, conversation_id: UUID) -> UsageTotals:
        items = [x for x in self.records.values() if x.conversation_id == conversation_id]
        start = min((x.created_at for x in items), default=datetime.min.replace(tzinfo=UTC))
        end = max((x.created_at for x in items), default=start)
        return totals_of(None, start, end, items)

    # model info
    async def get_model_info(self, app: str) -> ModelInfo | None:
        return self.models.get(app)

    async def put_model_info(self, info: ModelInfo) -> None:
        self.models[info.app] = info


def totals_of(
    user_id: UUID | None, start: datetime, end: datetime, items: Sequence[UsageRecord]
) -> UsageTotals:
    return UsageTotals(
        user_id=user_id,
        start=start,
        end=end,
        replies=sum(1 for x in items if x.kind == "chat"),
        prompt_tokens=sum(x.usage.prompt_tokens for x in items),
        completion_tokens=sum(x.usage.completion_tokens for x in items),
        reasoning_tokens=sum(x.usage.reasoning_tokens for x in items),
        retail=Money(amount=sum((x.retail.amount for x in items), Decimal(0)), currency="USD"),
        wholesale=Money(
            amount=sum(
                (x.wholesale.amount.amount for x in items if x.wholesale.amount is not None), Decimal(0)
            ),
            currency="USD",
        ),
        wholesale_pending=sum(1 for x in items if x.wholesale.status == "pending"),
        images=sum(1 for x in items if x.kind == "image"),
    )
