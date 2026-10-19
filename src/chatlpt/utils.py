"""Shared helpers with no package dependencies. Any layer may import this module."""

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4


def utc(value: datetime) -> datetime:
    """Normalize to timezone-aware UTC (SQLite returns naive datetimes)."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> UUID:
    return uuid4()


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def estimate_tokens(text: str) -> int:
    """A rough token estimate for truncation decisions only (tech debt T1). Never used for billing."""
    return max(1, (len(text) + 3) // 4)
