"""Settings come from CHATLPT_* variables and derive the approved hosts and admin set."""

from decimal import Decimal

from chatlpt.config import Settings


def test_from_env_reads_prefixed_variables_and_keeps_defaults() -> None:
    settings = Settings.from_env(
        {
            "CHATLPT_HTTP_PORT": "4000",
            "CHATLPT_ADMIN_EMAILS": "A@x.io, b@y.io",
            "CHATLPT_TEMPERATURE": "0.2",
            "OTHER": "1",
        }
    )
    assert settings.http_port == 4000 and settings.temperature == Decimal("0.2")
    assert settings.admin_email_set == frozenset({"a@x.io", "b@y.io"})
    assert settings.chat_app == "blueclaw/chat/qwen3.8-27b"


def test_approved_hosts_are_parsed_from_urls() -> None:
    assert Settings().approved_orchestrator_hosts == frozenset(
        {
            "orch-us-central.xodeapp.xyz",
            "us-central-metrics.speedybird.xyz",
            "orch-eu-central.open-pool.com",
            "hky.eliteencoder.net",
        }
    )
