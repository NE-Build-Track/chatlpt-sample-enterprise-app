"""Wiring: the engine builder's degraded path, Application.from_settings, the wholesale loop and health."""

from decimal import Decimal
from pathlib import Path

from livepeer_builder import EngineSettings
from pydantic import SecretStr

from chatlpt.config import Settings
from chatlpt.runtime import Application, package_version
from chatlpt.runtime.engine import build_engine
from chatlpt.testing import FixedClock, MemoryStore, PlainHasher, StaticPrices

ROOT = Path(__file__).resolve().parents[2]


def engine_settings(tmp_path: Path, **values: object) -> EngineSettings:
    """The embedded engine's settings as a value; no ``LPB_*`` variable is read or set."""
    return EngineSettings.model_validate(
        {"database_url": f"sqlite+aiosqlite:///{tmp_path}/engine.db", "log_json": False, **values}
    )


async def test_build_engine_is_none_without_a_signer(tmp_path: Path) -> None:
    built = await build_engine(
        engine_settings(tmp_path), apps=frozenset({"a"}), approved_hosts=frozenset(), clock=FixedClock()
    )
    assert built is None


async def test_build_engine_with_a_signer_wires_the_filtered_discovery(tmp_path: Path) -> None:
    built = await build_engine(
        engine_settings(tmp_path, signer_url="http://signer.test:8937"),
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
    app = await Application.from_settings(settings, engine_settings(tmp_path))
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
        settings, engine_settings(tmp_path, signer_url="http://signer.test:8937")
    )
    try:
        assert isinstance(app.backend, StreamingEngineChat)
    finally:
        await app.stop()
