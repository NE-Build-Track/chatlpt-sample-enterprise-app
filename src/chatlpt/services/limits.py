"""Attempt limits for login, signup and the claim prompt (D26): a sliding window per key, in memory.

One ChatLPT process serves one deployment, so memory is enough; a restart forgets the counts. Each
attempt names several keys, each with its own limit (the client IP, which a proxy may share among many
people, gets a looser one than the email), and any key over its limit refuses the attempt.
"""

from collections import deque
from datetime import timedelta

from chatlpt.errors import TooManyAttempts
from chatlpt.protocols import Clock


class AttemptLimiter:
    def __init__(self, clock: Clock, *, window: timedelta = timedelta(minutes=1)) -> None:
        self._clock = clock
        self._window = window
        self._hits: dict[str, deque[float]] = {}

    def hit(self, *keys: tuple[str, int]) -> None:
        """Count one attempt under every ``(key, limit)``. Raises TooManyAttempts (429) if any key is full."""
        now = self._clock.now().timestamp()
        horizon = now - self._window.total_seconds()
        waits: list[float] = []
        for key, limit in keys:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= horizon:
                hits.popleft()
            if len(hits) >= limit:
                waits.append(hits[0] - horizon)
        if waits:
            raise TooManyAttempts(
                "too many attempts; wait a minute and try again", retry_after_s=int(max(waits)) + 1
            )
        for key, _ in keys:
            self._hits[key].append(now)
        if len(self._hits) > 10_000:  # forget idle keys so the map cannot grow without bound
            self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > horizon}
