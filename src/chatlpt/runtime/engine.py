"""Build the embedded BuilderEngine from ``LPB_*`` settings, filtering discovery to our app and hosts (D8)."""

import logging
from collections.abc import Sequence
from urllib.parse import urlparse

from livepeer_builder import BuilderEngine, EngineSettings, Runner
from livepeer_builder.adapters.sdk import SignerDiscoverySource
from livepeer_builder.protocols import DiscoverySource

_LOG = logging.getLogger(__name__)


class ApprovedChatRunnersOnly:
    """Keeps runners advertising ``app`` on an approved orchestrator host. Decorates the signer's source."""

    def __init__(self, inner: DiscoverySource, *, app: str, hosts: frozenset[str]) -> None:
        self._inner = inner
        self._app = app
        self._hosts = hosts

    async def fetch(self) -> tuple[Runner, ...]:
        runners = await self._inner.fetch()
        kept = tuple(r for r in runners if r.app == self._app and self._host_ok(r.orchestrator_url))
        dropped = len(runners) - len(kept)
        if dropped:
            _LOG.debug(
                "discovery filtered",
                extra={"event": "discovery.filtered", "kept": len(kept), "dropped": dropped},
            )
        return kept

    def _host_ok(self, url: str | None) -> bool:
        if not self._hosts:
            return True
        host = urlparse(url).hostname if url else None
        return host is not None and host.lower() in self._hosts


async def build_engine(*, app: str, approved_hosts: frozenset[str]) -> BuilderEngine | None:
    """None when ``LPB_SIGNER_URL`` is unset: the app runs degraded (chat disabled) rather than failing."""
    settings = EngineSettings.from_env()
    if not settings.signer_url and not settings.discovery_url:
        return None
    source = ApprovedChatRunnersOnly(
        SignerDiscoverySource(signer_url=settings.signer_url, discovery_url=settings.discovery_url),
        app=app,
        hosts=approved_hosts,
    )
    engine = await BuilderEngine.from_settings(settings, discovery_source=source)
    _LOG.info(
        "engine built",
        extra={
            "event": "engine.built",
            "allocation_mode": settings.allocation_mode,
            "app": app,
            "hosts": sorted(approved_hosts),
        },
    )
    return engine


def describe_hosts(hosts: Sequence[str]) -> str:
    return ", ".join(sorted(hosts)) or "any"
