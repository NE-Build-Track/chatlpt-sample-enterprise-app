"""ChatLPT's DiscoverySource for the engine: our app on approved hosts (D8), plus runner metadata (D14).

The signer's discovery entries carry an app-controlled ``metadata`` string. The BlueClaw chat runner
publishes ``{"model_id": ..., "max_context": ...}`` in it, which is the model's own statement of its
context window, free of charge. builder-core's ``Runner`` contract drops that field, so this source
reads the raw entries itself, hands the engine the same ``Runner`` contracts the default source would,
and keeps the metadata for ``ContextService``. The only module importing ``livepeer_gateway``.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from livepeer_builder import Runner
from livepeer_builder.adapters.sdk import runners_from_entries
from livepeer_gateway.discovery import discover_runners

from chatlpt.contracts import ModelInfo
from chatlpt.protocols import Clock

_LOG = logging.getLogger(__name__)
Discover = Callable[..., Awaitable[list[dict[str, Any]]]]


class FilteredSignerDiscovery:
    def __init__(
        self,
        *,
        signer_url: str | None,
        discovery_url: str | None,
        app: str,
        hosts: frozenset[str],
        clock: Clock,
        discover: Discover = discover_runners,
    ) -> None:
        self._signer_url = signer_url
        self._discovery_url = discovery_url
        self._app = app
        self._hosts = hosts
        self._clock = clock
        self._discover = discover
        self._model: ModelInfo | None = None

    async def fetch(self) -> tuple[Runner, ...]:
        entries = await self._discover(
            signer_url=self._signer_url, discovery_url=self._discovery_url, app=[self._app]
        )
        kept: list[dict[str, Any]] = []
        dropped = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw_runners = entry.get("runners") or ()
            runners = [r for r in raw_runners if isinstance(r, dict) and r.get("app") == self._app]
            if not runners or not self._host_ok(entry.get("address")):
                dropped += len(runners) if runners else 0
                continue
            kept.append({**entry, "runners": runners})
            for runner in runners:
                self._remember(runner.get("metadata"))
        if dropped:
            _LOG.debug("discovery filtered", extra={"event": "discovery.filtered", "dropped": dropped})
        return tuple(runners_from_entries(kept))

    def model_from_discovery(self, app: str) -> ModelInfo | None:
        return self._model if app == self._app else None

    def _host_ok(self, url: object) -> bool:
        if not self._hosts:
            return True
        host = urlparse(url).hostname if isinstance(url, str) else None
        return host is not None and host.lower() in self._hosts

    def _remember(self, metadata: object) -> None:
        if not isinstance(metadata, str) or not metadata:
            return
        try:
            parsed = json.loads(metadata)
        except ValueError:
            return
        if not isinstance(parsed, dict):
            return
        max_context = parsed.get("max_context")
        if not isinstance(max_context, int) or max_context <= 0:
            return
        model_id = parsed.get("model_id")
        self._model = ModelInfo(
            app=self._app,
            model_id=str(model_id) if model_id else "unknown",
            max_model_len=max_context,
            observed_at=self._clock.now(),
        )
