"""Our discovery filter over the engine's own source: our app on approved hosts reaches the engine, and
runner metadata is remembered (D8, D14)."""

import json

import pytest
from livepeer_builder import Runner
from livepeer_builder.testing import runner

from chatlpt.adapters.discovery import FilteredDiscovery
from chatlpt.testing import FixedClock

APP = "blueclaw/chat/qwen3.8-27b"
META = json.dumps({"blueclaw": 1, "model_id": "Qwen3.8-27B", "max_context": 131072})
SMALLER = json.dumps({"model_id": "Qwen3.8-27B", "max_context": 40960})


def chat(orchestrator: str | None, metadata: str | None = META, app: str = APP) -> Runner:
    return runner(app, url=f"{orchestrator}/runner", orchestrator_url=orchestrator, metadata=metadata)


class Listed:
    """The engine's configured discovery source, as the decorator sees it."""

    def __init__(self, *runners: Runner) -> None:
        self.runners = list(runners)

    async def fetch(self) -> tuple[Runner, ...]:
        return tuple(self.runners)


def filtered(inner: Listed, hosts: frozenset[str]) -> FilteredDiscovery:
    return FilteredDiscovery(inner, apps=frozenset({APP}), hosts=hosts, clock=FixedClock())


async def test_filter_keeps_only_the_chat_app_on_approved_hosts_and_remembers_metadata() -> None:
    inner = Listed(
        chat("https://us-central-metrics.speedybird.xyz:28935"),
        chat("https://us-central-metrics.speedybird.xyz:28935", app="comfystream/fal-flux-schnell"),
        chat("https://evil.example:8935"),
        chat("https://hky.eliteencoder.net:8936", app="other/app"),
        chat(None),
    )
    discovery = filtered(inner, frozenset({"us-central-metrics.speedybird.xyz", "hky.eliteencoder.net"}))
    runners = await discovery.fetch()
    assert [(r.app, r.orchestrator_url) for r in runners] == [
        (APP, "https://us-central-metrics.speedybird.xyz:28935")
    ]
    assert runners[0] == inner.runners[0]  # passed through untouched: capacity, rate and all
    model = discovery.model_from_discovery(APP)
    assert model is not None and model.max_model_len == 131072 and model.model_id == "Qwen3.8-27B"
    assert discovery.model_from_discovery("other/app") is None


async def test_empty_host_list_means_any_host_and_bad_metadata_is_ignored() -> None:
    inner = Listed(
        chat("https://anyone.example", metadata="not json"),
        chat("https://anyone.example", metadata=json.dumps({"max_context": "big"})),
    )
    discovery = filtered(inner, frozenset())
    assert len(await discovery.fetch()) == 2
    assert discovery.model_from_discovery(APP) is None
    inner.runners.append(chat("https://two.example", metadata=None))
    assert len(await discovery.fetch()) == 3


async def test_the_smallest_advertised_window_wins_across_approved_runners() -> None:
    inner = Listed(
        chat("https://orch-us-central.xodeapp.xyz:18935"),
        chat("https://us-central-metrics.speedybird.xyz:28935", metadata=SMALLER),
        chat("https://evil.example:8935", metadata=json.dumps({"max_context": 8})),  # dropped host
    )
    discovery = filtered(
        inner, frozenset({"orch-us-central.xodeapp.xyz", "us-central-metrics.speedybird.xyz"})
    )
    assert len(await discovery.fetch()) == 2
    model = discovery.model_from_discovery(APP)
    assert model is not None and model.max_model_len == 40960  # the engine may route to either runner


async def test_a_failing_default_source_fails_the_fetch() -> None:
    class Down:
        async def fetch(self) -> tuple[Runner, ...]:
            raise ConnectionError("signer down")

    discovery = FilteredDiscovery(Down(), apps=frozenset({APP}), hosts=frozenset(), clock=FixedClock())
    with pytest.raises(ConnectionError):  # the engine keeps its last good snapshot and reports the error
        await discovery.fetch()
