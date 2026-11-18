"""Build the embedded BuilderEngine from its settings, its discovery filtered for ChatLPT (D8, D14)."""

import dataclasses
import logging

from livepeer_builder import BuilderEngine, EngineParts, EngineSettings
from pydantic import ValidationError

from chatlpt.adapters.discovery import FilteredDiscovery
from chatlpt.protocols import Clock

_LOG = logging.getLogger(__name__)


def engine_settings_from_env() -> EngineSettings | None:
    """The embedded engine's settings from ``LPB_*`` variables, for the CLI's composition root.

    None when ``LPB_DISCOVERY_URL`` is unset and every other setting is valid. The engine requires that
    URL (builder-core D63); without it ChatLPT runs without an engine, as it does without a signer. Any
    other invalid setting still raises.
    """
    try:
        return EngineSettings.from_env()
    except ValidationError as error:
        if [(e["type"], e["loc"]) for e in error.errors()] == [("missing", ("discovery_url",))]:
            return None
        raise


async def build_engine(
    settings: EngineSettings | None,
    *,
    apps: frozenset[str],
    approved_hosts: frozenset[str],
    clock: Clock,
) -> tuple[BuilderEngine, FilteredDiscovery] | None:
    """None without both a discovery URL (runners; no ``EngineSettings`` without one) and a signer
    (payment): the app runs degraded (chat disabled) rather than failing. The signer only signs; runners
    come from livepeer/node's discovery at ``LPB_DISCOVERY_URL`` (builder-core D63)."""
    if settings is None or not settings.signer_url:
        return None
    filters: list[FilteredDiscovery] = []

    def filter_discovery(parts: EngineParts) -> EngineParts:
        """Decorate the engine's configured source (``LPB_DISCOVERY_URL``), never re-create it."""
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
