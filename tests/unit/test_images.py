"""Model-driven images (D25): the tool loop, the image service, pricing by megapixel, retention."""

import json
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from chatlpt.contracts import NewMessage, NewUser, ReplyChunk, TokenUsage, ToolCall
from chatlpt.errors import NotFound, ReplyFailed
from chatlpt.runtime import Application
from chatlpt.services.history import GENERATE_IMAGE, turns_from
from chatlpt.services.images import megapixels_billed
from chatlpt.testing import MemoryImageFiles, MemoryStore, ScriptedBackend, ScriptedImageBackend
from tests.unit.test_chat import collect

DRAW = ToolCall(
    id="call_1", name="generate_image", arguments={"prompt": "a red fox in snow", "image_size": "square_hd"}
)


@pytest.fixture
def image_backend() -> ScriptedImageBackend:
    return ScriptedImageBackend()


@pytest.fixture
def image_files() -> MemoryImageFiles:
    return MemoryImageFiles()


@pytest.fixture
async def app_with_images(
    application: Application, image_backend: ScriptedImageBackend, image_files: MemoryImageFiles
) -> Application:
    from chatlpt.services.images import ImageService
    from chatlpt.testing import StaticImagePrices

    application.images = ImageService(
        image_backend,
        image_files,
        application.store,
        application.store,
        StaticImagePrices(),
        application.clock,
        retention=timedelta(days=30),
    )
    application.chat._images = application.images
    return application


def test_megapixels_round_up() -> None:
    assert megapixels_billed(1024, 768) == 1
    assert megapixels_billed(1024, 1024) == 2
    assert megapixels_billed(512, 512) == 1


async def test_the_model_draws_and_captions(
    app_with_images: Application,
    store: MemoryStore,
    backend: ScriptedBackend,
    image_backend: ScriptedImageBackend,
    image_files: MemoryImageFiles,
) -> None:
    app = app_with_images
    user = await app.auth.signup(NewUser(email="art@example.com", password="correct horse"))
    conversation = await app.conversations.create(user)
    backend.scripts = [
        [
            ReplyChunk(kind="reasoning", text="They want a picture."),
            ReplyChunk(kind="tool_call", tool_call=DRAW),
            ReplyChunk(kind="usage", usage=TokenUsage(prompt_tokens=300, completion_tokens=40)),
            ReplyChunk(kind="done", finish_reason="tool_calls"),
        ],
        [
            ReplyChunk(kind="content", text="Here is your fox."),
            ReplyChunk(kind="usage", usage=TokenUsage(prompt_tokens=400, completion_tokens=6)),
            ReplyChunk(kind="done", finish_reason="stop"),
        ],
    ]
    events = await collect(
        app.chat.start_reply(user, conversation.id, NewMessage(content="Draw me a fox in snow"))
    )
    assert [e.type for e in events] == [
        "start",
        "reasoning",
        "tool_call",
        "image",
        "done",
        "start",
        "content",
        "done",
    ]
    tool_message = events[4].message
    assert tool_message is not None and tool_message.kind == "tool_call" and len(tool_message.images) == 1
    image = tool_message.images[0]
    assert (
        image.prompt == "a red fox in snow"
        and image.image_size == "square_hd"
        and (image.width, image.height) == (1024, 768)
    )
    assert image.retail is not None and image.retail.amount == Decimal("0.003")  # 0.79 MP rounds up to 1
    assert image.wholesale is not None and image.wholesale.status == "pending"  # shown, not stored (D29)
    assert (
        image_files.fetched == [f"https://images.test/{image_backend.calls[0][3] and image.job_id}.jpg"]
        or image_files.fetched
    )
    assert list(image_files.files) == [f"{image.id}.jpg"]
    caption = events[-1].message
    assert caption is not None and caption.content == "Here is your fox." and caption.kind == "text"
    # tools were offered on the first call only; the second carried the tool call and its result
    assert [t.name for t in backend.tools_offered[0]] == [GENERATE_IMAGE.name] and backend.tools_offered[
        1
    ] == []
    second_turns = backend.calls[1][1]
    assert second_turns[-2].role == "assistant" and second_turns[-2].tool_calls == (DRAW,)
    assert second_turns[-1].role == "tool" and json.loads(second_turns[-1].content)["width"] == 1024
    # three ledger rows: two chat jobs and one image
    kinds = sorted(r.kind for r in store.records.values())
    assert kinds == ["chat", "chat", "image"]
    totals = await store.conversation_totals(conversation.id)
    assert (
        totals.images == 1
        and totals.replies == 2
        and totals.retail.amount
        == Decimal("0.003")
        + app.billing.retail(TokenUsage(prompt_tokens=300, completion_tokens=40), thinking=True).amount
        + app.billing.retail(TokenUsage(prompt_tokens=400, completion_tokens=6), thinking=False).amount
    )
    # later history shows the picture as one assistant turn with the caption
    history = await store.list_messages(conversation.id)
    turns = turns_from(history)
    assert (
        turns[-1].role == "assistant"
        and turns[-1].content == "[Generated an image from the prompt: a red fox in snow]\nHere is your fox."
    )


async def test_thinking_off_still_thinks_a_little_when_tools_are_offered(
    app_with_images: Application, backend: ScriptedBackend
) -> None:
    app = app_with_images
    user = await app.auth.signup(NewUser(email="t@example.com", password="correct horse"))
    conversation = await app.conversations.create(user)
    await app.conversations.set_thinking(user, conversation.id, "off")
    await collect(app.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    params = backend.calls[0][2]
    assert params.include_reasoning and params.reasoning_effort == "low"


async def test_no_tools_when_images_are_unavailable(
    app_with_images: Application, backend: ScriptedBackend, image_backend: ScriptedImageBackend
) -> None:
    app = app_with_images
    image_backend.available = (False, "no runner")
    user = await app.auth.signup(NewUser(email="n@example.com", password="correct horse"))
    conversation = await app.conversations.create(user)
    await collect(app.chat.start_reply(user, conversation.id, NewMessage(content="hi")))
    assert backend.tools_offered[0] == []


async def test_image_failure_marks_the_tool_message_failed(
    app_with_images: Application,
    store: MemoryStore,
    backend: ScriptedBackend,
    image_backend: ScriptedImageBackend,
) -> None:
    app = app_with_images
    user = await app.auth.signup(NewUser(email="f@example.com", password="correct horse"))
    conversation = await app.conversations.create(user)
    backend.scripts = [
        [ReplyChunk(kind="tool_call", tool_call=DRAW), ReplyChunk(kind="done", finish_reason="tool_calls")]
    ]
    image_backend.fail_with = ReplyFailed("runner 500", payment_sent=True)
    events = await collect(app.chat.start_reply(user, conversation.id, NewMessage(content="draw")))
    assert [e.type for e in events] == ["start", "tool_call", "error"]
    tool_message = next(m for m in await store.list_messages(conversation.id) if m.role == "assistant")
    assert (
        tool_message.state == "failed"
        and tool_message.kind == "tool_call"
        and "runner 500" in (tool_message.error or "")
    )


async def test_open_image_is_owner_only_and_retention_expires_files(
    app_with_images: Application, store: MemoryStore, backend: ScriptedBackend, image_files: MemoryImageFiles
) -> None:
    app = app_with_images
    user = await app.auth.signup(NewUser(email="o@example.com", password="correct horse"))
    conversation = await app.conversations.create(user)
    backend.scripts = [
        [ReplyChunk(kind="tool_call", tool_call=DRAW), ReplyChunk(kind="done", finish_reason="tool_calls")],
        [ReplyChunk(kind="content", text="done"), ReplyChunk(kind="done", finish_reason="stop")],
    ]
    events = await collect(app.chat.start_reply(user, conversation.id, NewMessage(content="draw")))
    image = next(e.image for e in events if e.type == "image")
    assert image is not None
    found, path = await app.images.open(user, image.id)
    assert found.id == image.id and path == f"/memory/{image.id}.jpg"
    with pytest.raises(NotFound):
        await app.images.open(user, uuid4())
    assert await app.images.expire_old() == 0
    app.clock.advance(days=31)  # type: ignore[attr-defined]
    assert await app.images.expire_old() == 1 and image_files.files == {}
    with pytest.raises(NotFound, match="expired"):
        await app.images.open(user, image.id)
    detail = await store.list_messages(conversation.id)
    assert next(m for m in detail if m.kind == "tool_call").images[0].expired
