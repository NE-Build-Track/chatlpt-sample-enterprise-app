"""Identity rules: signup, login, provider sign-in, claims and admin rights (D5, D6, D26).

A password signup proves nothing about its email, so it is **unverified**. Google and GitHub confirm
the email they return, so an account they create or link is **verified**. When a provider proves an
email that an unverified password account already uses, the verified owner wins (D26): they either
enter that account's password to keep it (``keep_account``), or continue with a new account, which
retires the old one (``claim``). Admin rights come only from an operator command (``set_admin``).
"""

import logging
from uuid import UUID

from chatlpt.contracts import UNCLAIMED_PREFIX, ClaimNeeded, Login, NewUser, OAuthIdentity, User
from chatlpt.errors import AccountDisabled, Conflict, InvalidRequest, NotAuthenticated, NotFound, SignupClosed
from chatlpt.protocols import Clock, PasswordHasher, UserStore
from chatlpt.utils import new_id

_LOG = logging.getLogger(__name__)


class AuthService:
    def __init__(self, users: UserStore, hasher: PasswordHasher, clock: Clock, *, allow_signup: bool) -> None:
        self._users = users
        self._hasher = hasher
        self._clock = clock
        self._allow_signup = allow_signup

    async def signup(self, request: NewUser) -> User:
        if not self._allow_signup:
            raise Conflict("signup is disabled")
        email = request.email.lower()
        if await self._users.user_by_email(email) is not None:
            raise Conflict("an account with that email already exists")
        user = self._new_user(email, request.display_name, verified=False)
        await self._users.create_user(user, self._hasher.hash(request.password))
        _LOG.info("user signed up", extra={"event": "auth.signup", "user_id": str(user.id)})
        return user

    async def login(self, request: Login) -> User:
        user = await self._users.user_by_email(request.email.lower())
        hashed = await self._users.password_hash(user.id) if user else None
        if user is None or hashed is None or not self._hasher.verify(request.password, hashed):
            raise NotAuthenticated("email or password is incorrect")
        if user.disabled:
            raise AccountDisabled("this account is disabled")
        _LOG.info("user logged in", extra={"event": "auth.login", "user_id": str(user.id)})
        return user

    async def sign_in_with(self, identity: OAuthIdentity) -> User | ClaimNeeded:
        """The linked user; else the verified account with this email; else a claim; else a new account."""
        user = await self._users.user_by_identity(identity.provider, identity.subject)
        if user is None:
            user = await self._users.user_by_email(identity.email)
            if user is not None and not user.email_verified:
                if not user.disabled:
                    return ClaimNeeded(identity=identity, account_id=user.id)
                return await self.claim(identity, user.id)  # nothing to keep in a disabled account
            if user is None:
                if not self._allow_signup:
                    raise SignupClosed("no account for that email and signup is disabled")
                user = self._new_user(identity.email, identity.display_name, verified=True)
                await self._users.create_user(user, None)
            await self._link(user, identity)
        if user.disabled:
            raise AccountDisabled("this account is disabled")
        return user

    async def keep_account(self, identity: OAuthIdentity, account_id: UUID, password: str) -> User:
        """The provider proved the email and the password proves the account: link them (D26)."""
        user = await self._claimable(identity, account_id)
        hashed = await self._users.password_hash(user.id)
        if hashed is None or not self._hasher.verify(password, hashed):
            raise NotAuthenticated("that password is not this account's")
        await self._link(user, identity)
        await self._users.set_email_verified(user.id, True)
        _LOG.info("account kept", extra={"event": "auth.account_kept", "user_id": str(user.id)})
        return user.model_copy(update={"email_verified": True})

    async def claim(self, identity: OAuthIdentity, account_id: UUID) -> User:
        """Retire the unverified account and give the verified owner a new one (D26). Works even when
        signup is closed: the address already had an account."""
        old = await self._claimable(identity, account_id)
        user = self._new_user(identity.email, identity.display_name, verified=True)
        placeholder = f"{UNCLAIMED_PREFIX}{old.id}@invalid"
        await self._users.claim_email(old.id, placeholder, user, identity)
        _LOG.warning(
            "email claimed",
            extra={
                "event": "auth.email_claimed",
                "retired_user_id": str(old.id),
                "user_id": str(user.id),
                "provider": identity.provider,
            },
        )
        return user

    async def set_admin(self, email: str, is_admin: bool, *, allow_unverified: bool = False) -> User:
        """Grant or revoke admin. Only ``chatlpt make-admin`` / ``revoke-admin`` call this (D26)."""
        user = await self._users.user_by_email(email.lower())
        if user is None:
            raise NotFound(f"no account for {email}")
        if is_admin and not user.email_verified and not allow_unverified:
            raise InvalidRequest(
                f"{email} is not verified: anyone could have signed up with it. Have the owner sign in "
                "with Google or GitHub first, or pass --allow-unverified"
            )
        await self._users.set_admin(user.id, is_admin)
        _LOG.warning(
            "admin rights changed",
            extra={"event": "auth.admin_set", "user_id": str(user.id), "is_admin": is_admin},
        )
        return user.model_copy(update={"is_admin": is_admin})

    async def current(self, user_id: UUID) -> User:
        user = await self._users.user_by_id(user_id)
        if user is None or user.disabled:
            raise NotAuthenticated("session is no longer valid")
        return user

    async def _claimable(self, identity: OAuthIdentity, account_id: UUID) -> User:
        """The account a claim is about, re-checked: it still has the proven email and is still unverified."""
        user = await self._users.user_by_id(account_id)
        if user is None or user.email != identity.email or user.email_verified:
            raise NotAuthenticated("this sign-in expired; try again")
        return user

    async def _link(self, user: User, identity: OAuthIdentity) -> None:
        await self._users.link_identity(user.id, identity)
        _LOG.info(
            "identity linked",
            extra={"event": "auth.link", "user_id": str(user.id), "provider": identity.provider},
        )

    def _new_user(self, email: str, display_name: str, *, verified: bool) -> User:
        return User(
            id=new_id(),
            email=email,
            display_name=display_name or email.split("@")[0],
            is_admin=False,
            disabled=False,
            created_at=self._clock.now(),
            email_verified=verified,
        )
