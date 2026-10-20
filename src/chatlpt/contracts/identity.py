"""Identity contracts: users, credentials and linked sign-in identities.

See docs/product-specs/chatlpt.md#accounts.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import EmailStr, Field

from chatlpt.contracts.common import Contract

OAuthProviderName = Literal["google", "github"]


UNCLAIMED_PREFIX = "unclaimed+"  # a retired account's email: unclaimed+<id>@invalid (D26)


class User(Contract):
    id: UUID
    email: str
    display_name: str
    is_admin: bool
    disabled: bool
    created_at: datetime
    # True only when Google or GitHub confirmed this email (D26). A password signup is unverified, and a
    # provider sign-in with the same email claims it.
    email_verified: bool = False

    @property
    def unclaimed(self) -> bool:
        """Retired by a claim: a provider proved someone else owns the address this account used."""
        return self.email.startswith(UNCLAIMED_PREFIX)


class NewUser(Contract):
    """What signup needs. The password never appears on a stored record; only its hash does."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(default="", max_length=120)


class Login(Contract):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class OAuthIdentity(Contract):
    """A verified identity returned by a provider after the code exchange."""

    provider: OAuthProviderName
    subject: str  # the provider's stable user id
    email: str  # verified by the provider
    display_name: str = ""


class ClaimNeeded(Contract):
    """A provider proved ``identity.email``, but an unverified password account already uses it (D26).

    The person chooses: enter that account's password to keep it (``keep_account``), or continue with a
    new account, which retires the old one (``claim``).
    """

    identity: OAuthIdentity
    account_id: UUID


class SessionClaims(Contract):
    """What a session cookie carries. Signed by the HTTP layer; never a secret."""

    user_id: UUID
    issued_at: datetime
