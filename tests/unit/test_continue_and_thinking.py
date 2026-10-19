"""Continue generating, thinking levels, folded history and dropped-turn counts (D24)."""

from decimal import Decimal
from uuid import uuid4

import pytest

from chatlpt.contracts import ChatTurn, Message, NewMessage, NewUser, ReplyChunk, TokenUsage
from chatlpt.errors import InvalidRequest, NotFound
from chatlpt.runtime import Application
from chatlpt.services.chat import chain_text, turns_from
from chatlpt.testing import MemoryStore, ScriptedBackend
from tests.unit.test_chat import collect

NOW = __import__("datetime").datetime(2026, 10, 19, tzinfo=__import__("datetime").UTC)


def message(role: str, content: str, *, continues=None) -> Message:  # type: ignore[no-untyped-def]
    return Message(
        id=uuid4(),
        conversation_id=uuid4(),
        role=role,
        content=content,
        continues_message_id=continues,
        created_at=NOW,
    )  # type: ignore[arg-type]


def test_turns_fold_continuation_segments_into_one_assistant_turn() -> None:
    first = message("assistant", "Part one")
    second = message("assistant", " part two", continues=first.id)
    history = [message("user", "q"), first, second, message("user", "next")]
    assert turns_from(history) == [
        ChatTurn(role="user", content="q"),
        ChatTurn(role="assistant", content="Part one part two"),
        ChatTurn(role="user", content="next"),
    ]
    assert chain_text(history, first.id) == "Part one part two"


async def test_params_follow_the_conversation_thinking_level(application: Application) -> None:
    chat = application.chat
    off = chat.params_for("off")
    assert (
        off.include_reasoning is False and off.thinking_token_budget is None and off.reasoning_effort is None
    )
    high = chat.params_for("high")
    assert high.include_reasoning and high.reasoning_effort == "high"
    assert high.thinking_token_budget == application.settings.thinking_budget_high
    assert chat.params_for("medium").thinking_token_budget == application.settings.thinking_budget_medium


async def test_thinking_level_reaches_the_backend(application: Application, backend: ScriptedBackend) -> None:
    user = await application.auth.signup(NewUser(email="t@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    assert conversation.thinking == "medium"
    await application.conversations.set_thinking(user, conversation.id, "off")
    await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    params = backend.calls[0][2]
    assert params.include_reasoning is False and params.continue_final_message is False


async def test_continue_sends_the_partial_answer_as_the_final_turn(
    application: Application, store: MemoryStore, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="c@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    backend.script = [
        ReplyChunk(kind="content", text="The first half"),
        ReplyChunk(kind="usage", usage=TokenUsage(prompt_tokens=10, completion_tokens=50)),
        ReplyChunk(kind="done", finish_reason="length"),
    ]
    events = await collect(
        application.chat.start_reply(user, conversation.id, NewMessage(content="Tell me a story"))
    )
    first = events[-1].message
    assert first is not None and first.finish_reason == "length"

    backend.script = [
        ReplyChunk(kind="content", text=" and the second half."),
        ReplyChunk(kind="usage", usage=TokenUsage(prompt_tokens=60, completion_tokens=7)),
        ReplyChunk(kind="done", finish_reason="stop"),
    ]
    events = await collect(application.chat.start_continue(user, conversation.id, first.id))
    assert [e.type for e in events] == ["start", "content", "done"]
    segment = events[-1].message
    assert segment is not None and segment.continues_message_id == first.id
    assert segment.content == " and the second half." and segment.finish_reason == "stop"
    assert segment.retail == application.billing.retail(
        TokenUsage(prompt_tokens=60, completion_tokens=7), thinking=False
    )
    _, turns, params, _ = backend.calls[1]
    assert params.continue_final_message is True and params.include_reasoning is False
    assert turns[-1] == ChatTurn(role="assistant", content="The first half")
    assert turns[-2] == ChatTurn(role="user", content="Tell me a story")
    assert len(store.records) == 2  # each segment is its own paid job in the ledger
    assert (await store.conversation_totals(conversation.id)).completion_tokens == 57

    # a second continuation extends the same chain; the model sees both halves
    backend.script = [
        ReplyChunk(kind="content", text=" The end."),
        ReplyChunk(kind="done", finish_reason="stop"),
    ]
    with pytest.raises(InvalidRequest, match="not cut off"):
        async for _ in application.chat.continue_reply(user, conversation.id, first.id):
            pass


async def test_continue_refuses_the_wrong_targets(application: Application, backend: ScriptedBackend) -> None:
    user = await application.auth.signup(NewUser(email="r@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    with pytest.raises(NotFound):
        async for _ in application.chat.continue_reply(user, conversation.id, uuid4()):
            pass
    backend.script = [ReplyChunk(kind="done", finish_reason="length")]  # cut off with no text at all
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    empty = events[-1].message
    assert empty is not None
    with pytest.raises(InvalidRequest, match="no answer text"):
        async for _ in application.chat.continue_reply(user, conversation.id, empty.id):
            pass
    backend.script = [ReplyChunk(kind="content", text="ok"), ReplyChunk(kind="done", finish_reason="stop")]
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="again")))
    with pytest.raises(InvalidRequest, match="latest reply"):
        async for _ in application.chat.continue_reply(user, conversation.id, empty.id):
            pass


async def test_dropped_turns_are_reported_and_stored(
    application: Application, backend: ScriptedBackend
) -> None:
    user = await application.auth.signup(NewUser(email="d@example.com", password="correct horse"))
    conversation = await application.conversations.create(user)
    backend.max_model_len = 600  # tiny window: only the newest turns fit beside the output reserve
    for i in range(3):
        await collect(
            application.chat.start_reply(user, conversation.id, NewMessage(content=f"message {i} " * 50))
        )
    events = await collect(application.chat.start_reply(user, conversation.id, NewMessage(content="last")))
    start, done = events[0], events[-1]
    assert (
        start.dropped_turns > 0
        and done.message is not None
        and done.message.dropped_turns == start.dropped_turns
    )
    assert Decimal(start.dropped_turns) >= 1
    params = backend.calls[-1][2]
    assert params.max_output_tokens < application.settings.max_output_tokens  # capped by what the prompt left
    assert params.max_output_tokens >= 256
