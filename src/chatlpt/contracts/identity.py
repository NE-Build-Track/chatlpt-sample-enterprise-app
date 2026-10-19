"""Identity contracts: users, credentials and linked sign-in identities.

See docs/product-specs/chatlpt.md#accounts.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import EmailStr, Field

from chatlpt.contracts.common import Contract

OAuthProviderName = Literal["google", "github"]


class User(Contract):
    id: UUID
    email: str
    display_name: str
    is_admin: bool
    disabled: bool
    created_at: datetime


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


class SessionClaims(Contract):
    """What a session cookie carries. Signed by the HTTP layer; never a secret."""

    user_id: UUID
    issued_at: datetime
