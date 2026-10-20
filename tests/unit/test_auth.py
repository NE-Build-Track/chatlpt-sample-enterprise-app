"""Signup, login, provider sign-in, claims of an unverified email, and admin rights (D5, D6, D26)."""

import pytest

from chatlpt.contracts import ClaimNeeded, Login, NewUser, OAuthIdentity, User
from chatlpt.errors import (
    AccountDisabled,
    Conflict,
    InvalidRequest,
    NotAuthenticated,
    NotFound,
    SignupClosed,
)
from chatlpt.services.auth import AuthService
from chatlpt.testing import FixedClock, MemoryStore, PlainHasher

CAROL = OAuthIdentity(provider="google", subject="g-carol", email="carol@example.com", display_name="Carol")


def service(store: MemoryStore, *, allow_signup: bool = True) -> AuthService:
    return AuthService(store, PlainHasher(), FixedClock(), allow_signup=allow_signup)


async def signed_in(auth: AuthService, identity: OAuthIdentity) -> User:
    result = await auth.sign_in_with(identity)
    assert isinstance(result, User), result
    return result


async def test_signup_is_unverified_and_never_admin() -> None:
    store = MemoryStore()
    auth = service(store)
    user = await auth.signup(NewUser(email="Admin@Example.com", password="correct horse", display_name=""))
    assert user.email == "admin@example.com" and user.display_name == "admin"
    assert not user.is_admin and not user.email_verified
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
    with pytest.raises(AccountDisabled):
        await auth.login(Login(email="bob@example.com", password="correct horse"))
    with pytest.raises(NotAuthenticated):
        await auth.current(user.id)


async def test_provider_accounts_are_verified_and_link_by_subject_then_verified_email() -> None:
    store = MemoryStore()
    auth = service(store)
    carol = await signed_in(auth, CAROL)
    assert carol.email_verified and await store.password_hash(carol.id) is None
    renamed = CAROL.model_copy(update={"email": "carol@other.example"})
    assert (await signed_in(auth, renamed)).id == carol.id  # the same subject wins over the email
    github = OAuthIdentity(provider="github", subject="42", email="carol@example.com")
    assert (await signed_in(auth, github)).id == carol.id  # two providers proving one email: one account


async def test_a_provider_sign_in_over_an_unverified_account_asks_first() -> None:
    store = MemoryStore()
    auth = service(store)
    squat = await auth.signup(NewUser(email="carol@example.com", password="squatters pw"))
    result = await auth.sign_in_with(CAROL)
    assert result == ClaimNeeded(identity=CAROL, account_id=squat.id)
    assert await store.user_by_identity("google", "g-carol") is None  # nothing linked until she chooses


async def test_keeping_the_account_needs_its_password_and_then_verifies_it() -> None:
    store = MemoryStore()
    auth = service(store)
    mine = await auth.signup(NewUser(email="carol@example.com", password="my own pw"))
    with pytest.raises(NotAuthenticated):
        await auth.keep_account(CAROL, mine.id, "a guess")
    kept = await auth.keep_account(CAROL, mine.id, "my own pw")
    assert kept.id == mine.id and kept.email_verified
    assert (await signed_in(auth, CAROL)).id == mine.id  # linked: no prompt next time
    with pytest.raises(NotAuthenticated):  # verified now, so it can no longer be claimed or kept again
        await auth.claim(CAROL, mine.id)


async def test_a_claim_retires_the_squatter_and_gives_the_owner_a_new_account() -> None:
    store = MemoryStore()
    auth = service(store)
    squat = await auth.signup(NewUser(email="carol@example.com", password="squatters pw"))
    await store.set_admin(squat.id, True)  # an unverified admin is retired like anyone else
    owner = await auth.claim(CAROL, squat.id)
    assert owner.id != squat.id and owner.email == "carol@example.com" and owner.email_verified
    assert not owner.is_admin
    retired = await store.user_by_id(squat.id)
    assert retired is not None and retired.disabled and retired.unclaimed and not retired.is_admin
    assert retired.email == f"unclaimed+{squat.id}@invalid"
    assert await store.password_hash(squat.id) is None
    with pytest.raises(NotAuthenticated):  # the old password is gone, and the address is someone else's
        await auth.login(Login(email="carol@example.com", password="squatters pw"))
    with pytest.raises(NotAuthenticated):  # the squatter's open session ends on its next request
        await auth.current(squat.id)
    with pytest.raises(Conflict):
        await auth.signup(NewUser(email="carol@example.com", password="try again"))
    assert (await signed_in(auth, CAROL)).id == owner.id


async def test_claims_work_with_signup_closed_and_skip_the_prompt_for_a_disabled_account() -> None:
    store = MemoryStore()
    open_auth = service(store)
    squat = await open_auth.signup(NewUser(email="carol@example.com", password="squatters pw"))
    closed = service(store, allow_signup=False)
    with pytest.raises(SignupClosed):
        await closed.sign_in_with(OAuthIdentity(provider="google", subject="x", email="new@example.com"))
    await store.set_disabled(squat.id, True)  # an admin already shut the squatter out
    owner = await signed_in(closed, CAROL)  # nothing to keep, so no prompt; the address is reclaimed
    assert owner.id != squat.id and owner.email_verified


async def test_a_stale_claim_is_refused() -> None:
    store = MemoryStore()
    auth = service(store)
    squat = await auth.signup(NewUser(email="carol@example.com", password="squatters pw"))
    other = CAROL.model_copy(update={"email": "someone@example.com"})
    with pytest.raises(NotAuthenticated):
        await auth.claim(other, squat.id)  # the cookie names an account with a different email


async def test_admin_rights_come_only_from_the_operator_command() -> None:
    store = MemoryStore()
    auth = service(store)
    pw = await auth.signup(NewUser(email="ops@example.com", password="correct horse"))
    with pytest.raises(InvalidRequest, match="not verified"):
        await auth.set_admin("ops@example.com", True)
    assert (await auth.set_admin("OPS@example.com", True, allow_unverified=True)).is_admin
    carol = await signed_in(auth, CAROL)
    assert (await auth.set_admin("carol@example.com", True)).is_admin
    assert not (await auth.set_admin("carol@example.com", False)).is_admin
    stored = await store.user_by_id(pw.id)
    assert stored is not None and stored.is_admin and carol.id != pw.id
    with pytest.raises(NotFound):
        await auth.set_admin("nobody@example.com", True)
