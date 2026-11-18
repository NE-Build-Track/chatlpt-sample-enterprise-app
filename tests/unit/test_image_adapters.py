"""The image adapters: files on disk, the price table, and the engine-backed image job."""

import base64
import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from livepeer_builder import JobRequest, Runner
from livepeer_builder.testing import Fails, FakeEngine, Reply, runner

from chatlpt.adapters.engine_images import EngineImages, EngineOpenAIImages
from chatlpt.adapters.images import LocalImageFiles
from chatlpt.adapters.pricing_images import FileImagePriceSource
from chatlpt.errors import ChatUnavailable, InvalidRequest, ReplyFailed

ROOT = Path(__file__).resolve().parents[2]
IMAGE_APP = "comfystream/fal-flux-schnell"


async def test_local_files_fetch_save_path_delete(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("missing.jpg"):
            return httpx.Response(404)
        if request.url.path.endswith("huge.jpg"):
            return httpx.Response(200, content=b"x" * (25 * 1024 * 1024 + 1))
        return httpx.Response(200, content=b"\xff\xd8\xffdata", headers={"content-type": "image/jpeg"})

    files = LocalImageFiles(tmp_path / "img", transport=httpx.MockTransport(handler))
    data = await files.fetch("https://v3.fal.media/files/a/b.jpg")
    assert data.startswith(b"\xff\xd8")
    with pytest.raises(ReplyFailed, match="HTTP 404"):
        await files.fetch("https://v3.fal.media/files/missing.jpg")
    with pytest.raises(ReplyFailed, match="25 MB"):
        await files.fetch("https://v3.fal.media/files/huge.jpg")
    image_id = uuid4()
    relative = files.save(image_id, "image/png", data)
    assert relative == f"{image_id}.png" and (tmp_path / "img" / relative).read_bytes() == data
    assert files.path(relative).endswith(relative)
    with pytest.raises(ReplyFailed, match="outside"):
        files.path("../escape.png")
    files.delete(relative)
    assert not (tmp_path / "img" / relative).exists()
    files.delete(relative)  # idempotent


def test_image_price_table_loads_and_missing_file_fails() -> None:
    table = FileImagePriceSource(ROOT / "config" / "pricing" / "fal-flux-schnell.json").table()
    assert str(table.price_per_unit) == "0.003" and table.unit == "megapixel"
    with pytest.raises(InvalidRequest):
        FileImagePriceSource(ROOT / "config" / "pricing" / "nope.json")
    klein = FileImagePriceSource(ROOT / "config" / "pricing" / "flux-2-klein-4b.json").table()
    assert str(klein.price_per_unit) == "0.005" and klein.unit == "megapixel"  # D30


IMAGE_RUNNER = runner(IMAGE_APP, url="https://ai1/app", orchestrator_url="https://ai1:8936")


def image_engine(reply: Reply | Fails, *, runners: tuple[Runner, ...] = (IMAGE_RUNNER,)) -> FakeEngine:
    return FakeEngine(replies={(IMAGE_APP, "/"): reply}, runners=runners)


async def test_engine_images_runs_the_job_and_parses_the_result() -> None:
    engine = image_engine(
        Reply(
            data={
                "output": {
                    "images": [
                        {
                            "url": "https://v3.fal.media/x.jpg",
                            "width": 768,
                            "height": 1024,
                            "content_type": "image/jpeg",
                        }
                    ],
                    "seed": 7,
                    "has_nsfw_concepts": [False],
                }
            }
        )
    )
    images = EngineImages(engine, app=IMAGE_APP)
    assert images.ready() == (True, None)
    result = await images.generate(UUID(int=1), "a fox", "portrait_4_3", operation_ref="img-1")
    assert (result.url, result.width, result.height, result.seed, result.flagged) == (
        "https://v3.fal.media/x.jpg",
        768,
        1024,
        7,
        False,
    )
    request: JobRequest = engine.jobs.requests[0][1]
    assert request.app == IMAGE_APP and request.path == "/" and request.payload is not None
    assert request.payload["prompt"] == "a fox" and request.payload["image_size"] == "portrait_4_3"
    assert request.payload["enable_safety_checker"] is True and request.operation_ref == "img-1"
    assert result.orchestrator_url == "https://ai1:8936"  # from the job's attempt


async def test_engine_images_errors() -> None:
    empty = EngineImages(image_engine(Reply(data={"output": {"images": []}})), app=IMAGE_APP)
    with pytest.raises(ReplyFailed, match="no image"):
        await empty.generate(UUID(int=1), "p", "square", operation_ref="a")
    refused = EngineImages(image_engine(Fails(kind="no_offering", message="none")), app=IMAGE_APP)
    with pytest.raises(ChatUnavailable):
        await refused.generate(UUID(int=1), "p", "square", operation_ref="b")
    assert EngineImages(image_engine(Reply(), runners=()), app=IMAGE_APP).ready()[0] is False


# -- the openai.images.v1 profile: a WIDTHxHEIGHT size in, base64 PNGs in the answer, no URL ----------

OPENAI_APP = "text-to-image"
OPENAI_PATH = "/v1/images/generations"
FLUX2 = "black-forest-labs/FLUX.2-klein-4B"
ENVELOPE = json.dumps({"model": {"name": FLUX2}, "endpoints": {"images": {"profile": "openai.images.v1"}}})
OPENAI_RUNNER = runner(
    OPENAI_APP, url="https://ai1/app", orchestrator_url="https://ai1:8936", metadata=ENVELOPE
)


def png(width: int, height: int) -> bytes:
    """The start of a PNG file: the signature and the IHDR chunk that holds the size."""
    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + header + b"\x00\x00\x00\x00pixels"


def answer(*images: bytes) -> Reply:
    return Reply(data={"created": 1, "data": [{"b64_json": base64.b64encode(i).decode()} for i in images]})


def openai_engine(reply: Reply | Fails, *, runners: tuple[Runner, ...] = (OPENAI_RUNNER,)) -> FakeEngine:
    return FakeEngine(replies={(OPENAI_APP, OPENAI_PATH): reply}, runners=runners)


async def test_openai_images_asks_in_the_profile_s_words_and_reads_the_png() -> None:
    engine = openai_engine(answer(png(768, 1024)))
    images = EngineOpenAIImages(engine, app=OPENAI_APP)
    assert images.ready() == (True, None)
    result = await images.generate(UUID(int=1), "a fox", "portrait_4_3", operation_ref="img-1")
    request: JobRequest = engine.jobs.requests[0][1]
    assert (request.app, request.path, request.method) == (OPENAI_APP, OPENAI_PATH, "POST")
    # Only what is needed: the profile allows no unknown field, and ai1's runner answered 400 to a request
    # that also named the default ``response_format`` (18 November 2026).
    assert request.payload == {
        "model": FLUX2,  # the name the runner's own envelope gives
        "prompt": "a fox",
        "n": 1,
        "size": "512x512",
    }
    assert request.operation_ref == "img-1"
    assert result.data == png(768, 1024) and result.url == ""  # the bytes are in the answer
    assert (result.width, result.height) == (768, 1024)  # read from the PNG, not from what was asked
    assert (result.content_type, result.seed, result.flagged) == ("image/png", None, False)
    assert result.orchestrator_url == "https://ai1:8936"


@pytest.mark.parametrize(
    "preset",
    ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9", "?"],
)
async def test_openai_images_sends_every_preset_as_the_one_size_the_runner_takes(preset: str) -> None:
    """On 18 November 2026 ai1's runner drew 512x512 and answered 400, and charged, for 1024x768."""
    engine = openai_engine(answer(png(512, 512)))
    result = await EngineOpenAIImages(engine, app=OPENAI_APP).generate(
        UUID(int=1), "p", preset, operation_ref="a"
    )
    payload = engine.jobs.requests[0][1].payload
    assert payload is not None and payload["size"] == "512x512"
    assert (result.width, result.height) == (512, 512)  # what was drawn, so retail is for that


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (Reply(data={"created": 1, "data": []}), "no image"),
        (Reply(data={"created": 1, "data": [{"url": "https://elsewhere/x.png"}]}), "no image"),
        (Reply(data={"created": 1, "data": [{"b64_json": "not base64!"}]}), "not a PNG"),
        (answer(b"\xff\xd8\xff a JPEG"), "not a PNG"),
        (answer(b"\x89PNG\r\n\x1a\n short"), "not a PNG"),
        (answer(png(0, 768)), "not a PNG"),
    ],
)
async def test_openai_images_refuses_an_answer_with_no_usable_png(reply: Reply, message: str) -> None:
    images = EngineOpenAIImages(openai_engine(reply), app=OPENAI_APP)
    with pytest.raises(ReplyFailed, match=message) as raised:
        await images.generate(UUID(int=1), "p", "square", operation_ref="a")
    assert raised.value.payment_sent is True  # the job ran and was paid


async def test_openai_images_refuses_an_image_over_the_size_limit() -> None:
    huge = png(1024, 1024) + b"x" * (25 * 1024 * 1024)
    with pytest.raises(ReplyFailed, match="25 MB"):
        await EngineOpenAIImages(openai_engine(answer(huge)), app=OPENAI_APP).generate(
            UUID(int=1), "p", "square", operation_ref="a"
        )


async def test_openai_images_needs_a_runner_that_names_its_model() -> None:
    """The profile requires ``model``. A runner whose envelope names none is not asked, so nothing is paid."""
    for metadata in (None, "not json", json.dumps({"model": {}}), json.dumps({"model": {"name": ""}}), "[]"):
        nameless = runner(OPENAI_APP, url="https://ai1/app", metadata=metadata)
        engine = openai_engine(answer(png(64, 64)), runners=(nameless,))
        images = EngineOpenAIImages(engine, app=OPENAI_APP)
        assert images.ready() == (False, f"no runner for {OPENAI_APP} names its model")
        with pytest.raises(ChatUnavailable, match="names its model"):
            await images.generate(UUID(int=1), "p", "square", operation_ref="a")
        assert engine.jobs.requests == []
    assert EngineOpenAIImages(openai_engine(Reply(), runners=()), app=OPENAI_APP).ready() == (
        False,
        f"no runner advertises {OPENAI_APP} on the approved orchestrators",
    )


async def test_openai_images_maps_the_engine_s_failures_like_the_fal_backend() -> None:
    refused = EngineOpenAIImages(openai_engine(Fails(kind="no_offering", message="none")), app=OPENAI_APP)
    with pytest.raises(ChatUnavailable):
        await refused.generate(UUID(int=1), "p", "square", operation_ref="b")
