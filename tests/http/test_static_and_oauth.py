"""The static bundle with SPA fallback, the session secret requirement, and the OAuth redirect dance."""

from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from chatlpt.config import Settings
from chatlpt.contracts import OAuthIdentity, OAuthProviderName
from chatlpt.errors import AppError, NotAuthenticated, UnverifiedEmail
from chatlpt.http import create_app
from chatlpt.http.sessions import CLAIM_COOKIE, OAUTH_COOKIE, SESSION_COOKIE
from chatlpt.runtime import Application
from chatlpt.testing import FixedClock, MemoryStore, PlainHasher, StaticPrices


class FakeProvider:
    name: OAuthProviderName = "google"

    def __init__(self) -> None:
        self.exchanged: list[tuple[str, str, str]] = []
        self.identity = OAuthIdentity(
            provider="google", subject="g-1", email="carol@example.com", display_name="Carol"
        )

    def authorization_url(self, redirect_uri: str, state: str, code_verifier: str) -> str:
        return f"https://idp.test/auth?state={state}&redirect_uri={redirect_uri}"

    async def exchange(self, redirect_uri: str, code: str, code_verifier: str) -> OAuthIdentity:
        self.exchanged.append((redirect_uri, code, code_verifier))
        if code == "bad":
            raise NotAuthenticated("bad code")
        if code == "boom":
            raise RuntimeError("provider exploded")
        if code == "unverified":
            raise UnverifiedEmail("no verified email")
        return self.identity


def make_app(static_dir: str, oauth: dict[str, FakeProvider] | None = None) -> Application:
    settings = Settings(
        session_secret=SecretStr("s"), static_dir=static_dir, public_base_url="https://app.test"
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


async def start(client: httpx.AsyncClient, next_url: str = "/") -> str:
    """Begin a sign-in; returns the state the provider would hand back."""
    begun = await client.get("/api/auth/oauth/google/start", params={"next": next_url})
    assert begun.status_code == 302 and OAUTH_COOKIE in begun.cookies
    return begun.headers["location"].split("state=")[1].split("&")[0]


async def callback(client: httpx.AsyncClient, **params: str) -> httpx.Response:
    return await client.get("/api/auth/oauth/google/callback", params=params)


def oauth_client(app: Application) -> httpx.AsyncClient:
    api = create_app(app, manage_lifecycle=False)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://app.test", headers={"x-chatlpt": "1"}
    )


async def test_oauth_start_and_callback_sign_the_user_in() -> None:
    provider = FakeProvider()
    async with oauth_client(make_app("/nonexistent", {"google": provider})) as client:
        assert (await client.get("/api/auth/providers")).json()["providers"] == ["google"]
        state = await start(client, "/c/1")
        done = await callback(client, code="c0de", state=state)
        assert done.status_code == 302 and done.headers["location"] == "/c/1"
        assert SESSION_COOKIE in done.cookies
        redirect_uri, _, verifier = provider.exchanged[0]
        assert redirect_uri == "https://app.test/api/auth/oauth/google/callback" and len(verifier) >= 43
        me = await client.get("/api/auth/me")
        assert me.json()["email"] == "carol@example.com" and me.json()["email_verified"] is True
        again = await callback(client, code="c0de", state=await start(client))  # linked by subject
        assert (
            again.headers["location"] == "/"
            and (await client.get("/api/auth/me")).json()["id"] == me.json()["id"]
        )


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"error": "access_denied"}, "cancelled"),  # the person clicked Cancel at the provider
        ({"error": "server_error"}, "provider_error"),
        ({}, "provider_error"),  # no code
        ({"code": "bad"}, "provider_error"),
        ({"code": "boom"}, "provider_error"),  # an unexpected failure is a message, never a 500
        ({"code": "unverified"}, "unverified_email"),
    ],
)
async def test_every_callback_failure_returns_to_the_login_page(params: dict[str, str], reason: str) -> None:
    async with oauth_client(make_app("/nonexistent", {"google": FakeProvider()})) as client:
        failed = await callback(client, state=await start(client), **params)
        assert failed.status_code == 302 and failed.headers["location"] == f"/login?error={reason}"
        assert SESSION_COOKIE not in failed.cookies


async def test_a_stale_or_forged_state_returns_to_the_login_page() -> None:
    async with oauth_client(make_app("/nonexistent", {"google": FakeProvider()})) as client:
        no_cookie = await callback(client, code="c", state="s")
        assert no_cookie.headers["location"] == "/login?error=expired"
        await start(client)
        forged = await callback(client, code="c", state="someone-elses")
        assert forged.headers["location"] == "/login?error=mismatch"


async def test_disabled_and_closed_signup_failures_say_why() -> None:
    app = make_app("/nonexistent", {"google": FakeProvider()})
    object.__setattr__(app.auth, "_allow_signup", False)
    async with oauth_client(app) as client:
        closed = await callback(client, code="c0de", state=await start(client))
        assert closed.headers["location"] == "/login?error=signup_closed"


@pytest.mark.parametrize(
    "next_url", ["https://evil", "//evil.com", "/\\evil.com", "/\tevil", "\\evil", "evil"]
)
async def test_next_must_stay_on_this_site(next_url: str) -> None:
    async with oauth_client(make_app("/nonexistent", {"google": FakeProvider()})) as client:
        refused = await client.get("/api/auth/oauth/google/start", params={"next": next_url})
        assert refused.status_code == 400, next_url
        assert (await client.get("/api/auth/oauth/github/start")).status_code == 404


async def test_the_claim_prompt_keeps_the_account_with_its_password() -> None:
    app = make_app("/nonexistent", {"google": FakeProvider()})
    async with oauth_client(app) as client:
        mine = (
            await client.post(
                "/api/auth/signup", json={"email": "carol@example.com", "password": "my own pw"}
            )
        ).json()
        await client.post("/api/auth/logout")
        prompt = await callback(client, code="c0de", state=await start(client, "/c/9"))
        assert prompt.headers["location"] == "/claim" and CLAIM_COOKIE in prompt.cookies
        assert SESSION_COOKIE not in prompt.cookies  # nobody is signed in until they choose
        assert (await client.get("/api/auth/claim")).json() == {
            "email": "carol@example.com",
            "provider": "google",
        }
        wrong = await client.post("/api/auth/claim/keep", json={"password": "a guess"})
        assert wrong.status_code == 401
        kept = await client.post("/api/auth/claim/keep", json={"password": "my own pw"})
        assert kept.status_code == 200 and kept.json()["next"] == "/c/9"
        assert kept.json()["user"]["id"] == mine["id"] and kept.json()["user"]["email_verified"] is True
        assert (await client.get("/api/auth/me")).json()["id"] == mine["id"]
        assert (await client.get("/api/auth/claim")).status_code == 401  # the prompt is used up


async def test_the_claim_prompt_can_start_a_new_account_and_retire_the_old_one() -> None:
    app = make_app("/nonexistent", {"google": FakeProvider()})
    async with oauth_client(app) as client:
        squat = (
            await client.post(
                "/api/auth/signup", json={"email": "carol@example.com", "password": "squatters"}
            )
        ).json()
        squatter_cookie = client.cookies.get(SESSION_COOKIE)
        client.cookies.clear()
        await callback(client, code="c0de", state=await start(client))
        fresh = await client.post("/api/auth/claim/new")
        assert fresh.status_code == 200 and fresh.json()["user"]["id"] != squat["id"]
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, squatter_cookie or "")
        assert (await client.get("/api/auth/me")).status_code == 401  # the squatter is out at once
        relogin = await client.post(
            "/api/auth/login", json={"email": "carol@example.com", "password": "squatters"}
        )
        assert relogin.status_code == 401


async def test_login_and_claim_attempts_are_rate_limited() -> None:
    app = make_app("/nonexistent", {"google": FakeProvider()})
    async with oauth_client(app) as client:
        for _ in range(5):
            bad = await client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"})
            assert bad.status_code == 401
        limited = await client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"})
        assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
        other = await client.post("/api/auth/login", json={"email": "y@example.com", "password": "nope"})
        assert other.status_code == 401  # another email still gets its own five
        app.clock.advance(minutes=2)  # type: ignore[attr-defined]
        again = await client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"})
        assert again.status_code == 401


def test_sign_in_needs_a_public_url_the_providers_can_return_to(caplog: pytest.LogCaptureFixture) -> None:
    for bad in ("http://chat.example.com", "ftp://x", "not a url"):
        app = make_app("/nonexistent", {"google": FakeProvider()})
        object.__setattr__(app, "settings", app.settings.model_copy(update={"public_base_url": bad}))
        with pytest.raises(AppError, match="CHATLPT_PUBLIC_BASE_URL"):
            create_app(app, manage_lifecycle=False)
    with caplog.at_level("INFO"):
        app = make_app("/nonexistent", {"google": FakeProvider()})
        object.__setattr__(
            app, "settings", app.settings.model_copy(update={"public_base_url": "https://chat.example.com"})
        )
        create_app(app, manage_lifecycle=False)
    logged = next(r for r in caplog.records if getattr(r, "event", None) == "auth.oauth_redirects")
    assert logged.redirect_uris == ["https://chat.example.com/api/auth/oauth/google/callback"]  # type: ignore[attr-defined]
    create_app(make_app("/nonexistent"), manage_lifecycle=False)  # no providers: any URL is fine


async def test_garbage_session_cookie_is_ignored() -> None:
    api = create_app(make_app("/nonexistent"), manage_lifecycle=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://t") as client:
        client.cookies.set(SESSION_COOKIE, "not-a-token")
        assert (await client.get("/api/auth/me")).status_code == 401
