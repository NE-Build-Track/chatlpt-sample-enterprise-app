"""A reply end to end against the scripted backend: events, both books, failures, the detached run."""

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest

from chatlpt.contracts import Money, NewMessage, NewUser, ReplyChunk, ReplyEvent, TokenUsage, WholesaleCost
from chatlpt.errors import ChatUnavailable, ReplyFailed
from chatlpt.runtime import Application
from chatlpt.testing import MemoryStore, ScriptedBackend


async def collect(queue: asyncio.Queue[ReplyEvent | None]) -> list[ReplyEvent]:
    events: list[ReplyEvent] = []
    while (event := await queue.get()) is not None:
        events.append(event)
    return events


async def test_reply_writes_both_books_and_titles_the_conversation(
    application: Application, store: MemoryStore, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="a@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    events = await collect(
        application.chat.start_reply(user, conversation.id, NewMessage(content="Hello there, model"))
    )
    assert [e.type for e in events] == ["start", "content", "done"]
    final = events[-1].message
    assert final is not None and final.content == "Hello from the network." and final.state == "complete"
    assert final.usage == TokenUsage(prompt_tokens=12, completion_tokens=6)
    assert final.retail == Money(
        amount=Decimal(12) * Decimal("0.50") / 10**6 + Decimal(6) * Decimal("3.00") / 10**6
    )
    assert final.wholesale == WholesaleCost(status="pending", orchestrator_url="https://orch.test:8935")
    assert final.job_id == backend.job_ids[0] and final.orchestrator_url == "https://orch.test:8935"
    stored = await store.get_message(final.id)
    assert stored is not None and stored.wholesale is None  # never stored; read from the engine (D29)
    (shown,) = await application.network.with_costs(user.id, [stored])
    assert shown.wholesale == WholesaleCost(status="pending", orchestrator_url="https://orch.test:8935")
    assert (await store.get_conversation(conversation.id)).title == "Hello there, model"  # type: ignore[union-attr]
    assert len(store.records) == 1 and backend.reported == [(final.job_id, final.usage)]
    turns = backend.calls[0][1]
    assert turns[0].role == "system" and turns[-1] == turns[-1].model_copy(
        update={"content": "Hello there, model"}
    )


async def test_network_cost_is_read_from_the_engine_every_time(
    application: Application, store: MemoryStore, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="b@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    job_id = events[-1].message.job_id  # type: ignore[union-attr]
    assert job_id is not None

    async def shown() -> WholesaleCost:
        (message,) = await application.network.with_costs(
            user.id, [m for m in await store.list_messages(conversation.id) if m.role == "assistant"]
        )
        assert message.wholesale is not None
        return message.wholesale

    assert (await shown()).status == "pending"  # the engine has not seen the usage yet
    backend.costs[job_id] = WholesaleCost(status="delivered", amount=Money(amount=Decimal("0.000111")))
    assert (await shown()).amount == Money(amount=Decimal("0.000111"))
    backend.costs[job_id] = WholesaleCost(status="delivered", amount=Money(amount=Decimal("0.000222")))
    assert (await shown()).amount == Money(amount=Decimal("0.000222"))  # a correction shows at once
    month = (application.clock.now().replace(day=1), application.clock.now().replace(day=28))
    totals = await application.network.user_totals(user.id, *month)
    assert totals.wholesale.amount == Decimal("0.000222") and totals.wholesale_pending == 0
    assert totals.retail.amount > 0 and totals.replies == 1  # retail still comes from the ledger
    backend.unknown.add(job_id)  # the engine's database was reset
    assert (await shown()).status == "unknown"  # never shown as $0


async def test_a_failed_paid_reply_keeps_its_job_and_its_network_cost_counts(
    application: Application, store: MemoryStore, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="c@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    job_id = uuid4()
    backend.owners[job_id] = user.id
    backend.fail_with = ReplyFailed("runner 502", payment_sent=True, uncertain=True, job_id=job_id)
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    assert events[-1].type == "error" and "runner 502" in (events[-1].error or "")
    reply = next(m for m in await store.list_messages(conversation.id) if m.role == "assistant")
    assert reply.state == "uncertain" and reply.job_id == job_id and reply.wholesale is None
    assert len(store.records) == 0  # no retail: nothing usable was delivered
    backend.costs[job_id] = WholesaleCost(status="uncertain", amount=Money(amount=Decimal("0.0001")))
    (shown,) = await application.network.with_costs(user.id, [reply])
    assert shown.wholesale is not None and shown.wholesale.status == "uncertain"
    month = (application.clock.now().replace(day=1), application.clock.now().replace(day=28))
    totals = await application.network.user_totals(user.id, *month)
    assert totals.wholesale_failed.amount == Decimal("0.0001") and totals.wholesale.amount == 0


async def test_unavailable_backend_refuses_before_any_message_is_stored(
    application: Application, store: MemoryStore, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="d@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    backend.available = (False, "no runner advertises the app")
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    assert events == [ReplyEvent(type="error", error="no runner advertises the app", retry_after_s=10)]
    assert await store.list_messages(conversation.id) == []


async def test_reasoning_is_streamed_and_stored(application: Application, backend: ScriptedBackend) -> None:
    user = await application.auth.signup(NewUser(email="e@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    backend.script = [
        ReplyChunk(kind="reasoning", text="Let me think."),
        ReplyChunk(kind="content", text="42"),
        ReplyChunk(kind="usage", usage=TokenUsage(prompt_tokens=5, completion_tokens=9, reasoning_tokens=6)),
        ReplyChunk(kind="done"),
    ]
    events = await collect(
        application.chat.start_reply(user, conversation.id, NewMessage(content="meaning?"))
    )
    assert [e.type for e in events] == ["start", "reasoning", "content", "done"]
    final = events[-1].message
    assert final is not None and final.reasoning == "Let me think." and final.usage is not None
    assert final.usage.reasoning_tokens == 6


async def test_other_users_conversations_are_not_found(application: Application) -> None:
    alice = await application.auth.signup(NewUser(email="f@example.com", password="correct horse"))
    bob = await application.auth.signup(NewUser(email="g@example.com", password="correct horse"))
    conversation = await application.conversations.create(alice)
    events = await collect(application.chat.start_reply(bob, conversation.id, NewMessage(content="hi")))
    assert events[0].type == "error" and events[0].error == "conversation not found"


async def test_no_backend_means_chat_unavailable(settings, store, clock) -> None:  # type: ignore[no-untyped-def]
    from chatlpt.testing import PlainHasher, StaticPrices

    app = Application(
        settings,
        store=store,
        backend=None,
        clock=clock,
        hasher=PlainHasher(),
        prices=StaticPrices(),
        oauth={},
    )
    user = await app.auth.signup(NewUser(email="h@example.com", password="correct horse"))
    conversation = await app.conversations.create(user)
    with pytest.raises(ChatUnavailable):
        async for _ in app.chat.reply(user, conversation.id, NewMessage(content="hi")):
            pass
    health = await app.health()
    assert health.ready and not health.chat_available and not health.engine_configured
    assert uuid4() != user.id
