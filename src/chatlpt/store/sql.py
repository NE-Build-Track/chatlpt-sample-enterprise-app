"""``SqlStore``: the AppStore over SQLAlchemy Core. One class, one SQLite file, WAL mode."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, delete, event, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from chatlpt.contracts import (
    Conversation,
    GeneratedImage,
    Message,
    ModelInfo,
    Money,
    OAuthIdentity,
    OAuthProviderName,
    ThinkingLevel,
    UsageRecord,
    UsageTotals,
    User,
    WholesaleCost,
)
from chatlpt.errors import Conflict
from chatlpt.store import rows as r
from chatlpt.store import schema as t
from chatlpt.store.migrate import upgrade


def create_engine(url: str) -> AsyncEngine:
    engine = create_async_engine(url)
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _pragmas(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


class SqlStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @classmethod
    async def connect(cls, url: str, *, migrate: bool = True) -> "SqlStore":
        engine = create_engine(url)
        if migrate:
            await upgrade(engine)
        return cls(engine)

    async def close(self) -> None:
        await self.engine.dispose()

    # -- users --------------------------------------------------------------------------------------

    async def create_user(self, user: User, password_hash: str | None) -> None:
        values = _user_values(user, password_hash)
        try:
            async with self.engine.begin() as conn:
                await conn.execute(insert(t.users).values(values))
        except IntegrityError as exc:
            raise Conflict("an account with that email already exists") from exc

    async def claim_email(
        self, retired_id: UUID, placeholder_email: str, new_user: User, identity: OAuthIdentity
    ) -> None:
        retired = {"disabled": True, "password_hash": None, "is_admin": False, "email": placeholder_email}
        async with self.engine.begin() as conn:
            await conn.execute(update(t.users).where(t.users.c.id == str(retired_id)).values(retired))
            await conn.execute(insert(t.users).values(_user_values(new_user, None)))
            await conn.execute(insert(t.identities).values(_identity_values(new_user.id, identity)))

    async def user_by_id(self, user_id: UUID) -> User | None:
        return await self._one_user(t.users.c.id == str(user_id))

    async def user_by_email(self, email: str) -> User | None:
        return await self._one_user(t.users.c.email == email.lower())

    async def _one_user(self, where: Any) -> User | None:
        async with self.engine.connect() as conn:
            row = (await conn.execute(select(t.users).where(where))).mappings().first()
        return r.user_from(row) if row else None

    async def password_hash(self, user_id: UUID) -> str | None:
        async with self.engine.connect() as conn:
            value = (
                await conn.execute(select(t.users.c.password_hash).where(t.users.c.id == str(user_id)))
            ).scalar_one_or_none()
        return None if value is None else str(value)

    async def set_password_hash(self, user_id: UUID, password_hash: str) -> None:
        await self._set_user(user_id, password_hash=password_hash)

    async def set_disabled(self, user_id: UUID, disabled: bool) -> None:
        await self._set_user(user_id, disabled=disabled)

    async def set_admin(self, user_id: UUID, is_admin: bool) -> None:
        await self._set_user(user_id, is_admin=is_admin)

    async def set_email_verified(self, user_id: UUID, verified: bool) -> None:
        await self._set_user(user_id, email_verified=verified)

    async def _set_user(self, user_id: UUID, **values: Any) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(update(t.users).where(t.users.c.id == str(user_id)).values(values))

    async def link_identity(self, user_id: UUID, identity: OAuthIdentity) -> None:
        key = and_(t.identities.c.provider == identity.provider, t.identities.c.subject == identity.subject)
        async with self.engine.begin() as conn:
            await conn.execute(delete(t.identities).where(key))
            await conn.execute(insert(t.identities).values(_identity_values(user_id, identity)))

    async def user_by_identity(self, provider: OAuthProviderName, subject: str) -> User | None:
        query = (
            select(t.users)
            .join(t.identities, t.identities.c.user_id == t.users.c.id)
            .where(t.identities.c.provider == provider, t.identities.c.subject == subject)
        )
        async with self.engine.connect() as conn:
            row = (await conn.execute(query)).mappings().first()
        return r.user_from(row) if row else None

    async def list_users(self) -> list[User]:
        async with self.engine.connect() as conn:
            result = await conn.execute(select(t.users).order_by(t.users.c.created_at))
            return [r.user_from(row) for row in result.mappings()]

    # -- conversations ------------------------------------------------------------------------------

    async def create_conversation(self, conversation: Conversation) -> None:
        values = conversation.model_dump() | {
            "id": str(conversation.id),
            "user_id": str(conversation.user_id),
        }
        async with self.engine.begin() as conn:
            await conn.execute(insert(t.conversations).values(values))

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        select(t.conversations).where(t.conversations.c.id == str(conversation_id))
                    )
                )
                .mappings()
                .first()
            )
        return r.conversation_from(row) if row else None

    async def list_conversations(self, user_id: UUID, limit: int = 100) -> list[Conversation]:
        query = (
            select(t.conversations)
            .where(t.conversations.c.user_id == str(user_id))
            .order_by(t.conversations.c.updated_at.desc())
            .limit(limit)
        )
        async with self.engine.connect() as conn:
            return [r.conversation_from(row) for row in (await conn.execute(query)).mappings()]

    async def rename_conversation(self, conversation_id: UUID, title: str, updated_at: datetime) -> None:
        await self._set_conversation(conversation_id, title=title, updated_at=updated_at)

    async def touch_conversation(self, conversation_id: UUID, updated_at: datetime) -> None:
        await self._set_conversation(conversation_id, updated_at=updated_at)

    async def set_thinking(self, conversation_id: UUID, thinking: ThinkingLevel) -> None:
        await self._set_conversation(conversation_id, thinking=thinking)

    async def _set_conversation(self, conversation_id: UUID, **values: Any) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                update(t.conversations).where(t.conversations.c.id == str(conversation_id)).values(values)
            )

    async def delete_conversation(self, conversation_id: UUID) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(delete(t.messages).where(t.messages.c.conversation_id == str(conversation_id)))
            await conn.execute(delete(t.conversations).where(t.conversations.c.id == str(conversation_id)))

    async def add_message(self, message: Message) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(insert(t.messages).values(r.message_values(message)))

    async def update_message(self, message: Message) -> None:
        values = r.message_values(message)
        values.pop("id")
        async with self.engine.begin() as conn:
            await conn.execute(update(t.messages).where(t.messages.c.id == str(message.id)).values(values))

    async def get_message(self, message_id: UUID) -> Message | None:
        async with self.engine.connect() as conn:
            row = (
                (await conn.execute(select(t.messages).where(t.messages.c.id == str(message_id))))
                .mappings()
                .first()
            )
        if not row:
            return None
        images = await self.images_for_messages([message_id])
        return r.message_from(row, images.get(message_id, []))

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        query = (
            select(t.messages)
            .where(t.messages.c.conversation_id == str(conversation_id))
            .order_by(t.messages.c.created_at, t.messages.c.id)
        )
        async with self.engine.connect() as conn:
            rows = list((await conn.execute(query)).mappings())
        images = await self.images_for_messages([UUID(row["id"]) for row in rows])
        return [r.message_from(row, images.get(UUID(row["id"]), [])) for row in rows]

    # -- images -------------------------------------------------------------------------------------

    async def add_image(self, image: GeneratedImage, path: str) -> None:
        async with self.engine.connect() as conn:
            owner = (
                await conn.execute(
                    select(t.conversations.c.user_id).where(
                        t.conversations.c.id == str(image.conversation_id)
                    )
                )
            ).scalar_one()
        async with self.engine.begin() as conn:
            await conn.execute(insert(t.images).values(r.image_values(image, path, UUID(str(owner)))))

    async def get_image(self, image_id: UUID) -> tuple[GeneratedImage, str] | None:
        async with self.engine.connect() as conn:
            row = (
                (await conn.execute(select(t.images).where(t.images.c.id == str(image_id))))
                .mappings()
                .first()
            )
        return (r.image_from(row), str(row["path"])) if row else None

    async def images_for_messages(self, message_ids: Sequence[UUID]) -> dict[UUID, list[GeneratedImage]]:
        if not message_ids:
            return {}
        query = (
            select(t.images)
            .where(t.images.c.message_id.in_([str(m) for m in message_ids]))
            .order_by(t.images.c.created_at)
        )
        grouped: dict[UUID, list[GeneratedImage]] = {}
        async with self.engine.connect() as conn:
            for row in (await conn.execute(query)).mappings():
                image = r.image_from(row)
                grouped.setdefault(image.message_id, []).append(image)
        return grouped

    async def images_older_than(self, cutoff: datetime) -> list[tuple[GeneratedImage, str]]:
        query = select(t.images).where(t.images.c.created_at < cutoff, t.images.c.expired_at.is_(None))
        async with self.engine.connect() as conn:
            return [(r.image_from(row), str(row["path"])) for row in (await conn.execute(query)).mappings()]

    async def mark_image_expired(self, image_id: UUID) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                update(t.images).where(t.images.c.id == str(image_id)).values(expired_at=datetime.now(tz=UTC))
            )

    # -- the ledger ---------------------------------------------------------------------------------

    async def record(self, record: UsageRecord) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(insert(t.usage_records).values(r.usage_record_values(record)))

    async def update_wholesale(self, message_id: UUID, wholesale: WholesaleCost) -> None:
        amount = None if wholesale.amount is None else str(wholesale.amount.amount)
        async with self.engine.begin() as conn:
            await conn.execute(
                update(t.usage_records)
                .where(t.usage_records.c.message_id == str(message_id))
                .values(
                    wholesale_status=wholesale.status,
                    wholesale_usd=amount,
                    wholesale_orchestrator_url=wholesale.orchestrator_url,
                    wholesale_updated_at=wholesale.updated_at,
                )
            )
            for table in (t.messages, t.images):
                await conn.execute(
                    update(table)
                    .where(table.c.id == str(message_id))
                    .values(
                        wholesale_status=wholesale.status,
                        wholesale_usd=amount,
                        wholesale_updated_at=wholesale.updated_at,
                    )
                )

    async def pending_wholesale(
        self, limit: int = 100, settling_since: datetime | None = None
    ) -> list[UsageRecord]:
        unsettled: ColumnElement[bool] = t.usage_records.c.wholesale_status.in_(("pending", "none"))
        if settling_since is not None:
            unsettled = or_(unsettled, t.usage_records.c.wholesale_updated_at >= settling_since)
        query = (
            select(t.usage_records)
            .where(unsettled, t.usage_records.c.job_id.is_not(None))
            .order_by(t.usage_records.c.created_at)
            .limit(limit)
        )
        async with self.engine.connect() as conn:
            return [r.usage_record_from(row) for row in (await conn.execute(query)).mappings()]

    async def totals(self, user_id: UUID | None, start: datetime, end: datetime) -> UsageTotals:
        where = [t.usage_records.c.created_at >= start, t.usage_records.c.created_at < end]
        if user_id is not None:
            where.append(t.usage_records.c.user_id == str(user_id))
        async with self.engine.connect() as conn:
            records = [
                r.usage_record_from(row)
                for row in (await conn.execute(select(t.usage_records).where(*where))).mappings()
            ]
        return _totals(user_id, start, end, records)

    async def totals_by_user(self, start: datetime, end: datetime) -> list[UsageTotals]:
        where = [t.usage_records.c.created_at >= start, t.usage_records.c.created_at < end]
        async with self.engine.connect() as conn:
            records = [
                r.usage_record_from(row)
                for row in (await conn.execute(select(t.usage_records).where(*where))).mappings()
            ]
        by_user: dict[UUID, list[UsageRecord]] = {}
        for record in records:
            by_user.setdefault(record.user_id, []).append(record)
        return [_totals(user, start, end, items) for user, items in by_user.items()]

    async def conversation_totals(self, conversation_id: UUID) -> UsageTotals:
        query = select(t.usage_records).where(t.usage_records.c.conversation_id == str(conversation_id))
        async with self.engine.connect() as conn:
            records = [r.usage_record_from(row) for row in (await conn.execute(query)).mappings()]
        start = min((x.created_at for x in records), default=datetime.min.replace(tzinfo=None))
        end = max((x.created_at for x in records), default=start)
        return _totals(None, start, end, records)

    # -- model info ---------------------------------------------------------------------------------

    async def get_model_info(self, app: str) -> ModelInfo | None:
        async with self.engine.connect() as conn:
            row = (
                (await conn.execute(select(t.model_info).where(t.model_info.c.app == app))).mappings().first()
            )
        return r.model_info_from(row) if row else None

    async def put_model_info(self, info: ModelInfo) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(delete(t.model_info).where(t.model_info.c.app == info.app))
            await conn.execute(insert(t.model_info).values(info.model_dump()))


def _totals(
    user_id: UUID | None, start: datetime, end: datetime, records: Sequence[UsageRecord]
) -> UsageTotals:
    retail = sum((x.retail.amount for x in records), Decimal(0))
    wholesale = sum(
        (x.wholesale.amount.amount for x in records if x.wholesale.amount is not None), Decimal(0)
    )
    return UsageTotals(
        user_id=user_id,
        start=start,
        end=end,
        replies=sum(1 for x in records if x.kind == "chat"),
        prompt_tokens=sum(x.usage.prompt_tokens for x in records),
        completion_tokens=sum(x.usage.completion_tokens for x in records),
        reasoning_tokens=sum(x.usage.reasoning_tokens for x in records),
        retail=Money(amount=retail, currency="USD"),
        wholesale=Money(amount=wholesale, currency="USD"),
        wholesale_pending=sum(1 for x in records if x.wholesale.status == "pending"),
        images=sum(1 for x in records if x.kind == "image"),
    )


def _user_values(user: User, password_hash: str | None) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email.lower(),
        "display_name": user.display_name,
        "password_hash": password_hash,
        "is_admin": user.is_admin,
        "disabled": user.disabled,
        "email_verified": user.email_verified,
        "created_at": user.created_at,
    }


def _identity_values(user_id: UUID, identity: OAuthIdentity) -> dict[str, Any]:
    return {
        "provider": identity.provider,
        "subject": identity.subject,
        "user_id": str(user_id),
        "email": identity.email,
        "created_at": datetime.now(tz=None).astimezone(),
    }
