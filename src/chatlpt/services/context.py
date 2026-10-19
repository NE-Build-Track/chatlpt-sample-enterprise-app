"""The context window: derived from the model, cached, and used to fit history (D14, tech debt T1)."""

import logging
from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from chatlpt.contracts import ChatTurn, ModelInfo
from chatlpt.errors import AppError
from chatlpt.protocols import ChatBackend, Clock, ModelInfoCache, ModelMetadataSource
from chatlpt.utils import estimate_tokens

_LOG = logging.getLogger(__name__)
LAST_RESORT_WINDOW = 8192  # used only when the model cannot be asked and no override is configured
TURN_OVERHEAD_TOKENS = 4  # chat-template framing per turn, approximate


class ContextService:
    def __init__(
        self,
        backend: ChatBackend | None,
        cache: ModelInfoCache,
        clock: Clock,
        *,
        ttl: timedelta,
        override: int | None,
        metadata: ModelMetadataSource | None = None,
    ) -> None:
        self._backend = backend
        self._metadata = metadata
        self._cache = cache
        self._clock = clock
        self._ttl = ttl
        self._override = override

    async def window(self, user_id: UUID, app: str) -> int:
        """Discovery metadata first (free), then the cache, then ``GET /v1/models`` (paid), then fallbacks."""
        advertised = self._metadata.model_from_discovery(app) if self._metadata is not None else None
        if advertised is not None:
            cached = await self._cache.get_model_info(app)
            if (
                cached is None
                or cached.max_model_len != advertised.max_model_len
                or cached.model_id != advertised.model_id
            ):
                await self._cache.put_model_info(
                    advertised.model_copy(update={"observed_at": self._clock.now()})
                )
            return advertised.max_model_len
        cached = await self._cache.get_model_info(app)
        if cached is not None and self._clock.now() - cached.observed_at < self._ttl:
            return cached.max_model_len
        if self._backend is not None:
            try:
                info = await self._backend.model_info(user_id)
            except AppError as error:
                _LOG.warning(
                    "model info unavailable",
                    extra={"event": "context.model_info_failed", "error": str(error)},
                )
            else:
                await self._cache.put_model_info(info.model_copy(update={"observed_at": self._clock.now()}))
                return info.max_model_len
        if cached is not None:
            return cached.max_model_len  # stale, but the model's own figure
        if self._override is not None:
            return self._override
        _LOG.warning(
            "context window defaulted",
            extra={"event": "context.window_defaulted", "window": LAST_RESORT_WINDOW},
        )
        return LAST_RESORT_WINDOW

    async def model(self, app: str) -> ModelInfo | None:
        return await self._cache.get_model_info(app)

    @staticmethod
    def fit(
        system_prompt: str, history: Sequence[ChatTurn], *, window: int, reserve: int
    ) -> tuple[list[ChatTurn], int]:
        """Keep the system prompt and the newest turns that fit ``window - reserve``.

        The last turn always stays, even when it alone exceeds the budget.
        """
        budget = window - reserve - estimate_tokens(system_prompt) - TURN_OVERHEAD_TOKENS
        kept: list[ChatTurn] = []
        for turn in reversed(history):
            cost = estimate_tokens(turn.content) + TURN_OVERHEAD_TOKENS
            if kept and cost > budget:
                break
            kept.append(turn)
            budget -= cost
        kept.reverse()
        return [ChatTurn(role="system", content=system_prompt), *kept], len(history) - len(kept)
