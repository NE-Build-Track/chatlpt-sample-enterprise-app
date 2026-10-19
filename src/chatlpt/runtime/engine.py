"""Build the embedded BuilderEngine from ``LPB_*`` settings with ChatLPT's filtered discovery (D8, D14)."""

import logging

from livepeer_builder import BuilderEngine, EngineSettings

from chatlpt.adapters.discovery import FilteredSignerDiscovery
from chatlpt.protocols import Clock

_LOG = logging.getLogger(__name__)


async def build_engine(
    *, apps: frozenset[str], approved_hosts: frozenset[str], clock: Clock
) -> tuple[BuilderEngine, FilteredSignerDiscovery] | None:
    """None when ``LPB_SIGNER_URL`` is unset: the app runs degraded (chat disabled) rather than failing."""
    settings = EngineSettings.from_env()
    if not settings.signer_url and not settings.discovery_url:
        return None
    source = FilteredSignerDiscovery(
        signer_url=settings.signer_url,
        discovery_url=settings.discovery_url,
        apps=apps,
        hosts=approved_hosts,
        clock=clock,
    )
    engine = await BuilderEngine.from_settings(settings, discovery_source=source)
    _LOG.info(
        "engine built",
        extra={
            "event": "engine.built",
            "allocation_mode": settings.allocation_mode,
            "apps": sorted(apps),
            "hosts": sorted(approved_hosts),
        },
    )
    return engine, source
