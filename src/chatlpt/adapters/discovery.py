"""ChatLPT's discovery filter, a decorator over the engine's configured source (D8, D14).

The engine builds its default ``DiscoverySource`` from ``LPB_*`` settings (the signer, or
``LPB_DISCOVERY_URL``, with the signer header). This wraps that source: only our apps on approved
orchestrators reach the engine (D8), and each runner's ``metadata`` is read as the model's own
statement of its context window (D14), kept for ``ContextService``. The BlueClaw chat runner publishes
``{"model_id": ..., "max_context": ...}`` there.
"""

import json
import logging
from urllib.parse import urlparse

from livepeer_builder import Runner
from livepeer_builder.protocols import DiscoverySource

from chatlpt.contracts import ModelInfo
from chatlpt.protocols import Clock

_LOG = logging.getLogger(__name__)


class FilteredDiscovery:
    def __init__(
        self, inner: DiscoverySource, *, apps: frozenset[str], hosts: frozenset[str], clock: Clock
    ) -> None:
        self._inner = inner
        self._apps = apps
        self._hosts = hosts
        self._clock = clock
        self._models: dict[str, ModelInfo] = {}

    async def fetch(self) -> tuple[Runner, ...]:
        """The inner source's runners for our apps on approved hosts. Its errors propagate: the engine
        keeps its last good snapshot and reports the error in health."""
        ours = [runner for runner in await self._inner.fetch() if runner.app in self._apps]
        kept = [runner for runner in ours if self._host_ok(runner.orchestrator_url)]
        advertised: dict[str, list[ModelInfo]] = {}
        for runner in kept:
            info = self._parse(runner.app, runner.metadata)
            if info is not None:
                advertised.setdefault(info.app, []).append(info)
        for app, infos in advertised.items():
            # Orchestrators advertise different limits for the same app (19 October: 40960 vs 131072). The
            # engine may pick any of them, so the smallest window is the one every reply fits in.
            self._models[app] = min(infos, key=lambda m: m.max_model_len)
        if len(kept) < len(ours):
            _LOG.debug(
                "discovery filtered", extra={"event": "discovery.filtered", "dropped": len(ours) - len(kept)}
            )
        return tuple(kept)

    def model_from_discovery(self, app: str) -> ModelInfo | None:
        return self._models.get(app)

    def _host_ok(self, url: str | None) -> bool:
        if not self._hosts:
            return True
        host = urlparse(url).hostname if url else None
        return host is not None and host.lower() in self._hosts

    def _parse(self, app: str, metadata: str | None) -> ModelInfo | None:
        if not metadata:
            return None
        try:
            parsed = json.loads(metadata)
        except ValueError:
            return None
        if not isinstance(parsed, dict):
            return None
        max_context = parsed.get("max_context")
        if not isinstance(max_context, int) or max_context <= 0:
            return None
        model_id = parsed.get("model_id")
        return ModelInfo(
            app=app,
            model_id=str(model_id) if model_id else "unknown",
            max_model_len=max_context,
            observed_at=self._clock.now(),
        )
