"""Generated images (D25): run the image app, keep the file, write both books, expire old files."""

import logging
import math
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from chatlpt.contracts import (
    Conversation,
    GeneratedImage,
    Money,
    TokenUsage,
    UsageRecord,
    User,
    WholesaleCost,
)
from chatlpt.errors import AppError, ChatUnavailable
from chatlpt.protocols import Clock, ImageBackend, ImageFiles, ImagePriceSource, ImageRepo, UsageLedger
from chatlpt.utils import new_id

_LOG = logging.getLogger(__name__)
SIZES = {"square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"}
DEFAULT_SIZE = "landscape_4_3"


def megapixels_billed(width: int, height: int) -> int:
    """fal bills by rounding up to the nearest megapixel (docs/references/fal-pricing.md)."""
    return max(1, math.ceil(width * height / 1_000_000))


class ImageService:
    def __init__(
        self,
        backend: ImageBackend | None,
        files: ImageFiles,
        images: ImageRepo,
        ledger: UsageLedger,
        prices: ImagePriceSource,
        clock: Clock,
        *,
        retention: timedelta,
    ) -> None:
        self._backend = backend
        self._files = files
        self._images = images
        self._ledger = ledger
        self._prices = prices
        self._clock = clock
        self._retention = retention

    @property
    def available(self) -> bool:
        return self._backend is not None and self._backend.ready()[0]

    def ready(self) -> tuple[bool, str | None]:
        if self._backend is None:
            return False, "image generation is not configured"
        return self._backend.ready()

    def retail(self, width: int, height: int) -> Money:
        table = self._prices.table()
        return Money(
            amount=Decimal(megapixels_billed(width, height)) * table.price_per_unit, currency=table.currency
        )

    async def generate(
        self, user: User, conversation: Conversation, message_id: UUID, prompt: str, image_size: str | None
    ) -> GeneratedImage:
        """One picture: the paid job, the bytes onto our volume, the image row and its ledger row."""
        if self._backend is None:
            raise ChatUnavailable("image generation is not configured")
        size = image_size if image_size in SIZES else DEFAULT_SIZE
        image_id = new_id()
        result = await self._backend.generate(user.id, prompt, size, operation_ref=str(image_id))
        data = await self._files.fetch(result.url)
        relative = self._files.save(image_id, result.content_type, data)
        now = self._clock.now()
        retail = self.retail(result.width, result.height)
        image = GeneratedImage(
            id=image_id,
            message_id=message_id,
            conversation_id=conversation.id,
            prompt=prompt,
            image_size=size,
            width=result.width,
            height=result.height,
            seed=result.seed,
            content_type=result.content_type,
            size_bytes=len(data),
            job_id=result.job_id,
            orchestrator_url=result.orchestrator_url,
            retail=retail,
            created_at=now,
        )
        await self._images.add_image(image, relative)
        await self._ledger.record(
            UsageRecord(
                message_id=image_id,
                kind="image",
                user_id=user.id,
                conversation_id=conversation.id,
                job_id=result.job_id,
                usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
                retail=retail,
                created_at=now,
            )
        )
        _LOG.info(
            "image generated",
            extra={
                "event": "images.generated",
                "image_id": str(image_id),
                "job_id": None if result.job_id is None else str(result.job_id),
                "size": f"{result.width}x{result.height}",
                "flagged": result.flagged,
            },
        )
        if image.job_id is None:
            return image
        pending = WholesaleCost(status="pending", orchestrator_url=image.orchestrator_url)
        return image.model_copy(update={"wholesale": pending})  # shown, never stored (D29)

    async def open(self, user: User, image_id: UUID) -> tuple[GeneratedImage, str]:
        """The image and its file path, for the owner only. Others get NotFound."""
        from chatlpt.errors import NotFound

        found = await self._images.get_image(image_id)
        if found is None:
            raise NotFound("image not found")
        image, relative = found
        if image.expired:
            raise NotFound("this image has expired")
        return image, self._files.path(relative)

    async def expire_old(self) -> int:
        """Delete files older than the retention window; rows stay and say the image expired."""
        cutoff = self._clock.now() - self._retention
        expired = 0
        for image, relative in await self._images.images_older_than(cutoff):
            try:
                self._files.delete(relative)
            except AppError as error:
                _LOG.warning(
                    "image not deleted", extra={"event": "images.delete_failed", "error": str(error)}
                )
                continue
            await self._images.mark_image_expired(image.id)
            expired += 1
        if expired:
            _LOG.info("images expired", extra={"event": "images.expired", "count": expired})
        return expired
