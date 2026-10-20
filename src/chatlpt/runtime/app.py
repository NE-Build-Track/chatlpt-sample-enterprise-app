"""``Application``: wires settings, store, the embedded engine and the services; owns the lifecycle."""

import asyncio
import contextlib
import logging
import os
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from chatlpt.adapters.clock import SystemClock
from chatlpt.adapters.images import LocalImageFiles
from chatlpt.adapters.oauth import GitHubProvider, GoogleProvider
from chatlpt.adapters.passwords import Argon2Hasher
from chatlpt.adapters.pricing import FilePriceSource
from chatlpt.adapters.pricing_images import FileImagePriceSource
from chatlpt.config import Settings
from chatlpt.contracts import AppHealth, ChatParams, Check, PriceTable
from chatlpt.protocols import (
    AppStore,
    ChatBackend,
    Clock,
    ImageBackend,
    ImageFiles,
    ImagePriceSource,
    ModelMetadataSource,
    OAuthProvider,
    PasswordHasher,
    PriceSource,
)
from chatlpt.runtime.engine import build_engine
from chatlpt.services.admin import AdminService
from chatlpt.services.auth import AuthService
from chatlpt.services.billing import BillingService
from chatlpt.services.chat import ChatService
from chatlpt.services.context import ContextService
from chatlpt.services.conversations import ConversationService
from chatlpt.services.images import ImageService
from chatlpt.services.limits import AttemptLimiter
from chatlpt.services.network import NetworkCostService
from chatlpt.store import SqlStore

_LOG = logging.getLogger(__name__)


def package_version() -> str:
    try:
        return version("chatlpt")
    except PackageNotFoundError:
        return "0.0.0"


class Application:
    def __init__(
        self,
        settings: Settings,
        *,
        store: AppStore,
        backend: ChatBackend | None,
        clock: Clock,
        hasher: PasswordHasher,
        prices: PriceSource,
        oauth: dict[str, OAuthProvider],
        engine: object | None = None,
        metadata: ModelMetadataSource | None = None,
        image_backend: ImageBackend | None = None,
        image_files: ImageFiles | None = None,
        image_prices: ImagePriceSource | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.backend = backend
        self.clock = clock
        self.oauth = oauth
        self._engine = engine
        params = ChatParams(
            system_prompt=settings.system_prompt,
            temperature=settings.temperature,
            max_output_tokens=settings.max_output_tokens,
            timeout_s=settings.reply_timeout_s,
        )
        self.auth = AuthService(store, hasher, clock, allow_signup=settings.allow_signup)
        self.attempts = AttemptLimiter(clock)
        self.conversations = ConversationService(store, clock, default_thinking=settings.default_thinking)
        self.context = ContextService(
            backend,
            store,
            clock,
            ttl=timedelta(hours=settings.model_info_ttl_hours),
            override=settings.context_window_override,
            metadata=metadata,
        )
        self.billing = BillingService(prices)
        # production passes both; tests may rely on the defaults (local images dir, committed price table)
        image_files = image_files or LocalImageFiles(Path(settings.images_dir))
        image_prices = image_prices or FileImagePriceSource(Path(settings.image_pricing_file))
        self.images = ImageService(
            image_backend,
            image_files,
            store,
            store,
            image_prices,
            clock,
            retention=timedelta(days=settings.image_retention_days),
        )
        self.chat = ChatService(
            store,
            store,
            self.conversations,
            backend,
            self.context,
            self.billing,
            clock,
            images=self.images,
            params=params,
            thinking_budgets={
                "off": 0,
                "low": settings.thinking_budget_low,
                "medium": settings.thinking_budget_medium,
                "high": settings.thinking_budget_high,
            },
            history_turn_limit=settings.history_turn_limit,
        )
        self.network = NetworkCostService(store, backend)  # read from the engine, never copied (D29)
        self.admin = AdminService(store, self.network)
        self._prices = prices
        self._metadata = metadata
        self._tasks: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()

    @classmethod
    async def from_settings(cls, settings: Settings | None = None) -> "Application":
        settings = settings or Settings.from_env()
        if os.environ.get("CHATLPT_ADMIN_EMAILS"):
            _LOG.warning(
                "CHATLPT_ADMIN_EMAILS is no longer read; grant admin with `chatlpt make-admin EMAIL` (D26)",
                extra={"event": "config.admin_emails_ignored"},
            )
        clock = SystemClock()
        store = await SqlStore.connect(settings.database_url, migrate=settings.auto_migrate)
        apps = frozenset({settings.chat_app} | ({settings.image_app} if settings.tools_enabled else set()))
        built = await build_engine(
            apps=apps, approved_hosts=settings.approved_orchestrator_hosts, clock=clock
        )
        backend: ChatBackend | None = None
        engine: object | None = None
        metadata: ModelMetadataSource | None = None
        image_backend: ImageBackend | None = None
        if built is not None:
            from chatlpt.adapters.engine import BufferedEngineChat, StreamingEngineChat
            from chatlpt.adapters.engine_images import EngineImages

            engine, metadata = built
            if settings.tools_enabled:
                image_backend = EngineImages(engine, app=settings.image_app)
            adapter = StreamingEngineChat if hasattr(engine.jobs, "stream") else BufferedEngineChat
            backend = adapter(
                engine, clock, app=settings.chat_app, idle_timeout_s=settings.reply_idle_timeout_s
            )
        oauth: dict[str, OAuthProvider] = {}
        if settings.google_client_id and settings.google_client_secret:
            oauth["google"] = GoogleProvider(
                settings.google_client_id, settings.google_client_secret.get_secret_value()
            )
        if settings.github_client_id and settings.github_client_secret:
            oauth["github"] = GitHubProvider(
                settings.github_client_id, settings.github_client_secret.get_secret_value()
            )
        return cls(
            settings,
            store=store,
            backend=backend,
            clock=clock,
            hasher=Argon2Hasher(),
            prices=FilePriceSource(Path(settings.pricing_file)),
            oauth=oauth,
            engine=engine,
            metadata=metadata,
            image_backend=image_backend,
            image_files=LocalImageFiles(Path(settings.images_dir)),
            image_prices=FileImagePriceSource(Path(settings.image_pricing_file)),
        )

    async def start(self) -> None:
        if self._engine is not None:
            await self._engine.start()  # type: ignore[attr-defined]
        self._stop.clear()
        self._tasks = [
            asyncio.create_task(self._retention_loop(), name="image-retention"),
        ]
        _LOG.info(
            "application started",
            extra={"event": "app.started", "version": package_version(), "engine": self._engine is not None},
        )

    async def stop(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []
        await self.chat.drain()
        if self._engine is not None:
            await self._engine.stop()  # type: ignore[attr-defined]
        await self.store.close()
        _LOG.info("application stopped", extra={"event": "app.stopped"})

    def billing_prices(self) -> PriceTable:
        return self._prices.table()

    async def _retention_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.images.expire_old()
            except Exception:
                _LOG.exception("image retention failed", extra={"event": "images.retention_crashed"})
            with contextlib.suppress(asyncio.TimeoutError, TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=3600)

    async def health(self) -> AppHealth:
        checks: list[Check] = []
        try:
            await self.store.list_users()
            checks.append(Check(name="database", ok=True))
        except Exception as error:
            checks.append(Check(name="database", ok=False, detail=str(error)))
        chat_available: bool = False
        reason: str | None = "engine not configured (LPB_SIGNER_URL)"
        if self.backend is not None:
            chat_available, reason = self.backend.ready()
        checks.append(Check(name="chat", ok=chat_available, detail=reason))
        images_ok, images_reason = self.images.ready()
        checks.append(Check(name="images", ok=images_ok, detail=images_reason))
        info = await self.context.model(self.settings.chat_app)
        if info is None and self._metadata is not None:
            info = self._metadata.model_from_discovery(self.settings.chat_app)
        return AppHealth(
            ready=all(c.ok for c in checks if c.name == "database"),
            version=package_version(),
            checks=tuple(checks),
            engine_configured=self.backend is not None,
            chat_available=chat_available,
            model=info.model_id if info else None,
            observed_at=self.clock.now(),
        )
