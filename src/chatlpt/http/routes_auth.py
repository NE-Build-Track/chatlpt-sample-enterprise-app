"""Account routes: signup, login, logout, me, and the OAuth redirect dance (D5, D6)."""

import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from chatlpt.contracts import Login, NewUser, User
from chatlpt.errors import InvalidRequest, NotFound
from chatlpt.http.sessions import Sessions, csrf_guard
from chatlpt.runtime import Application


class ProvidersOut(BaseModel):
    providers: list[str]
    allow_signup: bool


def auth_router(
    app: Application, sessions: Sessions, current_user: Callable[[Request], Awaitable[User]]
) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(csrf_guard)])
    Current = Annotated[User, Depends(current_user)]

    @router.get("/providers", response_model=ProvidersOut)
    async def providers() -> ProvidersOut:
        return ProvidersOut(providers=sorted(app.oauth), allow_signup=app.settings.allow_signup)

    @router.post("/signup", response_model=User, status_code=201)
    async def signup(body: NewUser, response: Response) -> User:
        user = await app.auth.signup(body)
        sessions.issue(response, user.id)
        return user

    @router.post("/login", response_model=User)
    async def login(body: Login, response: Response) -> User:
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
    async def oauth_start(provider: str, request: Request, next: str = "/") -> RedirectResponse:
        oauth = app.oauth.get(provider)
        if oauth is None:
            raise NotFound(f"sign-in with {provider} is not configured")
        if not next.startswith("/") or next.startswith("//"):
            raise InvalidRequest("next must be a local path")
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        redirect = RedirectResponse(
            oauth.authorization_url(_callback(app, provider), state, nonce), status_code=302
        )
        sessions.start_oauth(redirect, provider, state, nonce, next)
        return redirect

    @router.get("/oauth/{provider}/callback", include_in_schema=False)
    async def oauth_callback(
        provider: str, request: Request, code: str = "", state: str = ""
    ) -> RedirectResponse:
        oauth = app.oauth.get(provider)
        if oauth is None:
            raise NotFound(f"sign-in with {provider} is not configured")
        redirect = RedirectResponse("/", status_code=302)
        nonce, next_url = sessions.finish_oauth(request, redirect, provider, state)
        if not code:
            raise InvalidRequest("the provider returned no code")
        identity = await oauth.exchange(_callback(app, provider), code, nonce)
        user = await app.auth.sign_in_with(identity)
        sessions.issue(redirect, user.id)
        redirect.headers["location"] = next_url
        return redirect

    return router


def _callback(app: Application, provider: str) -> str:
    return f"{app.settings.public_base_url.rstrip('/')}/api/auth/oauth/{provider}/callback"
