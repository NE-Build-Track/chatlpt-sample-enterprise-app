"""In-memory fakes for every port: a clock, the store, a hasher, a price table and a scripted backend."""

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from chatlpt.contracts import (
    ChatParams,
    ChatTurn,
    Conversation,
    Message,
    ModelInfo,
    Money,
    OAuthIdentity,
    OAuthProviderName,
    PriceTable,
    ReplyChunk,
    TokenUsage,
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

    def ready(self) -> tuple[bool, str | None]:
        return self.available

    async def open_reply(
        self, user_id: UUID, turns: Sequence[ChatTurn], params: ChatParams, operation_ref: str
    ) -> ScriptedReply:
        self.calls.append((user_id, list(turns), params, operation_ref))
        if self.fail_with is not None:
            raise self.fail_with
        job_id = UUID(int=len(self.calls))
        self.job_ids.append(job_id)
        return ScriptedReply(job_id, "https://orch.test:8935", self.script)

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


class MemoryStore:
    """The AppStore in dictionaries. Passes the same contract tests as SqlStore (tests/store)."""

    def __init__(self) -> None:
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

    async def delete_conversation(self, conversation_id: UUID) -> None:
        self.conversations.pop(conversation_id, None)
        for message_id in [m.id for m in self.messages.values() if m.conversation_id == conversation_id]:
            del self.messages[message_id]

    async def add_message(self, message: Message) -> None:
        self.messages[message.id] = message

    async def update_message(self, message: Message) -> None:
        self.messages[message.id] = message

    async def get_message(self, message_id: UUID) -> Message | None:
        return self.messages.get(message_id)

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        mine = [m for m in self.messages.values() if m.conversation_id == conversation_id]
        return sorted(mine, key=lambda m: (m.created_at, str(m.id)))

    # ledger
    async def record(self, record: UsageRecord) -> None:
        self.records[record.message_id] = record

    async def update_wholesale(self, message_id: UUID, wholesale: WholesaleCost) -> None:
        record = self.records[message_id]
        self.records[message_id] = record.model_copy(update={"wholesale": wholesale})
        if message_id in self.messages:
            self.messages[message_id] = self.messages[message_id].model_copy(update={"wholesale": wholesale})

    async def pending_wholesale(self, limit: int = 100) -> list[UsageRecord]:
        pending = [x for x in self.records.values() if x.wholesale.status == "pending"]
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
        replies=len(items),
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
    )
