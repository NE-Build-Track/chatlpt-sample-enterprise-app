"""The context window is derived from the model and cached; history is fitted within it (D14)."""

from datetime import timedelta
from uuid import uuid4

from chatlpt.contracts import ChatTurn
from chatlpt.services.context import LAST_RESORT_WINDOW, ContextService
from chatlpt.testing import FixedClock, MemoryStore, ScriptedBackend

APP = "blueclaw/chat/qwen3.8-27b"


async def test_window_is_read_from_the_model_then_cached() -> None:
    backend, store, clock = ScriptedBackend(max_model_len=40_960), MemoryStore(), FixedClock()
    context = ContextService(backend, store, clock, ttl=timedelta(hours=24), override=None)
    assert await context.window(uuid4(), APP) == 40_960
    assert await context.window(uuid4(), APP) == 40_960
    assert backend.model_info_calls == 1  # the second read came from the cache
    clock.advance(hours=25)
    assert await context.window(uuid4(), APP) == 40_960
    assert backend.model_info_calls == 2  # expired, asked again


async def test_override_and_last_resort_when_the_model_cannot_be_asked() -> None:
    store, clock = MemoryStore(), FixedClock()
    assert (
        await ContextService(None, store, clock, ttl=timedelta(hours=1), override=16_000).window(uuid4(), APP)
        == 16_000
    )
    assert (
        await ContextService(None, store, clock, ttl=timedelta(hours=1), override=None).window(uuid4(), APP)
        == LAST_RESORT_WINDOW
    )


def test_fit_keeps_the_system_prompt_and_the_newest_turns() -> None:
    history = [ChatTurn(role="user" if i % 2 == 0 else "assistant", content="x" * 400) for i in range(10)]
    fitted, dropped = ContextService.fit("be brief", history, window=1000, reserve=200)
    assert fitted[0].role == "system" and dropped == 3
    assert [t.content for t in fitted[1:]] == [
        t.content for t in history[-7:]
    ]  # 100 tokens + 4 overhead each


def test_fit_always_keeps_the_last_turn_even_when_it_is_too_big() -> None:
    history = [ChatTurn(role="user", content="y" * 10_000)]
    fitted, dropped = ContextService.fit("sys", history, window=100, reserve=50)
    assert len(fitted) == 2 and fitted[1].content == history[0].content and dropped == 0


async def test_discovery_metadata_wins_and_costs_nothing() -> None:
    from chatlpt.contracts import ModelInfo

    class Advertised:
        def model_from_discovery(self, app: str) -> ModelInfo | None:
            return ModelInfo(
                app=app, model_id="Qwen3.8-27B", max_model_len=131072, observed_at=FixedClock().now()
            )

    backend, store, clock = ScriptedBackend(max_model_len=40_960), MemoryStore(), FixedClock()
    context = ContextService(
        backend, store, clock, ttl=timedelta(hours=24), override=None, metadata=Advertised()
    )
    assert await context.window(uuid4(), APP) == 131072
    assert backend.model_info_calls == 0  # no paid call
    cached = await store.get_model_info(APP)
    assert cached is not None and cached.max_model_len == 131072 and cached.observed_at == clock.now()
    assert await context.window(uuid4(), APP) == 131072  # cache already matches; nothing rewritten
