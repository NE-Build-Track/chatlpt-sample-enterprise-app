"""Our discovery source: our app on approved hosts reaches the engine, and runner metadata is remembered (D8, D14)."""

import json
from typing import Any

from chatlpt.adapters.discovery import FilteredSignerDiscovery
from chatlpt.testing import FixedClock

APP = "blueclaw/chat/qwen3.8-27b"
META = json.dumps({"blueclaw": 1, "model_id": "Qwen3.8-27B", "max_context": 131072})


def entry(address: str, *runners: dict[str, Any]) -> dict[str, Any]:
    return {"address": address, "runners": list(runners)}


def runner(app: str, metadata: str | None = META) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "url": f"{app}-url",
        "app": app,
        "mode": "single-shot",
        "capacity": 8,
        "session_ids": [],
        "price_info": {"price": 4634466808, "currency": "wei", "unit": "seconds"},
    }
    if metadata is not None:
        raw["metadata"] = metadata
    return raw


def source(
    entries: list[dict[str, Any]], hosts: frozenset[str]
) -> tuple[FilteredSignerDiscovery, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    async def discover(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return entries

    return FilteredSignerDiscovery(
        signer_url="http://signer",
        discovery_url=None,
        app=APP,
        hosts=hosts,
        clock=FixedClock(),
        discover=discover,
    ), calls


async def test_filter_keeps_only_the_chat_app_on_approved_hosts_and_remembers_metadata() -> None:
    entries = [
        entry(
            "https://us-central-metrics.speedybird.xyz:28935",
            runner(APP),
            runner("comfystream/fal-flux-schnell"),
        ),
        entry("https://evil.example:8935", runner(APP)),
        entry("https://hky.eliteencoder.net:8936", runner("other/app")),
        {"address": None, "runners": [runner(APP)]},
        "garbage",
    ]
    discovery, calls = source(
        entries, frozenset({"us-central-metrics.speedybird.xyz", "hky.eliteencoder.net"})
    )
    runners = await discovery.fetch()
    assert [(r.app, r.orchestrator_url) for r in runners] == [
        (APP, "https://us-central-metrics.speedybird.xyz:28935")
    ]
    assert (
        runners[0].capacity_available == 8
        and runners[0].rate is not None
        and runners[0].rate.unit == "seconds"
    )
    assert calls[0]["app"] == [APP] and calls[0]["signer_url"] == "http://signer"
    model = discovery.model_from_discovery(APP)
    assert model is not None and model.max_model_len == 131072 and model.model_id == "Qwen3.8-27B"
    assert discovery.model_from_discovery("other/app") is None


async def test_empty_host_list_means_any_host_and_bad_metadata_is_ignored() -> None:
    entries = [
        entry(
            "https://anyone.example",
            runner(APP, metadata="not json"),
            runner(APP, metadata=json.dumps({"max_context": "big"})),
        )
    ]
    discovery, _ = source(entries, frozenset())
    assert len(await discovery.fetch()) == 2
    assert discovery.model_from_discovery(APP) is None
    entries.append(entry("https://two.example", runner(APP, metadata=None)))
    assert len(await discovery.fetch()) == 3
