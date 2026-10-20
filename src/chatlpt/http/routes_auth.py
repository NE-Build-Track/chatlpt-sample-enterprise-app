"""Account routes: signup, login, logout, me, the OAuth redirect dance and the claim prompt (D5, D6, D26).

An OAuth callback never shows an error page: every failure sends the person to ``/login?error=<reason>``
with the cause in the log. When a provider proves an email that an unverified password account uses,
the callback sends them to ``/claim`` to keep that account (its password) or start a new one.
"""

import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from chatlpt.contracts import ClaimNeeded, Login, NewUser, User
from chatlpt.errors import (
    AccountDisabled,
    InvalidRequest,
    NotAuthenticated,
    NotFound,
    SignupClosed,
    UnverifiedEmail,
)
from chatlpt.http.sessions import CLAIM_COOKIE, OAUTH_COOKIE, Sessions, csrf_guard
from chatlpt.runtime import Application

_LOG = logging.getLogger(__name__)
IP_LIMIT = 20  # per minute; looser, because a proxy can put many people behind one address
EMAIL_LIMIT = 5  # per minute (D26)


class ProvidersOut(BaseModel):
    providers: list[str]
    allow_signup: bool


class ClaimOut(BaseModel):
    email: str
    provider: str


class KeepAccount(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class SignedIn(BaseModel):
    user: User
    next: str


def local_path(value: str) -> str | None:
    """``value`` when it is a path on this site, else None. Browsers read ``\\`` as ``/`` and drop tabs
    and newlines, so ``/\\evil.com`` and ``/\\t/evil.com`` both mean ``//evil.com``: another site."""
    if not value.startswith("/") or any(ord(ch) < 0x20 or ch == "\x7f" for ch in value):
        return None
    candidate = value.replace("\\", "/")
    parts = urlsplit(candidate)
    if parts.scheme or parts.netloc or not candidate.startswith("/") or candidate.startswith("//"):
        return None
    return candidate


def auth_router(
    app: Application, sessions: Sessions, current_user: Callable[[Request], Awaitable[User]]
) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(csrf_guard)])
    Current = Annotated[User, Depends(current_user)]

    def limit(request: Request, email: str | None = None) -> None:
        keys = [(f"ip:{client_ip(request)}", IP_LIMIT)]
        if email:
            keys.append((f"email:{email.lower()}", EMAIL_LIMIT))
        app.attempts.hit(*keys)

    def client_ip(request: Request) -> str:
        if app.settings.trust_forwarded_for:
            forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            if forwarded:
                return forwarded
        return request.client.host if request.client else "unknown"

    @router.get("/providers", response_model=ProvidersOut)
    async def providers() -> ProvidersOut:
        return ProvidersOut(providers=sorted(app.oauth), allow_signup=app.settings.allow_signup)

    @router.post("/signup", response_model=User, status_code=201)
    async def signup(body: NewUser, request: Request, response: Response) -> User:
        limit(request, body.email)
        user = await app.auth.signup(body)
        sessions.issue(response, user.id)
        return user

    @router.post("/login", response_model=User)
    async def login(body: Login, request: Request, response: Response) -> User:
        limit(request, body.email)
        user = await app.auth.login(body)
        sessions.issue(response, user.id)
        return user

    @router.post("/logout", status_code=204)
    async def logout(response: Response) -> Response:
        sessions.clear(response)
        response.status_code = 204
        return response

    @router.get("/me", response_model=User)
    async def me(user: Current) -> User:
        return user

    @router.get("/oauth/{provider}/start", include_in_schema=False)
    async def oauth_start(provider: str, next: str = "/") -> RedirectResponse:
        oauth = app.oauth.get(provider)
        if oauth is None:
            raise NotFound(f"sign-in with {provider} is not configured")
        next_url = local_path(next)
        if next_url is None:
            raise InvalidRequest("next must be a local path")
        state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        redirect = RedirectResponse(oauth.authorization_url(_callback(app, provider), state, verifier), 302)
        sessions.start_oauth(redirect, provider, state, verifier, next_url)
        return redirect

    @router.get("/oauth/{provider}/callback", include_in_schema=False)
    async def oauth_callback(
        provider: str, request: Request, code: str = "", state: str = "", error: str = ""
    ) -> RedirectResponse:
        oauth = app.oauth.get(provider)
        if oauth is None:
            raise NotFound(f"sign-in with {provider} is not configured")
        try:
            verifier, next_url = sessions.finish_oauth(request, provider, state)
        except NotAuthenticated as exc:
            return _failed(provider, str(exc))  # "expired" or "mismatch"
        if error or not code:
            return _failed(provider, "cancelled" if error == "access_denied" else "provider_error", error)
        try:
            identity = await oauth.exchange(_callback(app, provider), code, verifier)
            result = await app.auth.sign_in_with(identity)
        except UnverifiedEmail as exc:
            return _failed(provider, "unverified_email", str(exc))
        except AccountDisabled:
            return _failed(provider, "disabled")
        except SignupClosed:
            return _failed(provider, "signup_closed")
        except Exception as exc:  # a provider or network failure is a message on the login page, never a 500
            _LOG.exception("oauth sign-in failed", extra={"event": "auth.oauth_failed", "provider": provider})
            return _failed(provider, "provider_error", type(exc).__name__, logged=True)
        if isinstance(result, ClaimNeeded):
            redirect = _redirect("/claim")
            sessions.start_claim(redirect, result, next_url)
            return redirect
        redirect = _redirect(next_url)
        sessions.issue(redirect, result.id)
        return redirect

    @router.get("/claim", response_model=ClaimOut)
    async def claim_details(request: Request) -> ClaimOut:
        claim, _ = sessions.read_claim(request)
        return ClaimOut(email=claim.identity.email, provider=claim.identity.provider)

    @router.post("/claim/keep", response_model=SignedIn)
    async def claim_keep(body: KeepAccount, request: Request, response: Response) -> SignedIn:
        claim, next_url = sessions.read_claim(request)
        limit(request, claim.identity.email)
        user = await app.auth.keep_account(claim.identity, claim.account_id, body.password)
        return _signed_in(response, user, next_url)

    @router.post("/claim/new", response_model=SignedIn)
    async def claim_new(request: Request, response: Response) -> SignedIn:
        claim, next_url = sessions.read_claim(request)
        user = await app.auth.claim(claim.identity, claim.account_id)
        return _signed_in(response, user, next_url)

    def _signed_in(response: Response, user: User, next_url: str) -> SignedIn:
        response.delete_cookie(CLAIM_COOKIE, path="/")
        sessions.issue(response, user.id)
        return SignedIn(user=user, next=next_url)

    return router


def _redirect(location: str) -> RedirectResponse:
    redirect = RedirectResponse(location, status_code=302)
    redirect.delete_cookie(OAUTH_COOKIE, path="/")
    return redirect


def _failed(provider: str, reason: str, detail: str = "", *, logged: bool = False) -> RedirectResponse:
    if not logged:
        _LOG.warning(
            "oauth sign-in failed",
            extra={"event": "auth.oauth_failed", "provider": provider, "reason": reason, "detail": detail},
        )
    return _redirect(f"/login?error={reason}")


def _callback(app: Application, provider: str) -> str:
    return f"{app.settings.public_base_url.rstrip('/')}/api/auth/oauth/{provider}/callback"


def oauth_redirect_uris(app: Application) -> list[str]:
    """What to register in the Google and GitHub consoles, character for character."""
    return [_callback(app, provider) for provider in sorted(app.oauth)]
