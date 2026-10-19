"""Generated images on disk: fetched once from the runner's temporary URL, kept under ``images_dir`` (D25).

The only module besides ``oauth.py`` that imports httpx. Files are named by image id; the directory
is the app's volume in Docker and ``.local/images`` in development.
"""

from pathlib import Path
from uuid import UUID

import httpx

from chatlpt.errors import ReplyFailed

_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_BYTES = 25 * 1024 * 1024


class LocalImageFiles:
    def __init__(self, root: Path, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._root = root
        self._transport = transport  # tests inject httpx.MockTransport
        root.mkdir(parents=True, exist_ok=True)

    async def fetch(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True, transport=self._transport) as http:
            response = await http.get(url)
        if response.status_code != 200:
            raise ReplyFailed(
                f"the image could not be fetched (HTTP {response.status_code})", payment_sent=True
            )
        if len(response.content) > _MAX_BYTES:
            raise ReplyFailed("the image is larger than the 25 MB limit", payment_sent=True)
        return response.content

    def save(self, image_id: UUID, content_type: str, data: bytes) -> str:
        relative = f"{image_id}.{_EXTENSIONS.get(content_type, 'bin')}"
        target = self._root / relative
        target.write_bytes(data)
        return relative

    def path(self, relative: str) -> str:
        target = (self._root / relative).resolve()
        if self._root.resolve() not in target.parents:
            raise ReplyFailed("image path outside the images directory", payment_sent=False)
        return str(target)

    def delete(self, relative: str) -> None:
        target = self._root / relative
        if target.exists():
            target.unlink()
