"""Shared fixtures: in-memory ports and a wired Application without the engine."""

from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr

from chatlpt.config import Settings
from chatlpt.runtime import Application
from chatlpt.testing import FixedClock, MemoryStore, PlainHasher, ScriptedBackend, StaticPrices


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def backend() -> ScriptedBackend:
    return ScriptedBackend()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        session_secret=SecretStr("test-secret"),
        static_dir="/nonexistent",
    )


@pytest.fixture
async def application(
    settings: Settings, store: MemoryStore, backend: ScriptedBackend, clock: FixedClock
) -> AsyncIterator[Application]:
    app = Application(
        settings,
        store=store,
        backend=backend,
        clock=clock,
        hasher=PlainHasher(),
        prices=StaticPrices(),
        oauth={},
    )
    await app.start()
    try:
        yield app
    finally:
        await app.stop()
