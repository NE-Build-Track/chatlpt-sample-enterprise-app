"""Wiring: the engine builder's degraded path, Application.from_settings, the wholesale loop and health."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from livepeer_builder import ActorApi, EngineSettings
from livepeer_builder.testing import FakeEngine
from pydantic import SecretStr, ValidationError

from chatlpt.config import Settings
from chatlpt.runtime import Application, package_version
from chatlpt.runtime.engine import build_engine
from chatlpt.testing import FixedClock, MemoryStore, PlainHasher, StaticPrices

ROOT = Path(__file__).resolve().parents[2]


SIGNER = "http://signer.test:8937"
DISCOVERY = "http://discovery.test:8939/discovery"


def engine_settings(tmp_path: Path, **values: object) -> EngineSettings:
    """The embedded engine's settings as a value; no ``LPB_*`` variable is read or set."""
    return EngineSettings.model_validate(
        {"database_url": f"sqlite+aiosqlite:///{tmp_path}/engine.db", "log_json": False, **values}
    )


async def test_build_engine_is_none_without_engine_settings() -> None:
    """No LPB_DISCOVERY_URL means no EngineSettings at all (builder-core D63 requires the URL), signer or not."""
    built = await build_engine(None, apps=frozenset({"a"}), approved_hosts=frozenset(), clock=FixedClock())
    assert built is None


async def test_build_engine_is_none_without_a_signer(tmp_path: Path) -> None:
    # the signer pays and livepeer/node's discovery lists runners (builder-core D63); chat needs both
    built = await build_engine(
        engine_settings(tmp_path, discovery_url=DISCOVERY),
        apps=frozenset({"a"}),
        approved_hosts=frozenset(),
        clock=FixedClock(),
    )
    assert built is None


def test_engine_settings_from_env_is_none_only_when_the_discovery_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from chatlpt.runtime.engine import engine_settings_from_env

    for name in ("LPB_DISCOVERY_URL", "LPB_SIGNER_URL", "LPB_DISCOVERY_INTERVAL_S"):
        monkeypatch.delenv(name, raising=False)
    assert engine_settings_from_env() is None
    monkeypatch.setenv("LPB_DISCOVERY_URL", "")  # empty is unset, as EngineSettings.from_env reads it
    assert engine_settings_from_env() is None
    monkeypatch.setenv("LPB_DISCOVERY_INTERVAL_S", "0")  # another invalid setting is never hidden
    with pytest.raises(ValidationError):
        engine_settings_from_env()
    monkeypatch.delenv("LPB_DISCOVERY_INTERVAL_S")
    monkeypatch.setenv("LPB_DISCOVERY_URL", "discovery:8939")  # a bad URL is an error, not "not configured"
    with pytest.raises(ValidationError):
        engine_settings_from_env()
    monkeypatch.setenv("LPB_DISCOVERY_URL", DISCOVERY)
    settings = engine_settings_from_env()
    assert settings is not None and settings.discovery_url == DISCOVERY


async def test_build_engine_with_a_signer_and_discovery_wires_the_filtered_discovery(tmp_path: Path) -> None:
    built = await build_engine(
        engine_settings(tmp_path, signer_url=SIGNER, discovery_url=DISCOVERY),
        apps=frozenset({"a"}),
        approved_hosts=frozenset({"h"}),
        clock=FixedClock(),
    )
    assert built is not None
    engine, source = built
    assert source.model_from_discovery("a") is None
    await engine.stop()


async def test_from_settings_boots_without_an_engine_and_configures_providers(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/app.db",
        session_secret=SecretStr("s"),
        pricing_file=str(ROOT / "config" / "pricing" / "qwen3.8-27b.json"),
        google_client_id="g",
        google_client_secret=SecretStr("gs"),
        github_client_id="h",
        github_client_secret=SecretStr("hs"),
    )
    app = await Application.from_settings(settings, None)  # no LPB_DISCOVERY_URL: no engine settings
    try:
        assert set(app.oauth) == {"google", "github"} and app.backend is None
        await app.start()
        health = await app.health()
        assert health.ready and not health.engine_configured and health.version == package_version()
        assert app.billing_prices().input_per_m == Decimal("0.5")
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


async def test_runtime_picks_the_streaming_adapter_when_the_engine_streams(tmp_path: Path) -> None:
    from chatlpt.adapters.engine import StreamingEngineChat

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/app.db",
        session_secret=SecretStr("s"),
        pricing_file=str(ROOT / "config" / "pricing" / "qwen3.8-27b.json"),
    )
    app = await Application.from_settings(
        settings, engine_settings(tmp_path, signer_url=SIGNER, discovery_url=DISCOVERY)
    )
    try:
        assert isinstance(app.backend, StreamingEngineChat)
    finally:
        await app.stop()


async def test_a_failure_while_building_closes_what_was_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from chatlpt.errors import InvalidRequest
    from chatlpt.runtime import app as app_module
    from chatlpt.store import SqlStore

    closed: list[SqlStore] = []
    close = SqlStore.close

    async def recording_close(self: SqlStore) -> None:
        closed.append(self)
        await close(self)

    built: list[ActorApi] = []
    build = app_module.build_engine

    async def recording_build(*args: Any, **kwargs: Any) -> Any:
        result = await build(*args, **kwargs)
        if result is not None:
            built.append(result[0])
        return result

    monkeypatch.setattr(SqlStore, "close", recording_close)
    monkeypatch.setattr(app_module, "build_engine", recording_build)
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/app.db",
        session_secret=SecretStr("s"),
        pricing_file=str(tmp_path / "missing.json"),  # fails after the store and the engine are open
    )
    with pytest.raises(InvalidRequest, match="pricing file"):
        await Application.from_settings(
            settings, engine_settings(tmp_path, signer_url=SIGNER, discovery_url=DISCOVERY)
        )
    assert len(closed) == 1
    with pytest.raises(RuntimeError, match="engine is stopped"):
        await built[0].start()


async def test_stop_runs_every_step_when_one_fails(caplog: pytest.LogCaptureFixture) -> None:
    class StuckEngine(FakeEngine):
        async def stop(self) -> None:
            raise RuntimeError("stuck")

    class Recording(MemoryStore):
        closed = False

        async def close(self) -> None:
            self.closed = True

    store = Recording()
    app = Application(
        Settings(session_secret=SecretStr("s")),
        store=store,
        backend=None,
        clock=FixedClock(),
        hasher=PlainHasher(),
        prices=StaticPrices(),
        oauth={},
        engine=StuckEngine(),
    )
    await app.stop()
    assert store.closed
    assert [r.event for r in caplog.records if r.levelname == "ERROR"] == ["app.stop_failed"]  # type: ignore[attr-defined]


async def test_stopping_twice_is_harmless(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/app.db",
        session_secret=SecretStr("s"),
        pricing_file=str(ROOT / "config" / "pricing" / "qwen3.8-27b.json"),
    )
    app = await Application.from_settings(
        settings,
        engine_settings(tmp_path, signer_url=SIGNER, discovery_url=DISCOVERY),  # an engine to stop twice
    )
    await app.start()
    await app.stop()  # the HTTP lifespan's stop
    await app.stop()  # then the CLI's finally
    assert not [r for r in caplog.records if r.levelname == "ERROR"]
