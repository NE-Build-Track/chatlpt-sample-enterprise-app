"""Identity rules: signup, login, provider sign-in and account linking (D5, D6, D7)."""

import logging
from uuid import UUID

from chatlpt.contracts import Login, NewUser, OAuthIdentity, User
from chatlpt.errors import Conflict, NotAuthenticated
from chatlpt.protocols import Clock, PasswordHasher, UserStore
from chatlpt.utils import new_id

_LOG = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        users: UserStore,
        hasher: PasswordHasher,
        clock: Clock,
        *,
        admin_emails: frozenset[str],
        allow_signup: bool,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._clock = clock
        self._admins = admin_emails
        self._allow_signup = allow_signup

    async def signup(self, request: NewUser) -> User:
        if not self._allow_signup:
            raise Conflict("signup is disabled")
        email = request.email.lower()
        if await self._users.user_by_email(email) is not None:
            raise Conflict("an account with that email already exists")
        user = self._new_user(email, request.display_name)
        await self._users.create_user(user, self._hasher.hash(request.password))
        _LOG.info("user signed up", extra={"event": "auth.signup", "user_id": str(user.id)})
        return user

    async def login(self, request: Login) -> User:
        user = await self._users.user_by_email(request.email.lower())
        hashed = await self._users.password_hash(user.id) if user else None
        if user is None or hashed is None or not self._hasher.verify(request.password, hashed):
            raise NotAuthenticated("email or password is incorrect")
        if user.disabled:
            raise NotAuthenticated("this account is disabled")
        _LOG.info("user logged in", extra={"event": "auth.login", "user_id": str(user.id)})
        return user

    async def sign_in_with(self, identity: OAuthIdentity) -> User:
        """Find the linked user; else link by verified email; else create (when signup is open)."""
        user = await self._users.user_by_identity(identity.provider, identity.subject)
        if user is None:
            user = await self._users.user_by_email(identity.email)
            if user is None:
                if not self._allow_signup:
                    raise NotAuthenticated("no account for that email and signup is disabled")
                user = self._new_user(identity.email, identity.display_name)
                await self._users.create_user(user, None)
            await self._users.link_identity(user.id, identity)
            _LOG.info(
                "identity linked",
                extra={"event": "auth.link", "user_id": str(user.id), "provider": identity.provider},
            )
        if user.disabled:
            raise NotAuthenticated("this account is disabled")
        return user

    async def current(self, user_id: UUID) -> User:
        user = await self._users.user_by_id(user_id)
        if user is None or user.disabled:
            raise NotAuthenticated("session is no longer valid")
        return user

    def _new_user(self, email: str, display_name: str) -> User:
        return User(
            id=new_id(),
            email=email,
            display_name=display_name or email.split("@")[0],
            is_admin=email in self._admins,
            disabled=False,
            created_at=self._clock.now(),
        )
