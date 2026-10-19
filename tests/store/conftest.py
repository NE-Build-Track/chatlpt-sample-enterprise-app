"""Both AppStore implementations run the same contract suite."""

from collections.abc import AsyncIterator

import pytest

from chatlpt.protocols import AppStore
from chatlpt.store import SqlStore
from chatlpt.testing import MemoryStore


@pytest.fixture(params=["memory", "sqlite"])
async def app_store(request: pytest.FixtureRequest, tmp_path: object) -> AsyncIterator[AppStore]:
    if request.param == "memory":
        yield MemoryStore()
        return
    store = await SqlStore.connect(f"sqlite+aiosqlite:///{tmp_path}/store.db")
    try:
        yield store
    finally:
        await store.close()
