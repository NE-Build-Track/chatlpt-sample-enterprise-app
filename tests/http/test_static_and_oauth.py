"""The static bundle with SPA fallback, the session secret requirement, and the OAuth redirect dance."""

from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from chatlpt.config import Settings
from chatlpt.contracts import OAuthIdentity, OAuthProviderName
from chatlpt.errors import AppError, NotAuthenticated
from chatlpt.http import create_app
from chatlpt.http.sessions import OAUTH_COOKIE, SESSION_COOKIE
from chatlpt.runtime import Application
from chatlpt.testing import FixedClock, MemoryStore, PlainHasher, StaticPrices


class FakeProvider:
    name: OAuthProviderName = "google"

    def __init__(self) -> None:
        self.exchanged: list[tuple[str, str, str]] = []
        self.identity = OAuthIdentity(
            provider="google", subject="g-1", email="carol@example.com", display_name="Carol"
        )

    def authorization_url(self, redirect_uri: str, state: str, nonce: str) -> str:
        return f"https://idp.test/auth?state={state}&redirect_uri={redirect_uri}"

    async def exchange(self, redirect_uri: str, code: str, nonce: str) -> OAuthIdentity:
        self.exchanged.append((redirect_uri, code, nonce))
        if code == "bad":
            raise NotAuthenticated("bad code")
        return self.identity


def make_app(static_dir: str, oauth: dict[str, FakeProvider] | None = None) -> Application:
    settings = Settings(
        session_secret=SecretStr("s"), static_dir=static_dir, public_base_url="http://app.test"
    )
    return Application(
        settings,
        store=MemoryStore(),
        backend=None,
        clock=FixedClock(),
        hasher=PlainHasher(),
        prices=StaticPrices(),
        oauth=dict(oauth or {}),  # type: ignore[arg-type]
    )


def test_create_app_requires_a_session_secret() -> None:
    app = make_app("/nonexistent")
    object.__setattr__(app, "settings", app.settings.model_copy(update={"session_secret": None}))
    with pytest.raises(AppError, match="CHATLPT_SESSION_SECRET"):
        create_app(app, manage_lifecycle=False)


async def test_static_bundle_is_served_with_spa_fallback(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "a.js").write_text("js")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    api = create_app(make_app(str(tmp_path)), manage_lifecycle=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://t") as client:
        assert (await client.get("/")).text == "<html>app</html>"
        shell = await client.get("/c/123")
        assert shell.text == "<html>app</html>" and shell.headers["cache-control"] == "no-cache"
        assert (await client.get("/favicon.svg")).text == "<svg/>"
        assert (await client.get("/assets/a.js")).text == "js"
        assert (await client.get("/../etc/passwd")).text == "<html>app</html>"
        assert (await client.get("/healthz")).json() == {"status": "ok"}


async def test_oauth_start_and_callback_sign_the_user_in() -> None:
    provider = FakeProvider()
    api = create_app(make_app("/nonexistent", {"google": provider}), manage_lifecycle=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://app.test"
    ) as client:
        assert (await client.get("/api/auth/providers")).json()["providers"] == ["google"]
        start = await client.get("/api/auth/oauth/google/start", params={"next": "/c/1"})
        assert start.status_code == 302 and start.headers["location"].startswith(
            "https://idp.test/auth?state="
        )
        state = start.headers["location"].split("state=")[1].split("&")[0]
        assert OAUTH_COOKIE in start.cookies
        bad_state = await client.get(
            "/api/auth/oauth/google/callback", params={"code": "c", "state": "other"}
        )
        assert bad_state.status_code == 401
        start = await client.get("/api/auth/oauth/google/start", params={"next": "/c/1"})
        state = start.headers["location"].split("state=")[1].split("&")[0]
        done = await client.get("/api/auth/oauth/google/callback", params={"code": "c0de", "state": state})
        assert done.status_code == 302 and done.headers["location"] == "/c/1"
        assert SESSION_COOKIE in done.cookies
        assert provider.exchanged[0][0] == "http://app.test/api/auth/oauth/google/callback"
        me = await client.get("/api/auth/me")
        assert me.json()["email"] == "carol@example.com" and me.json()["display_name"] == "Carol"
        # second sign-in links by subject and reuses the account
        start = await client.get("/api/auth/oauth/google/start")
        state = start.headers["location"].split("state=")[1].split("&")[0]
        again = await client.get("/api/auth/oauth/google/callback", params={"code": "c0de", "state": state})
        assert again.headers["location"] == "/"
        assert len({r["id"] for r in [me.json(), (await client.get("/api/auth/me")).json()]}) == 1


async def test_oauth_rejects_bad_next_missing_code_and_unknown_provider() -> None:
    api = create_app(make_app("/nonexistent", {"google": FakeProvider()}), manage_lifecycle=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://app.test"
    ) as client:
        assert (
            await client.get("/api/auth/oauth/google/start", params={"next": "https://evil"})
        ).status_code == 400
        assert (await client.get("/api/auth/oauth/github/start")).status_code == 404
        assert (
            await client.get("/api/auth/oauth/google/callback", params={"code": "c", "state": "s"})
        ).status_code == 401
        start = await client.get("/api/auth/oauth/google/start")
        state = start.headers["location"].split("state=")[1].split("&")[0]
        assert (
            await client.get("/api/auth/oauth/google/callback", params={"state": state})
        ).status_code == 400
        start = await client.get("/api/auth/oauth/google/start")
        state = start.headers["location"].split("state=")[1].split("&")[0]
        assert (
            await client.get("/api/auth/oauth/google/callback", params={"code": "bad", "state": state})
        ).status_code == 401


async def test_garbage_session_cookie_is_ignored() -> None:
    api = create_app(make_app("/nonexistent"), manage_lifecycle=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://t") as client:
        client.cookies.set(SESSION_COOKIE, "not-a-token")
        assert (await client.get("/api/auth/me")).status_code == 401
