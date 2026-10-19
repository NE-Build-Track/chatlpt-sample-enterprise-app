"""The AppStore contract: users, identities, conversations, messages, the ledger, model info."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from chatlpt.contracts import (
    Conversation,
    Message,
    ModelInfo,
    Money,
    OAuthIdentity,
    TokenUsage,
    UsageRecord,
    User,
    WholesaleCost,
)
from chatlpt.errors import Conflict
from chatlpt.protocols import AppStore

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def user(email: str = "a@example.com") -> User:
    return User(id=uuid4(), email=email, display_name="A", is_admin=False, disabled=False, created_at=NOW)


async def test_users_identities_and_flags(app_store: AppStore) -> None:
    alice = user()
    await app_store.create_user(alice, "hash")
    assert await app_store.user_by_id(alice.id) == alice
    assert await app_store.user_by_email("A@EXAMPLE.COM") == alice
    assert await app_store.password_hash(alice.id) == "hash"
    with pytest.raises(Conflict):
        await app_store.create_user(user(), None)
    await app_store.link_identity(
        alice.id, OAuthIdentity(provider="github", subject="7", email="a@example.com")
    )
    assert await app_store.user_by_identity("github", "7") == alice
    assert await app_store.user_by_identity("google", "7") is None
    await app_store.set_disabled(alice.id, True)
    await app_store.set_admin(alice.id, True)
    loaded = await app_store.user_by_id(alice.id)
    assert loaded is not None and loaded.disabled and loaded.is_admin
    assert [u.id for u in await app_store.list_users()] == [alice.id]


async def test_conversations_and_messages_round_trip(app_store: AppStore) -> None:
    alice = user()
    await app_store.create_user(alice, None)
    conversation = Conversation(
        id=uuid4(), user_id=alice.id, title="New chat", created_at=NOW, updated_at=NOW
    )
    await app_store.create_conversation(conversation)
    usage = TokenUsage(prompt_tokens=10, completion_tokens=3, reasoning_tokens=1, cached_prompt_tokens=2)
    reply = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content="hi",
        reasoning="think",
        state="complete",
        job_id=uuid4(),
        orchestrator_url="https://o",
        usage=usage,
        retail=Money(amount=Decimal("0.0000140")),
        wholesale=WholesaleCost.pending(),
        created_at=NOW + timedelta(seconds=1),
    )
    question = Message(id=uuid4(), conversation_id=conversation.id, role="user", content="q", created_at=NOW)
    await app_store.add_message(question)
    await app_store.add_message(reply)
    assert await app_store.list_messages(conversation.id) == [question, reply]
    await app_store.rename_conversation(conversation.id, "Renamed", NOW + timedelta(minutes=1))
    loaded = await app_store.get_conversation(conversation.id)
    assert (
        loaded is not None and loaded.title == "Renamed" and loaded.updated_at == NOW + timedelta(minutes=1)
    )
    assert [c.id for c in await app_store.list_conversations(alice.id)] == [conversation.id]
    updated = reply.model_copy(update={"content": "hi there"})
    await app_store.update_message(updated)
    assert await app_store.get_message(reply.id) == updated
    await app_store.delete_conversation(conversation.id)
    assert await app_store.get_conversation(conversation.id) is None
    assert await app_store.list_messages(conversation.id) == []


async def test_ledger_totals_keep_pending_out_of_the_sum(app_store: AppStore) -> None:
    alice, bob = user("a@example.com"), user("b@example.com")
    await app_store.create_user(alice, None)
    await app_store.create_user(bob, None)
    conversation_id = uuid4()
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50)

    def record(owner: User, retail: str, wholesale: WholesaleCost, at: datetime) -> UsageRecord:
        return UsageRecord(
            message_id=uuid4(),
            user_id=owner.id,
            conversation_id=conversation_id,
            job_id=uuid4(),
            usage=usage,
            retail=Money(amount=Decimal(retail)),
            wholesale=wholesale,
            created_at=at,
        )

    paid = WholesaleCost(status="delivered", amount=Money(amount=Decimal("0.0001")), updated_at=NOW)
    first = record(alice, "0.0002", WholesaleCost.pending(), NOW)
    await app_store.record(first)
    await app_store.record(record(alice, "0.0003", paid, NOW + timedelta(minutes=1)))
    await app_store.record(record(bob, "0.0005", paid, NOW + timedelta(minutes=2)))
    await app_store.record(record(bob, "0.9", paid, NOW + timedelta(days=40)))  # outside the window
    totals = await app_store.totals(alice.id, NOW - timedelta(days=1), NOW + timedelta(days=1))
    assert totals.replies == 2 and totals.prompt_tokens == 200
    assert totals.retail.amount == Decimal("0.0005") and totals.wholesale.amount == Decimal("0.0001")
    assert totals.wholesale_pending == 1
    everyone = await app_store.totals(None, NOW - timedelta(days=1), NOW + timedelta(days=1))
    assert everyone.replies == 3 and everyone.retail.amount == Decimal("0.0010")
    by_user = {
        t.user_id: t for t in await app_store.totals_by_user(NOW - timedelta(days=1), NOW + timedelta(days=1))
    }
    assert by_user[bob.id].retail.amount == Decimal("0.0005")
    assert [x.message_id for x in await app_store.pending_wholesale()] == [first.message_id]
    await app_store.update_wholesale(first.message_id, paid)
    assert await app_store.pending_wholesale() == []
    settling = await app_store.pending_wholesale(settling_since=NOW - timedelta(minutes=1))
    assert len(settling) == 4  # every row was filled at NOW, so all are still settling
    assert await app_store.pending_wholesale(settling_since=NOW + timedelta(seconds=1)) == []
    per_conversation = await app_store.conversation_totals(conversation_id)
    assert per_conversation.replies == 4 and per_conversation.wholesale.amount == Decimal("0.0004")


async def test_model_info_cache(app_store: AppStore) -> None:
    info = ModelInfo(
        app="blueclaw/chat/qwen3.8-27b", model_id="Qwen3.8-27B", max_model_len=40960, observed_at=NOW
    )
    assert await app_store.get_model_info(info.app) is None
    await app_store.put_model_info(info)
    assert await app_store.get_model_info(info.app) == info
    await app_store.put_model_info(info.model_copy(update={"max_model_len": 8192}))
    loaded = await app_store.get_model_info(info.app)
    assert loaded is not None and loaded.max_model_len == 8192
