"""Config layer: application settings from ``CHATLPT_*`` variables (docs/RELIABILITY.md#configuration).

The embedded engine reads its own ``LPB_*`` variables; this module does not duplicate them.
"""

import os
from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import Field, SecretStr

from chatlpt.contracts import Contract

ENV_PREFIX = "CHATLPT_"
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./chatlpt.db"
DEFAULT_SYSTEM_PROMPT = (
    "You are ChatLPT, a helpful assistant running on the Livepeer network. "
    "Answer clearly and concisely. Use Markdown when it helps."
)


class Settings(Contract):
    # persistence
    database_url: str = DEFAULT_DATABASE_URL
    auto_migrate: bool = True

    # http
    public_base_url: str = "http://localhost:3050"  # OAuth callbacks are built from this (D18)
    http_host: str = "127.0.0.1"
    http_port: int = Field(default=3050, ge=1, le=65535)
    static_dir: str = "web/dist"
    session_secret: SecretStr | None = None  # required to serve; `chatlpt gen-secret` prints one
    session_ttl_hours: int = Field(default=24 * 14, ge=1)
    secure_cookies: bool = False  # set true behind TLS
    trust_forwarded_for: bool = False  # behind a reverse proxy: rate-limit by X-Forwarded-For (D26)

    # identity
    allow_signup: bool = True  # D5; open by default; close it for a public deployment (docs/RELIABILITY.md)
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None

    # the model
    chat_app: str = "blueclaw/chat/qwen3.8-27b"
    # D8: only runners on these orchestrators are offered to the engine (comma-separated URLs)
    approved_orchestrators: str = (
        "https://orch-us-central.xodeapp.xyz:18935,https://us-central-metrics.speedybird.xyz:28935,"
        "https://orch-eu-central.open-pool.com:443,https://hky.eliteencoder.net:8936,"
        "https://ai1.eliteencoder.net:8936"
    )
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    temperature: Decimal = Field(default=Decimal("0.7"), ge=0, le=2)
    max_output_tokens: int = Field(default=32_768, ge=1)  # answer + thinking; the network bills per second
    default_thinking: Literal["off", "low", "medium", "high"] = "medium"  # per conversation (D24)
    thinking_budget_low: int = Field(default=1024, ge=1)  # chain-of-thought caps per level (vLLM/Qwen)
    thinking_budget_medium: int = Field(default=4096, ge=1)
    thinking_budget_high: int = Field(default=16_384, ge=1)
    reply_timeout_s: float = Field(default=300.0, gt=0, le=3600)
    reply_idle_timeout_s: float = Field(
        default=60.0, gt=0, le=3600
    )  # longest silence inside a streamed reply
    context_window_override: int | None = Field(default=None, ge=1)  # last resort (D14)
    model_info_ttl_hours: int = Field(default=24, ge=1)
    history_turn_limit: int = Field(default=60, ge=1)

    # images (D25): the assistant draws through a tool call; the app runs the image app and keeps the file
    image_app: str = "comfystream/fal-flux-schnell"
    tools_enabled: bool = True
    images_dir: str = "./.local/images"
    image_retention_days: int = Field(default=30, ge=1)
    image_pricing_file: str = "config/pricing/fal-flux-schnell.json"

    # billing
    pricing_file: str = "config/pricing/qwen3.8-27b.json"

    # operations
    log_json: bool = True

    @property
    def approved_orchestrator_hosts(self) -> frozenset[str]:
        from urllib.parse import urlparse

        hosts = (urlparse(u.strip()).hostname for u in self.approved_orchestrators.split(",") if u.strip())
        return frozenset(h.lower() for h in hosts if h)

    @property
    def engine_configured(self) -> bool:
        return bool(os.environ.get("LPB_SIGNER_URL"))

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        """Build settings from ``CHATLPT_<FIELD>`` variables; unset variables keep their defaults."""
        source = os.environ if env is None else env
        values: dict[str, str] = {}
        for name in cls.model_fields:
            raw = source.get(ENV_PREFIX + name.upper())
            if raw is not None and raw != "":
                values[name] = raw
        return cls.model_validate(values)
