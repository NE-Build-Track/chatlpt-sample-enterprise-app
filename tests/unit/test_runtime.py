"""Wiring: the engine builder's degraded path, Application.from_settings, the wholesale loop and health."""

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from chatlpt.config import Settings
from chatlpt.contracts import Money, NewMessage, NewUser, WholesaleCost
from chatlpt.runtime import Application, package_version
from chatlpt.runtime.engine import build_engine
from chatlpt.testing import FixedClock, MemoryStore, PlainHasher, ScriptedBackend, StaticPrices

ROOT = Path(__file__).resolve().parents[2]


async def test_build_engine_is_none_without_a_signer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LPB_SIGNER_URL", raising=False)
    monkeypatch.delenv("LPB_DISCOVERY_URL", raising=False)
    assert await build_engine(app="a", approved_hosts=frozenset()) is None


async def test_build_engine_with_a_signer_wires_the_filtered_discovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LPB_SIGNER_URL", "http://signer.test:8937")
    monkeypatch.setenv("LPB_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/engine.db")
    monkeypatch.delenv("LPB_BATTERIES_URL", raising=False)
    engine = await build_engine(app="a", approved_hosts=frozenset({"h"}))
    assert engine is not None
    assert type(engine.discovery._source).__name__ == "ApprovedChatRunnersOnly"
    await engine.stop()


async def test_from_settings_boots_without_an_engine_and_configures_providers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("LPB_SIGNER_URL", raising=False)
    monkeypatch.delenv("LPB_DISCOVERY_URL", raising=False)
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/app.db",
        session_secret=SecretStr("s"),
        pricing_file=str(ROOT / "config" / "pricing" / "qwen3.8-27b.json"),
        google_client_id="g",
        google_client_secret=SecretStr("gs"),
        github_client_id="h",
        github_client_secret=SecretStr("hs"),
    )
    app = await Application.from_settings(settings)
    try:
        assert set(app.oauth) == {"google", "github"} and app.backend is None
        await app.start()
        health = await app.health()
        assert health.ready and not health.engine_configured and health.version == package_version()
        assert app.billing_prices().input_per_m == Decimal("0.5")
    finally:
        await app.stop()


async def test_wholesale_loop_fills_costs_and_survives_errors() -> None:
    store, backend, clock = MemoryStore(), ScriptedBackend(), FixedClock()
    settings = Settings(session_secret=SecretStr("s"), wholesale_sync_interval_s=0.01)
    app = Application(
        settings,
        store=store,
        backend=backend,
        clock=clock,
        hasher=PlainHasher(),
        prices=StaticPrices(),
        oauth={},
    )
    user = await app.auth.signup(NewUser(email="a@example.com", password="correct horse"))
    conversation = await app.conversations.create(user)
    queue = app.chat.start_reply(user, conversation.id, NewMessage(content="hi"))
    while await queue.get() is not None:
        pass
    backend.costs[backend.job_ids[0]] = WholesaleCost(
        status="delivered", amount=Money(amount=Decimal("0.00001"))
    )
    await app.start()
    try:
        for _ in range(100):
            if not await store.pending_wholesale():
                break
            await asyncio.sleep(0.01)
        assert await store.pending_wholesale() == []
    finally:
        await app.stop()


async def test_health_reports_a_broken_database() -> None:
    class Broken(MemoryStore):
        async def list_users(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("disk gone")

    app = Application(
        Settings(session_secret=SecretStr("s")),
        store=Broken(),
        backend=None,
        clock=FixedClock(),
        hasher=PlainHasher(),
        prices=StaticPrices(),
        oauth={},
    )
    health = await app.health()
    assert not health.ready and health.checks[0].detail == "disk gone"
