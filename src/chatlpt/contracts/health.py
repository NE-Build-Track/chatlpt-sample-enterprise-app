"""Health contract returned by ``GET /readyz``. Degraded states are named, never hidden."""

from datetime import datetime

from chatlpt.contracts.common import Contract


class Check(Contract):
    name: str
    ok: bool
    detail: str | None = None


class AppHealth(Contract):
    ready: bool
    version: str
    checks: tuple[Check, ...]
    engine_configured: bool
    chat_available: bool
    model: str | None
    observed_at: datetime
