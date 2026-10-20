"""Signed session cookies and the current-user dependency (docs/SECURITY.md#rules)."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from chatlpt.contracts import ClaimNeeded, User
from chatlpt.errors import NotAuthenticated
from chatlpt.runtime import Application

SESSION_COOKIE = "chatlpt_session"
OAUTH_COOKIE = "chatlpt_oauth"
CLAIM_COOKIE = "chatlpt_claim"
CSRF_HEADER = "x-chatlpt"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_FLOW_TTL_S = 600  # an OAuth round trip and the claim prompt (D26) each get ten minutes


class Sessions:
    def __init__(self, secret: str, *, ttl_s: int, secure: bool) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt="chatlpt.session")
        self._oauth = URLSafeTimedSerializer(secret, salt="chatlpt.oauth")
        self._claim = URLSafeTimedSerializer(secret, salt="chatlpt.claim")
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

    def start_oauth(
        self, response: Response, provider: str, state: str, code_verifier: str, next_url: str
    ) -> None:
        token = self._oauth.dumps({"p": provider, "s": state, "v": code_verifier, "next": next_url})
        self._set(response, OAUTH_COOKIE, token)

    def finish_oauth(self, request: Request, provider: str, state: str) -> tuple[str, str]:
        """Returns (code_verifier, next_url). Raises NotAuthenticated ("expired" or "mismatch")."""
        token = request.cookies.get(OAUTH_COOKIE)
        if not token:
            raise NotAuthenticated("expired")
        try:
            data = self._oauth.loads(token, max_age=_FLOW_TTL_S)
        except (BadSignature, SignatureExpired) as exc:
            raise NotAuthenticated("expired") from exc
        if data.get("p") != provider or data.get("s") != state or not data.get("v"):
            raise NotAuthenticated("mismatch")
        return str(data["v"]), str(data.get("next") or "/")

    def start_claim(self, response: Response, claim: ClaimNeeded, next_url: str) -> None:
        """Hold the proven identity while the person answers the claim prompt (D26). Signed, never stored."""
        token = self._claim.dumps({"c": claim.model_dump(mode="json"), "next": next_url})
        self._set(response, CLAIM_COOKIE, token)

    def read_claim(self, request: Request) -> tuple[ClaimNeeded, str]:
        token = request.cookies.get(CLAIM_COOKIE)
        if not token:
            raise NotAuthenticated("this sign-in expired; try again")
        try:
            data = self._claim.loads(token, max_age=_FLOW_TTL_S)
            return ClaimNeeded.model_validate(data["c"]), str(data.get("next") or "/")
        except (BadSignature, SignatureExpired, KeyError, ValueError) as exc:
            raise NotAuthenticated("this sign-in expired; try again") from exc

    def _set(self, response: Response, name: str, token: str) -> None:
        response.set_cookie(
            name, token, max_age=_FLOW_TTL_S, httponly=True, secure=self._secure, samesite="lax", path="/"
        )


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
