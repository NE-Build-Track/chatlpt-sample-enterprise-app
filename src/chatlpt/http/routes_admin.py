"""Admin routes: every user with both books for the month, and disabling users (D17)."""

from collections.abc import Awaitable, Callable
from datetime import UTC
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from chatlpt.contracts import UsageTotals, User
from chatlpt.http.routes_chat import month_bounds
from chatlpt.http.sessions import csrf_guard
from chatlpt.runtime import Application


class UserRow(BaseModel):
    user: User
    totals: UsageTotals | None


class DisabledBody(BaseModel):
    disabled: bool


def admin_router(app: Application, current_user: Callable[[Request], Awaitable[User]]) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(csrf_guard)])
    Current = Annotated[User, Depends(current_user)]

    @router.get("/users", response_model=list[UserRow])
    async def users(admin: Current) -> list[UserRow]:
        start, end = month_bounds(app.clock.now().astimezone(UTC))
        people = await app.admin.users(admin)
        totals = {t.user_id: t for t in await app.admin.totals_by_user(admin, start, end)}
        return [UserRow(user=u, totals=totals.get(u.id)) for u in people]

    @router.post("/users/{user_id}/disabled", response_model=User)
    async def set_disabled(user_id: UUID, body: DisabledBody, admin: Current) -> User:
        return await app.admin.set_disabled(admin, user_id, body.disabled)

    return router
