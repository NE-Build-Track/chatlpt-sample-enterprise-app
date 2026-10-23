"""Build the embedded BuilderEngine from ``LPB_*`` settings, its discovery filtered for ChatLPT (D8, D14)."""

import dataclasses
import logging

from livepeer_builder import BuilderEngine, EngineParts, EngineSettings

from chatlpt.adapters.discovery import FilteredDiscovery
from chatlpt.protocols import Clock

_LOG = logging.getLogger(__name__)


async def build_engine(
    *, apps: frozenset[str], approved_hosts: frozenset[str], clock: Clock
) -> tuple[BuilderEngine, FilteredDiscovery] | None:
    """None when ``LPB_SIGNER_URL`` is unset: the app runs degraded (chat disabled) rather than failing."""
    settings = EngineSettings.from_env()
    if not settings.signer_url and not settings.discovery_url:
        return None
    filters: list[FilteredDiscovery] = []

    def filter_discovery(parts: EngineParts) -> EngineParts:
        """Decorate the engine's configured source; it keeps the signer header and discovery URL."""
        filtered = FilteredDiscovery(parts.discovery_source, apps=apps, hosts=approved_hosts, clock=clock)
        filters.append(filtered)
        return dataclasses.replace(parts, discovery_source=filtered)

    engine = await BuilderEngine.create(settings, decorate=filter_discovery)
    _LOG.info(
        "engine built",
        extra={
            "event": "engine.built",
            "allocation_mode": settings.allocation_mode,
            "apps": sorted(apps),
            "hosts": sorted(approved_hosts),
        },
    )
    return engine, filters[0]
