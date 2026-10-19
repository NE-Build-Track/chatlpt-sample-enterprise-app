"""Google and GitHub providers: the authorization URL, and the identity each one derives after the exchange."""

from typing import Any

import httpx
import pytest

from chatlpt.adapters import oauth
from chatlpt.adapters.oauth import GitHubProvider, GoogleProvider
from chatlpt.errors import NotAuthenticated

REDIRECT = "http://localhost:3050/api/auth/oauth/google/callback"


def test_authorization_url_carries_state_nonce_scope_and_redirect() -> None:
    url = GoogleProvider("cid", "secret").authorization_url(REDIRECT, "st4te", "n0nce")
    assert url.startswith(oauth.GOOGLE_AUTH)
    assert "state=st4te" in url and "nonce=n0nce" in url and "client_id=cid" in url
    assert "scope=openid+email+profile" in url and "redirect_uri=http%3A%2F%2Flocalhost%3A3050" in url
    github = GitHubProvider("cid", "secret").authorization_url(REDIRECT, "s", "n")
    assert github.startswith(oauth.GITHUB_AUTH) and "scope=read%3Auser+user%3Aemail" in github


async def _patch_token(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_token(self: Any, redirect_uri: str, code: str) -> dict[str, Any]:
        assert code == "c0de"
        return {"access_token": "tok", "token_type": "bearer"}

    monkeypatch.setattr(oauth._Provider, "_token", fake_token)


async def test_google_identity_comes_from_userinfo(monkeypatch: pytest.MonkeyPatch) -> None:
    await _patch_token(monkeypatch)
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(
            200, json={"sub": "g-1", "email": "Carol@Example.com", "email_verified": True, "name": "Carol"}
        )

    provider = GoogleProvider("cid", "secret", transport=httpx.MockTransport(handler))
    identity = await provider.exchange(REDIRECT, "c0de", "n")
    assert identity.provider == "google" and identity.subject == "g-1"
    assert identity.email == "carol@example.com" and identity.display_name == "Carol"
    assert seen["auth"] == "Bearer tok"


async def test_google_rejects_unverified_email(monkeypatch: pytest.MonkeyPatch) -> None:
    await _patch_token(monkeypatch)
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"sub": "g-1", "email": "x@y", "email_verified": False})
    )
    with pytest.raises(NotAuthenticated):
        await GoogleProvider("cid", "secret", transport=transport).exchange(REDIRECT, "c0de", "n")
    failing = httpx.MockTransport(lambda _: httpx.Response(500))
    with pytest.raises(NotAuthenticated):
        await GoogleProvider("cid", "secret", transport=failing).exchange(REDIRECT, "c0de", "n")


async def test_github_identity_uses_the_primary_verified_email(monkeypatch: pytest.MonkeyPatch) -> None:
    await _patch_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 42, "login": "dave", "name": None})
        return httpx.Response(
            200,
            json=[
                {"email": "old@example.com", "primary": False, "verified": True},
                {"email": "Dave@Example.com", "primary": True, "verified": True},
            ],
        )

    identity = await GitHubProvider("cid", "secret", transport=httpx.MockTransport(handler)).exchange(
        REDIRECT, "c0de", "n"
    )
    assert identity.provider == "github" and identity.subject == "42"
    assert identity.email == "dave@example.com" and identity.display_name == "dave"


async def test_github_without_a_verified_primary_email_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    await _patch_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 1, "login": "x"})
        return httpx.Response(200, json=[{"email": "a@b", "primary": True, "verified": False}])

    with pytest.raises(NotAuthenticated):
        await GitHubProvider("cid", "secret", transport=httpx.MockTransport(handler)).exchange(
            REDIRECT, "c0de", "n"
        )
    with pytest.raises(NotAuthenticated):
        await GitHubProvider(
            "cid", "secret", transport=httpx.MockTransport(lambda _: httpx.Response(401))
        ).exchange(REDIRECT, "c0de", "n")


async def test_missing_access_token_is_refused() -> None:
    class NoToken(GoogleProvider):
        def _client(self, redirect_uri: str) -> Any:
            class _Client:
                async def __aenter__(self) -> "_Client":
                    return self

                async def __aexit__(self, *args: object) -> None:
                    return None

                async def fetch_token(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
                    return {"token_type": "bearer"}

            return _Client()

    with pytest.raises(NotAuthenticated):
        await NoToken("cid", "secret").exchange(REDIRECT, "c0de", "n")
