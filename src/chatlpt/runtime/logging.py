"""Structured logging. Code logs with ``logger.info("message", extra={"event": "domain.action", ...})``.

``print`` is forbidden outside the CLI (tests/structure/test_taste.py), so every runtime signal is a JSON
line an agent or log pipeline can query. Fields whose names look like credentials are redacted.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}
_SECRET_WORDS = ("token", "secret", "password", "api_key", "payment_key", "authorization")


def _redact(key: str, value: Any) -> Any:
    name = key.lower()
    if name.endswith("_tokens"):
        return value  # token counts are usage, not credentials
    return "[redacted]" if any(word in name for word in _SECRET_WORDS) else value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update({k: _redact(k, v) for k, v in vars(record).items() if k not in _RESERVED})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(*, json_lines: bool = True, level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JsonFormatter() if json_lines else logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
