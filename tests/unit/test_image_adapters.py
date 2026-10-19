"""The image adapters: files on disk, the price table, and the engine-backed image job."""

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from livepeer_builder import JobRequest, JobResult
from livepeer_builder.contracts import Failure, Runner
from livepeer_builder.errors import JobFailed

from chatlpt.adapters.engine_images import EngineImages
from chatlpt.adapters.images import LocalImageFiles
from chatlpt.adapters.pricing_images import FileImagePriceSource
from chatlpt.errors import ChatUnavailable, InvalidRequest, ReplyFailed
from tests.unit.test_engine_backend import FakeEngine, job

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


def _image_result(data: dict[str, Any]) -> JobResult:
    return JobResult(job=job(), status_code=200, content=b"{}", content_type="application/json", data=data)


@pytest.fixture
def engine() -> FakeEngine:
    fake = FakeEngine()
    fake.discovery.runners.append(
        Runner(
            url="https://ai1/app",
            app=IMAGE_APP,
            runner_id=None,
            mode="single-shot",
            orchestrator_url="https://ai1:8936",
            capacity=4,
            capacity_available=4,
            rate=None,
        )
    )
    return fake


async def test_engine_images_runs_the_job_and_parses_the_result(engine: FakeEngine) -> None:
    images = EngineImages(engine, app=IMAGE_APP)  # type: ignore[arg-type]
    assert images.ready() == (True, None)
    engine.jobs.outcome = _image_result(
        {
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
    assert result.orchestrator_url == "https://o:1"  # from the job's attempt


async def test_engine_images_errors(engine: FakeEngine) -> None:
    images = EngineImages(engine, app=IMAGE_APP)  # type: ignore[arg-type]
    engine.jobs.outcome = _image_result({"output": {"images": []}})
    with pytest.raises(ReplyFailed, match="no image"):
        await images.generate(UUID(int=1), "p", "square", operation_ref="a")
    engine.jobs.outcome = JobFailed(job(state="failed", failure=Failure(kind="no_offering", message="none")))
    with pytest.raises(ChatUnavailable):
        await images.generate(UUID(int=1), "p", "square", operation_ref="b")
    engine.discovery.runners = [r for r in engine.discovery.runners if r.app != IMAGE_APP]
    assert images.ready()[0] is False
