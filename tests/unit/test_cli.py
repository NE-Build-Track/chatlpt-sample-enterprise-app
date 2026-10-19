"""The operator CLI: secrets, migrations, revisions, generated docs and the smoke check."""

import json
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
    assert json.loads(capsys.readouterr().out)["revision"] == "0003"
    assert main(["revision"]) == 0
    assert json.loads(capsys.readouterr().out) == {"database": "0003", "package": "0003"}
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
