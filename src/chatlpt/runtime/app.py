"""``Application``: wires settings, store, the embedded engine and the services; owns the lifecycle."""

import asyncio
import contextlib
import logging
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from chatlpt.adapters.clock import SystemClock
from chatlpt.adapters.oauth import GitHubProvider, GoogleProvider
from chatlpt.adapters.passwords import Argon2Hasher
from chatlpt.adapters.pricing import FilePriceSource
from chatlpt.config import Settings
from chatlpt.contracts import AppHealth, ChatParams, Check, PriceTable
from chatlpt.protocols import (
    AppStore,
    ChatBackend,
    Clock,
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
            include_reasoning=settings.include_reasoning,
            timeout_s=settings.reply_timeout_s,
        )
        self.auth = AuthService(
            store, hasher, clock, admin_emails=settings.admin_email_set, allow_signup=settings.allow_signup
        )
        self.conversations = ConversationService(store, clock)
        self.context = ContextService(
            backend,
            store,
            clock,
            ttl=timedelta(hours=settings.model_info_ttl_hours),
            override=settings.context_window_override,
            metadata=metadata,
        )
        self.billing = BillingService(prices)
        self.chat = ChatService(
            store,
            store,
            self.conversations,
            backend,
            self.context,
            self.billing,
            clock,
            params=params,
            history_turn_limit=settings.history_turn_limit,
            wholesale_settle_window=timedelta(minutes=settings.wholesale_settle_minutes),
        )
        self.admin = AdminService(store, store)
        self._prices = prices
        self._metadata = metadata
        self._tasks: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()

    @classmethod
    async def from_settings(cls, settings: Settings | None = None) -> "Application":
        settings = settings or Settings.from_env()
        clock = SystemClock()
        store = await SqlStore.connect(settings.database_url, migrate=settings.auto_migrate)
        built = await build_engine(
            app=settings.chat_app, approved_hosts=settings.approved_orchestrator_hosts, clock=clock
        )
        backend: ChatBackend | None = None
        engine: object | None = None
        metadata: ModelMetadataSource | None = None
        if built is not None:
            from chatlpt.adapters.engine import BufferedEngineChat

            engine, metadata = built
            backend = BufferedEngineChat(engine, clock, app=settings.chat_app)
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
        )

    async def start(self) -> None:
        if self._engine is not None:
            await self._engine.start()  # type: ignore[attr-defined]
        self._stop.clear()
        self._tasks = [asyncio.create_task(self._wholesale_loop(), name="wholesale-sync")]
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

    async def _wholesale_loop(self) -> None:
        interval = self.settings.wholesale_sync_interval_s
        while not self._stop.is_set():
            try:
                filled = await self.chat.sync_wholesale()
                if filled:
                    _LOG.info(
                        "wholesale filled", extra={"event": "billing.wholesale_filled", "count": filled}
                    )
            except Exception:
                _LOG.exception("wholesale sync failed", extra={"event": "billing.wholesale_sync_crashed"})
            with contextlib.suppress(asyncio.TimeoutError, TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=interval)

    def billing_prices(self) -> PriceTable:
        return self._prices.table()

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
