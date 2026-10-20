"""Service edge cases: the detached reply crashing, mid-stream unavailability, usage reporting failures, admin."""

from uuid import uuid4

import pytest

from chatlpt.contracts import NewMessage, NewUser, ReplyChunk, TokenUsage, UsageRecord, WholesaleCost
from chatlpt.errors import AccessDenied, ChatUnavailable, NotFound, ReplyFailed
from chatlpt.runtime import Application
from chatlpt.testing import MemoryStore, ScriptedBackend
from tests.unit.test_chat import collect


async def test_unexpected_exception_still_closes_the_queue(
    application: Application, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="a@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)

    async def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("kaboom")

    backend.open_reply = explode  # type: ignore[method-assign]
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    assert events[-1].type == "error" and events[-1].error == "the reply failed unexpectedly"


async def test_unavailable_raised_by_the_backend_marks_the_placeholder_failed(
    application: Application, store: MemoryStore, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="b@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    backend.fail_with = ChatUnavailable("payment refused everywhere")
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    assert events[-1].type == "error" and events[-1].retry_after_s == 10
    reply = next(m for m in await store.list_messages(conversation.id) if m.role == "assistant")
    assert reply.state == "failed" and reply.error == "unavailable"


async def test_report_usage_failure_does_not_lose_the_reply(
    application: Application, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="c@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)

    async def refuse(*args: object, **kwargs: object) -> None:
        raise ChatUnavailable("engine busy")

    backend.report_usage = refuse  # type: ignore[method-assign]
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    assert (
        events[-1].type == "done"
        and events[-1].message is not None
        and events[-1].message.state == "complete"
    )


async def test_reply_without_usage_records_no_retail(
    application: Application, store: MemoryStore, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="d@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    backend.script = [ReplyChunk(kind="content", text="no usage here"), ReplyChunk(kind="done")]
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    final = events[-1].message
    assert final is not None and final.retail is None and final.usage is None and store.records == {}


async def test_sync_wholesale_skips_records_without_jobs_and_tolerates_lookup_errors(
    application: Application, store: MemoryStore, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="e@example.com", password="correct horse"))
    usage = TokenUsage(prompt_tokens=1, completion_tokens=1)
    from decimal import Decimal

    from chatlpt.contracts import Money

    await store.record(
        UsageRecord(
            message_id=uuid4(),
            user_id=user.id,
            conversation_id=uuid4(),
            job_id=None,
            usage=usage,
            retail=Money(amount=Decimal(0)),
            wholesale=WholesaleCost.pending(),
            created_at=application.clock.now(),
        )
    )
    job_id = uuid4()
    await store.record(
        UsageRecord(
            message_id=uuid4(),
            user_id=user.id,
            conversation_id=uuid4(),
            job_id=job_id,
            usage=usage,
            retail=Money(amount=Decimal(0)),
            wholesale=WholesaleCost.pending(),
            created_at=application.clock.now(),
        )
    )

    async def fail(*args: object) -> WholesaleCost:
        raise ChatUnavailable("engine down")

    backend.wholesale = fail  # type: ignore[method-assign]
    assert await application.chat.sync_wholesale() == 0
    assert [x.job_id for x in await store.pending_wholesale()] == [job_id]  # the job-less row is never polled


async def test_admin_edges(application: Application) -> None:
    admin = await application.auth.signup(NewUser(email="admin@example.com", password="correct horse"))
    admin = await application.auth.set_admin(admin.email, True, allow_unverified=True)
    with pytest.raises(NotFound):
        await application.admin.set_disabled(admin, uuid4(), True)
    with pytest.raises(AccessDenied):
        await application.admin.set_disabled(admin, admin.id, True)
    plain = await application.auth.signup(NewUser(email="p@example.com", password="correct horse"))
    with pytest.raises(AccessDenied):
        await application.admin.users(plain)


async def test_context_falls_back_to_a_stale_cache_when_the_model_cannot_be_asked(
    application: Application, backend: ScriptedBackend
) -> None:
    user_id = uuid4()
    assert await application.context.window(user_id, backend.app) == 32768

    async def fail(user_id: object) -> None:
        raise ChatUnavailable("engine down")

    backend.model_info = fail  # type: ignore[method-assign]
    application.clock.advance(hours=48)  # type: ignore[attr-defined]
    assert (
        await application.context.window(user_id, backend.app) == 32768
    )  # stale, but the model's own figure


async def test_disabled_user_cannot_sign_in_with_a_provider(
    application: Application, store: MemoryStore
) -> None:
    from chatlpt.contracts import ClaimNeeded, OAuthIdentity
    from chatlpt.errors import NotAuthenticated

    identity = OAuthIdentity(provider="github", subject="1", email="z@example.com")
    user = await application.auth.sign_in_with(identity)  # a verified account
    assert not isinstance(user, ClaimNeeded)
    await store.set_disabled(user.id, True)
    with pytest.raises(NotAuthenticated):
        await application.auth.sign_in_with(identity)
    other = identity.model_copy(update={"provider": "google", "subject": "g"})
    with pytest.raises(NotAuthenticated):  # a verified, disabled account is never claimed
        await application.auth.sign_in_with(other)


async def test_partial_text_survives_a_failure_mid_stream(
    application: Application, store: MemoryStore, backend: ScriptedBackend
) -> None:
    from chatlpt.testing.fakes import ScriptedReply

    user = await application.auth.signup(NewUser(email="partial@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)

    class Breaking(ScriptedReply):
        async def _iterate(self):  # type: ignore[no-untyped-def]
            yield ReplyChunk(kind="content", text="half an ")
            raise ReplyFailed("stream cut", payment_sent=True, uncertain=True)

    async def open_reply(*args: object, **kwargs: object) -> Breaking:
        return Breaking(uuid4(), "https://orch.test", [])

    backend.open_reply = open_reply  # type: ignore[method-assign]
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="go")))
    assert [e.type for e in events] == ["start", "content", "error"]
    reply = next(m for m in await store.list_messages(conversation.id) if m.role == "assistant")
    assert (
        reply.state == "uncertain"
        and reply.content == "half an "
        and reply.wholesale == WholesaleCost.pending()
    )
