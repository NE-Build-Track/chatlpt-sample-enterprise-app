"""Signed session cookies and the current-user dependency (docs/SECURITY.md#rules)."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from chatlpt.contracts import User
from chatlpt.errors import NotAuthenticated
from chatlpt.runtime import Application

SESSION_COOKIE = "chatlpt_session"
OAUTH_COOKIE = "chatlpt_oauth"
CSRF_HEADER = "x-chatlpt"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class Sessions:
    def __init__(self, secret: str, *, ttl_s: int, secure: bool) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt="chatlpt.session")
        self._oauth = URLSafeTimedSerializer(secret, salt="chatlpt.oauth")
        self._ttl_s = ttl_s
        self._secure = secure

    def issue(self, response: Response, user_id: UUID) -> None:
        token = self._serializer.dumps({"uid": str(user_id)})
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=self._ttl_s,
            httponly=True,
            secure=self._secure,
            samesite="lax",
            path="/",
        )

    def clear(self, response: Response) -> None:
        response.delete_cookie(SESSION_COOKIE, path="/")

    def read(self, request: Request) -> UUID | None:
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            return None
        try:
            data = self._serializer.loads(token, max_age=self._ttl_s)
        except (BadSignature, SignatureExpired):
            return None
        try:
            return UUID(str(data.get("uid")))
        except (ValueError, AttributeError):
            return None

    def start_oauth(self, response: Response, provider: str, state: str, nonce: str, next_url: str) -> None:
        token = self._oauth.dumps({"p": provider, "s": state, "n": nonce, "next": next_url})
        response.set_cookie(
            OAUTH_COOKIE, token, max_age=600, httponly=True, secure=self._secure, samesite="lax", path="/"
        )

    def finish_oauth(
        self, request: Request, response: Response, provider: str, state: str
    ) -> tuple[str, str]:
        """Returns (nonce, next_url). Raises NotAuthenticated when the state does not match."""
        token = request.cookies.get(OAUTH_COOKIE)
        response.delete_cookie(OAUTH_COOKIE, path="/")
        if not token:
            raise NotAuthenticated("sign-in expired; try again")
        try:
            data = self._oauth.loads(token, max_age=600)
        except (BadSignature, SignatureExpired) as exc:
            raise NotAuthenticated("sign-in expired; try again") from exc
        if data.get("p") != provider or data.get("s") != state:
            raise NotAuthenticated("sign-in state mismatch")
        return str(data.get("n") or ""), str(data.get("next") or "/")


def csrf_guard(request: Request) -> None:
    """State-changing JSON requests must carry the custom header; browsers never add it cross-site."""
    if request.method in _SAFE_METHODS:
        return
    if request.headers.get(CSRF_HEADER) != "1":
        raise NotAuthenticated("missing request header")


def current_user_dependency(app: Application, sessions: Sessions) -> Callable[[Request], Awaitable[User]]:
    async def current_user(request: Request) -> User:
        user_id = sessions.read(request)
        if user_id is None:
            raise NotAuthenticated("sign in to continue")
        return await app.auth.current(user_id)

    return current_user
