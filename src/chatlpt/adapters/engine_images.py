"""The ImageBackend over the embedded engine: one buffered ``jobs.run`` per picture on the FLUX app (D25)."""

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
        try:
            result = await self._engine.jobs.run(actor_for(user_id), request)
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
        return EngineImageResult(data, result.job.id, attempt.orchestrator_url if attempt else None)
