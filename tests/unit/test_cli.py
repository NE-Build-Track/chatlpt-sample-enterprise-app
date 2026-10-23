"""The operator CLI: secrets, migrations, revisions, generated docs and the smoke check."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from chatlpt.cli import main

ROOT = Path(__file__).resolve().parents[2]


def test_gen_secret_prints_a_long_token(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["gen-secret"]) == 0
    assert len(capsys.readouterr().out.strip()) >= 48


def test_migrate_revision_and_smoke(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHATLPT_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/cli.db")
    monkeypatch.setenv("CHATLPT_PRICING_FILE", str(ROOT / "config" / "pricing" / "qwen3.8-27b.json"))
    monkeypatch.setenv("CHATLPT_SESSION_SECRET", "s")
    monkeypatch.delenv("LPB_SIGNER_URL", raising=False)
    monkeypatch.delenv("LPB_DISCOVERY_URL", raising=False)
    assert main(["migrate"]) == 0
    assert json.loads(capsys.readouterr().out)["revision"] == "0001"
    assert main(["revision"]) == 0
    assert json.loads(capsys.readouterr().out) == {"database": "0001", "package": "0001"}
    assert main(["smoke"]) == 0
    assert json.loads(capsys.readouterr().out)["ready"] is True


def test_gen_docs_check_passes_on_a_current_tree(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["gen-docs", "--check", "--out", str(ROOT / "docs" / "generated")]) == 0


def test_gen_docs_writes_to_a_fresh_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["gen-docs", "--out", str(tmp_path / "gen")]) == 0
    assert {p.name for p in (tmp_path / "gen").iterdir()} == {"openapi.json", "db-schema.md"}
    assert main(["gen-docs", "--check", "--out", str(tmp_path / "empty")]) == 1


def test_app_errors_exit_one(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("CHATLPT_PRICING_FILE", "/nonexistent.json")
    monkeypatch.setenv("CHATLPT_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.delenv("LPB_SIGNER_URL", raising=False)
    assert main(["smoke"]) == 1
    assert "pricing file" in capsys.readouterr().err


def test_make_admin_refuses_an_unverified_email_unless_told(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import asyncio
    from uuid import uuid4

    from chatlpt.contracts import User
    from chatlpt.store import SqlStore

    url = f"sqlite+aiosqlite:///{tmp_path}/admins.db"
    monkeypatch.setenv("CHATLPT_DATABASE_URL", url)

    async def seed() -> None:
        store = await SqlStore.connect(url)
        now = datetime.now(UTC)
        for email, verified in (("pw@example.com", False), ("g@example.com", True)):
            await store.create_user(
                User(id=uuid4(), email=email, display_name="x", is_admin=False, disabled=False,
                     created_at=now, email_verified=verified),
                None,
            )  # fmt: skip
        await store.close()

    asyncio.run(seed())
    assert main(["make-admin", "pw@example.com"]) == 1
    assert "not verified" in capsys.readouterr().err
    assert main(["make-admin", "pw@example.com", "--allow-unverified"]) == 0
    assert json.loads(capsys.readouterr().out)["is_admin"] is True
    assert main(["make-admin", "g@example.com"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "email": "g@example.com",
        "is_admin": True,
        "email_verified": True,
    }
    assert main(["revoke-admin", "g@example.com"]) == 0
    assert json.loads(capsys.readouterr().out)["is_admin"] is False
    assert main(["make-admin", "nobody@example.com"]) == 1


async def test_serve_stops_the_application_when_the_server_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import chatlpt.http
    from chatlpt import cli
    from chatlpt.runtime import Application

    monkeypatch.setenv("CHATLPT_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/serve.db")
    monkeypatch.setenv("CHATLPT_PRICING_FILE", str(ROOT / "config" / "pricing" / "qwen3.8-27b.json"))
    monkeypatch.setenv("CHATLPT_SESSION_SECRET", "s")
    monkeypatch.delenv("LPB_SIGNER_URL", raising=False)
    monkeypatch.delenv("LPB_DISCOVERY_URL", raising=False)
    stopped: list[Application] = []
    stop = Application.stop

    async def recording_stop(self: Application) -> None:
        stopped.append(self)
        await stop(self)

    def broken(app: Application) -> object:
        raise ValueError("a bug in the routes")

    monkeypatch.setattr(Application, "stop", recording_stop)
    monkeypatch.setattr(chatlpt.http, "create_app", broken)
    with pytest.raises(ValueError, match="routes"):
        await cli._serve(argparse.Namespace())
    assert len(stopped) == 1
