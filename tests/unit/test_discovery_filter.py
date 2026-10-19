"""Only runners advertising our app on approved orchestrators reach the engine (D8)."""

from livepeer_builder import Runner

from chatlpt.runtime.engine import ApprovedChatRunnersOnly

APP = "blueclaw/chat/qwen3.8-27b"


class _Source:
    def __init__(self, runners: list[Runner]) -> None:
        self._runners = runners

    async def fetch(self) -> tuple[Runner, ...]:
        return tuple(self._runners)


def runner(app: str, orchestrator: str | None) -> Runner:
    return Runner(
        url="https://r",
        app=app,
        runner_id=None,
        mode="single-shot",
        orchestrator_url=orchestrator,
        capacity=1,
        capacity_available=1,
        rate=None,
    )


async def test_filter_keeps_only_the_chat_app_on_approved_hosts() -> None:
    runners = [
        runner(APP, "https://us-central-metrics.speedybird.xyz:28935"),
        runner(APP, "https://evil.example:8935"),
        runner("comfystream/fal-flux-schnell", "https://us-central-metrics.speedybird.xyz:28935"),
        runner(APP, None),
    ]
    source = ApprovedChatRunnersOnly(
        _Source(runners), app=APP, hosts=frozenset({"us-central-metrics.speedybird.xyz"})
    )
    assert await source.fetch() == (runners[0],)


async def test_empty_host_list_means_any_host() -> None:
    runners = [runner(APP, "https://anyone.example")]
    assert await ApprovedChatRunnersOnly(_Source(runners), app=APP, hosts=frozenset()).fetch() == tuple(
        runners
    )
