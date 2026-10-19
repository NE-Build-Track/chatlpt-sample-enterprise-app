"""The small adapters: argon2 hashing, the price file, the system clock and structured logging."""

import json
import logging
from datetime import UTC
from decimal import Decimal
from pathlib import Path

import pytest

from chatlpt.adapters.clock import SystemClock
from chatlpt.adapters.passwords import Argon2Hasher
from chatlpt.adapters.pricing import FilePriceSource
from chatlpt.contracts import Money
from chatlpt.errors import InvalidRequest
from chatlpt.runtime.logging import JsonFormatter, configure_logging
from chatlpt.utils import estimate_tokens, random_token, sha256_hex, utc

ROOT = Path(__file__).resolve().parents[2]


def test_argon2_round_trip_and_rejections() -> None:
    hasher = Argon2Hasher()
    hashed = hasher.hash("correct horse")
    assert hashed.startswith("$argon2id$") and hasher.verify("correct horse", hashed)
    assert not hasher.verify("wrong", hashed)
    assert not hasher.verify("correct horse", "not-a-hash")


def test_price_file_loads_the_committed_table() -> None:
    table = FilePriceSource(ROOT / "config" / "pricing" / "qwen3.8-27b.json").table()
    assert table.input_per_m == Decimal("0.5") and table.output_per_m == Decimal("3")
    assert table.cached_input_per_m == Decimal("0.1") and table.region.startswith("Singapore")
    with pytest.raises(InvalidRequest):
        FilePriceSource(ROOT / "config" / "pricing" / "missing.json")


def test_system_clock_is_utc_aware() -> None:
    assert SystemClock().now().tzinfo is UTC


def test_json_formatter_redacts_secret_looking_fields_and_keeps_events() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    record.event = "auth.login"
    record.api_key = "lpg_secret"
    record.user_id = "u1"
    entry = json.loads(JsonFormatter().format(record))
    assert entry["event"] == "auth.login" and entry["user_id"] == "u1" and entry["level"] == "info"
    assert entry["api_key"] == "[redacted]"


def test_configure_logging_installs_one_handler() -> None:
    configure_logging(json_lines=True)
    configure_logging(json_lines=False)
    assert len(logging.getLogger().handlers) == 1


def test_money_and_utils() -> None:
    assert Money(amount=Decimal("1.5")) + Money(amount=Decimal("0.5")) == Money(amount=Decimal("2.0"))
    assert Money.zero().amount == 0
    with pytest.raises(ValueError, match="different currencies"):
        Money(amount=Decimal(1)) + Money.zero().model_copy(update={"currency": "EUR"})
    with pytest.raises(ValueError, match="finite"):
        Money(amount=Decimal("Infinity"))
    assert len(sha256_hex("x")) == 64 and random_token() != random_token()
    assert estimate_tokens("") == 1 and estimate_tokens("abcdefgh") == 2
    from datetime import datetime

    assert utc(datetime(2026, 1, 1)).tzinfo is UTC
