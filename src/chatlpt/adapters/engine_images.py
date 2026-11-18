"""The ImageBackend over the embedded engine: one buffered ``jobs.run`` per picture (D25, D30).

Two image apps speak two formats. ``EngineImages`` is the fal FLUX app: a preset name in, a temporary URL
out. ``EngineOpenAIImages`` is the ``openai.images.v1`` runner profile: a ``WIDTHxHEIGHT`` size in, the PNG
as base64 inside the answer, and no URL.
"""

import base64
import binascii
import json
from typing import Any
from uuid import UUID

from livepeer_builder import (
    ActorApi,
    EngineError,
    JobFailed,
    JobRequest,
    NoCapacity,
    NotProvisioned,
    OperationConflict,
    OperationExists,
    ProviderUnavailable,
)

from chatlpt.adapters.engine import actor_for, failure_from
from chatlpt.errors import ChatUnavailable, Conflict, ReplyFailed


class EngineImageResult:
    def __init__(self, data: dict[str, Any], job_id: UUID | None, orchestrator_url: str | None) -> None:
        output_raw = data.get("output")
        output: dict[str, Any] = output_raw if isinstance(output_raw, dict) else {}
        images_raw = output.get("images")
        images: list[Any] = images_raw if isinstance(images_raw, list) else []
        first: dict[str, Any] = images[0] if images and isinstance(images[0], dict) else {}
        if not first.get("url"):
            raise ReplyFailed("the image app returned no image", payment_sent=True)
        self.url = str(first["url"])
        self.data: bytes | None = None  # the app keeps the file; the image service fetches it
        self.width = int(first.get("width") or 0)
        self.height = int(first.get("height") or 0)
        seed = output.get("seed")
        self.seed = seed if isinstance(seed, int) else None
        self.content_type = str(first.get("content_type") or "image/jpeg")
        flags = output.get("has_nsfw_concepts")
        self.flagged = bool(flags[0]) if isinstance(flags, list) and flags else False
        self.job_id = job_id
        self.orchestrator_url = orchestrator_url


class EngineImages:
    """The ImageBackend: one buffered ``jobs.run`` per picture on the fal FLUX app (D25)."""

    def __init__(self, engine: ActorApi, *, app: str, max_attempts: int = 2) -> None:
        self._engine = engine
        self.app = app
        self._max_attempts = max_attempts

    def ready(self) -> tuple[bool, str | None]:
        if not self._engine.discovery.candidates(self.app):
            return False, f"no runner advertises {self.app} on the approved orchestrators"
        return True, None

    async def generate(
        self, user_id: UUID, prompt: str, image_size: str, operation_ref: str
    ) -> EngineImageResult:
        payload = {"prompt": prompt, "image_size": image_size, "num_images": 1, "enable_safety_checker": True}
        request = JobRequest(
            app=self.app,
            path="/",
            method="POST",
            payload=payload,
            operation_ref=operation_ref,
            max_attempts=self._max_attempts,
            timeout_s=120,
        )
        data, job_id, orchestrator_url = await _run(self._engine, user_id, request)
        return EngineImageResult(data, job_id, orchestrator_url)


async def _run(
    engine: ActorApi, user_id: UUID, request: JobRequest
) -> tuple[dict[str, Any], UUID | None, str | None]:
    """One paid job: its JSON answer, its id and the orchestrator that ran it, or the app's own error."""
    try:
        result = await engine.jobs.run(actor_for(user_id), request)
    except JobFailed as exc:
        raise failure_from(exc) from exc
    except (NoCapacity, NotProvisioned, ProviderUnavailable) as exc:
        raise ChatUnavailable(str(exc)) from exc
    except (OperationExists, OperationConflict) as exc:
        raise Conflict(str(exc)) from exc
    except EngineError as exc:
        raise ReplyFailed(str(exc), payment_sent=False) from exc
    data = result.data if isinstance(result.data, dict) else {}
    attempt = result.job.attempts[-1] if result.job.attempts else None
    return data, result.job.id, attempt.orchestrator_url if attempt else None


# -- the openai.images.v1 profile (D30) ----------------------------------------------------------------

OPENAI_IMAGES_PATH = "/v1/images/generations"
# The tool's presets in pixels, as fal defines them (docs/references/fal-pricing.md). The profile takes
# WIDTHxHEIGHT, each side 256 to 2048; FLUX rounds a side down to a multiple of 16, and these all are.
PIXELS = {
    "square_hd": (1024, 1024),
    "square": (512, 512),
    "portrait_4_3": (768, 1024),
    "portrait_16_9": (576, 1024),
    "landscape_4_3": (1024, 768),
    "landscape_16_9": (1024, 576),
}
_DEFAULT_PIXELS = PIXELS["landscape_4_3"]
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_BYTES = 25 * 1024 * 1024  # the limit adapters/images.py puts on a fetched image


def _png_size(image: bytes) -> tuple[int, int] | None:
    """Width and height from a PNG's IHDR chunk, the first after the signature. None when it is no PNG."""
    if len(image) < 24 or not image.startswith(_PNG_SIGNATURE) or image[12:16] != b"IHDR":
        return None
    width, height = int.from_bytes(image[16:20], "big"), int.from_bytes(image[20:24], "big")
    return (width, height) if width > 0 and height > 0 else None


def _model_name(metadata: str | None) -> str | None:
    """``model.name`` from a runner's envelope, the name the profile's ``model`` field takes."""
    try:
        envelope = json.loads(metadata or "")
    except ValueError:
        return None
    model = envelope.get("model") if isinstance(envelope, dict) else None
    name = model.get("name") if isinstance(model, dict) else None
    return name if isinstance(name, str) and name else None


class OpenAIImageResult:
    def __init__(self, data: dict[str, Any], job_id: UUID | None, orchestrator_url: str | None) -> None:
        items_raw = data.get("data")
        items: list[Any] = items_raw if isinstance(items_raw, list) else []
        first: dict[str, Any] = items[0] if items and isinstance(items[0], dict) else {}
        encoded = first.get("b64_json")
        if not isinstance(encoded, str) or not encoded:
            raise ReplyFailed("the image app returned no image", payment_sent=True)
        try:
            image = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            image = b""
        size = _png_size(image)
        if size is None:
            raise ReplyFailed("the image app's answer is not a PNG image", payment_sent=True)
        if len(image) > _MAX_BYTES:
            raise ReplyFailed("the image is larger than the 25 MB limit", payment_sent=True)
        self.url = ""  # the profile returns no URL
        self.data: bytes | None = image
        self.width, self.height = size  # what the runner drew, which may differ from what was asked
        self.seed: int | None = None  # the profile does not report the seed it used
        self.content_type = "image/png"
        self.flagged = False  # the profile has no safety checker
        self.job_id = job_id
        self.orchestrator_url = orchestrator_url


class EngineOpenAIImages:
    """The ImageBackend for a runner that speaks ``openai.images.v1`` (D30)."""

    def __init__(self, engine: ActorApi, *, app: str, max_attempts: int = 2) -> None:
        self._engine = engine
        self.app = app
        self._max_attempts = max_attempts

    def _model(self) -> str | None:
        names = (_model_name(runner.metadata) for runner in self._engine.discovery.candidates(self.app))
        return next((name for name in names if name), None)

    def ready(self) -> tuple[bool, str | None]:
        if not self._engine.discovery.candidates(self.app):
            return False, f"no runner advertises {self.app} on the approved orchestrators"
        if self._model() is None:
            return False, f"no runner for {self.app} names its model"
        return True, None

    async def generate(
        self, user_id: UUID, prompt: str, image_size: str, operation_ref: str
    ) -> OpenAIImageResult:
        model = self._model()
        if model is None:  # the profile requires it; asking without it would pay for a refusal
            raise ChatUnavailable(f"no runner for {self.app} names its model")
        width, height = PIXELS.get(image_size, _DEFAULT_PIXELS)
        request = JobRequest(
            app=self.app,
            path=OPENAI_IMAGES_PATH,
            method="POST",
            # ``response_format`` is left out: b64_json is the profile's only value and its default.
            payload={"model": model, "prompt": prompt, "n": 1, "size": f"{width}x{height}"},
            operation_ref=operation_ref,
            max_attempts=self._max_attempts,
            timeout_s=120,
        )
        data, job_id, orchestrator_url = await _run(self._engine, user_id, request)
        return OpenAIImageResult(data, job_id, orchestrator_url)
