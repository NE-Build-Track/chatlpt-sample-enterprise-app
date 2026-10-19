"""Sign in with Google (OpenID Connect) and GitHub (OAuth 2.0), D6. The only module importing authlib/httpx.

Both providers return a verified email. Google's comes from its OIDC userinfo endpoint, called with the
access token just obtained over TLS. GitHub has no identity token, so the primary verified email is read
from ``/user/emails``.
"""

from typing import Any

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client

from chatlpt.contracts import OAuthIdentity, OAuthProviderName
from chatlpt.errors import NotAuthenticated

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105  (an endpoint, not a credential)
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
GITHUB_AUTH = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"  # noqa: S105
GITHUB_API = "https://api.github.com"


class _Provider:
    name: OAuthProviderName
    auth_url: str
    token_url: str
    scope: str

    def __init__(
        self, client_id: str, client_secret: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport  # tests inject httpx.MockTransport

    def _http(self, **kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=15, transport=self._transport, **kwargs)

    def _client(self, redirect_uri: str) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            self._client_id, self._client_secret, scope=self.scope, redirect_uri=redirect_uri
        )

    def authorization_url(self, redirect_uri: str, state: str, nonce: str) -> str:
        url, _ = self._client(redirect_uri).create_authorization_url(self.auth_url, state=state, nonce=nonce)
        return str(url)

    async def _token(self, redirect_uri: str, code: str) -> dict[str, Any]:
        async with self._client(redirect_uri) as client:
            token = await client.fetch_token(
                self.token_url, code=code, redirect_uri=redirect_uri, headers={"Accept": "application/json"}
            )
        access = token.get("access_token")
        if not isinstance(access, str) or not access:
            raise NotAuthenticated(f"{self.name} returned no access token")
        return dict(token)


class GoogleProvider(_Provider):
    name: OAuthProviderName = "google"
    auth_url = GOOGLE_AUTH
    token_url = GOOGLE_TOKEN
    scope = "openid email profile"

    async def exchange(self, redirect_uri: str, code: str, nonce: str) -> OAuthIdentity:
        token = await self._token(redirect_uri, code)
        async with self._http() as http:
            response = await http.get(
                GOOGLE_USERINFO, headers={"Authorization": f"Bearer {token['access_token']}"}
            )
        if response.status_code != 200:
            raise NotAuthenticated("google userinfo failed")
        info = response.json()
        if not info.get("email_verified") or not info.get("email") or not info.get("sub"):
            raise NotAuthenticated("google account has no verified email")
        return OAuthIdentity(
            provider="google",
            subject=str(info["sub"]),
            email=str(info["email"]).lower(),
            display_name=str(info.get("name") or ""),
        )


class GitHubProvider(_Provider):
    name: OAuthProviderName = "github"
    auth_url = GITHUB_AUTH
    token_url = GITHUB_TOKEN
    scope = "read:user user:email"

    async def exchange(self, redirect_uri: str, code: str, nonce: str) -> OAuthIdentity:
        token = await self._token(redirect_uri, code)
        headers = {
            "Authorization": f"Bearer {token['access_token']}",
            "Accept": "application/vnd.github+json",
        }
        async with self._http(base_url=GITHUB_API) as http:
            user, emails = (
                await http.get("/user", headers=headers),
                await http.get("/user/emails", headers=headers),
            )
        if user.status_code != 200 or emails.status_code != 200:
            raise NotAuthenticated("github user lookup failed")
        primary = next((e for e in emails.json() if e.get("primary") and e.get("verified")), None)
        if primary is None:
            raise NotAuthenticated("github account has no verified primary email")
        profile = user.json()
        return OAuthIdentity(
            provider="github",
            subject=str(profile["id"]),
            email=str(primary["email"]).lower(),
            display_name=str(profile.get("name") or profile.get("login") or ""),
        )
