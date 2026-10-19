"""An incremental server-sent-events decoder for OpenAI-style chat completion streams.

Feed it bytes as they arrive; it yields the JSON objects of complete ``data:`` frames and tells you
when the ``[DONE]`` sentinel passed. No third-party code: the format is three rules long.
"""

import json
from typing import Any


class SseDecoder:
    def __init__(self) -> None:
        self._buffer = b""
        self.done = False

    def feed(self, chunk: bytes) -> list[dict[str, Any]]:
        """Return the complete events in ``chunk`` plus whatever was buffered before it."""
        self._buffer += chunk
        events: list[dict[str, Any]] = []
        while True:
            index = self._buffer.find(b"\n\n")
            if index < 0:
                break
            frame, self._buffer = self._buffer[:index], self._buffer[index + 2 :]
            event = self._parse(frame)
            if event is not None:
                events.append(event)
        return events

    def flush(self) -> list[dict[str, Any]]:
        """Decode a final frame that arrived without its trailing blank line."""
        frame, self._buffer = self._buffer, b""
        event = self._parse(frame) if frame.strip() else None
        return [event] if event is not None else []

    def _parse(self, frame: bytes) -> dict[str, Any] | None:
        data_lines = [
            line[5:].lstrip()
            for line in frame.replace(b"\r\n", b"\n").split(b"\n")
            if line.startswith(b"data:")
        ]
        if not data_lines:
            return None
        payload = b"\n".join(data_lines).strip()
        if payload == b"[DONE]":
            self.done = True
            return None
        try:
            parsed = json.loads(payload)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
