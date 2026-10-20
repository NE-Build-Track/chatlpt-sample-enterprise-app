"""Admin rules: who may see the two books for everyone, and disabling users (D17)."""

from datetime import datetime
from uuid import UUID

from chatlpt.contracts import UsageTotals, User
from chatlpt.errors import AccessDenied, NotFound
from chatlpt.protocols import UserStore
from chatlpt.services.network import NetworkCostService


class AdminService:
    def __init__(self, users: UserStore, network: NetworkCostService) -> None:
        self._users = users
        self._network = network

    @staticmethod
    def require(admin: User) -> None:
        if not admin.is_admin:
            raise AccessDenied("admin only")

    async def users(self, admin: User) -> list[User]:
        self.require(admin)
        return await self._users.list_users()

    async def totals_by_user(self, admin: User, start: datetime, end: datetime) -> list[UsageTotals]:
        self.require(admin)
        return await self._network.totals_by_user(await self._users.list_users(), start, end)

    async def set_disabled(self, admin: User, user_id: UUID, disabled: bool) -> User:
        self.require(admin)
        user = await self._users.user_by_id(user_id)
        if user is None:
            raise NotFound("user not found")
        if user.id == admin.id:
            raise AccessDenied("you cannot disable yourself")
        await self._users.set_disabled(user_id, disabled)
        return user.model_copy(update={"disabled": disabled})
