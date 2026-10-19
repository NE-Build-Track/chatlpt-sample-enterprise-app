"""An HTTP client over the wired Application (no engine, scripted backend)."""

from collections.abc import AsyncIterator

import httpx
import pytest

from chatlpt.http import create_app
from chatlpt.runtime import Application

HEADERS = {"x-chatlpt": "1"}


@pytest.fixture
async def client(application: Application) -> AsyncIterator[httpx.AsyncClient]:
    api = create_app(application, manage_lifecycle=False)
    transport = httpx.ASGITransport(app=api)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=HEADERS) as http:
        yield http


async def signup(client: httpx.AsyncClient, email: str) -> dict[str, object]:
    response = await client.post(
        "/api/auth/signup", json={"email": email, "password": "correct horse", "display_name": ""}
    )
    assert response.status_code == 201, response.text
    return dict(response.json())
