"""Signup, login, provider sign-in, linking and admin flags (D5 to D7)."""

import pytest

from chatlpt.contracts import Login, NewUser, OAuthIdentity
from chatlpt.errors import Conflict, NotAuthenticated
from chatlpt.services.auth import AuthService
from chatlpt.testing import FixedClock, MemoryStore, PlainHasher


def service(store: MemoryStore, *, allow_signup: bool = True) -> AuthService:
    return AuthService(
        store,
        PlainHasher(),
        FixedClock(),
        admin_emails=frozenset({"admin@example.com"}),
        allow_signup=allow_signup,
    )


async def test_signup_then_login_and_admin_flag() -> None:
    store = MemoryStore()
    auth = service(store)
    user = await auth.signup(NewUser(email="Admin@Example.com", password="correct horse", display_name=""))
    assert user.is_admin and user.email == "admin@example.com" and user.display_name == "admin"
    assert (await auth.login(Login(email="admin@example.com", password="correct horse"))).id == user.id
    with pytest.raises(NotAuthenticated):
        await auth.login(Login(email="admin@example.com", password="wrong"))
    with pytest.raises(Conflict):
        await auth.signup(NewUser(email="admin@example.com", password="another one"))


async def test_disabled_users_cannot_log_in_or_keep_a_session() -> None:
    store = MemoryStore()
    auth = service(store)
    user = await auth.signup(NewUser(email="bob@example.com", password="correct horse"))
    await store.set_disabled(user.id, True)
    with pytest.raises(NotAuthenticated):
        await auth.login(Login(email="bob@example.com", password="correct horse"))
    with pytest.raises(NotAuthenticated):
        await auth.current(user.id)


async def test_provider_sign_in_links_by_verified_email_then_by_subject() -> None:
    store = MemoryStore()
    auth = service(store)
    existing = await auth.signup(NewUser(email="carol@example.com", password="correct horse"))
    identity = OAuthIdentity(provider="github", subject="42", email="carol@example.com", display_name="Carol")
    assert (await auth.sign_in_with(identity)).id == existing.id
    renamed = identity.model_copy(update={"email": "carol@other.example"})
    assert (await auth.sign_in_with(renamed)).id == existing.id  # same subject wins over the email
    fresh = OAuthIdentity(provider="google", subject="g1", email="dave@example.com", display_name="Dave")
    dave = await auth.sign_in_with(fresh)
    assert dave.email == "dave@example.com" and await store.password_hash(dave.id) is None


async def test_provider_sign_in_respects_closed_signup() -> None:
    auth = service(MemoryStore(), allow_signup=False)
    with pytest.raises(NotAuthenticated):
        await auth.sign_in_with(OAuthIdentity(provider="google", subject="x", email="new@example.com"))
    with pytest.raises(Conflict):
        await auth.signup(NewUser(email="new@example.com", password="correct horse"))
