"""The network book, read from the engine whenever it is shown (D29).

The embedded engine already keeps the Batteries usage rows and a cost per job, in its own database in
this container. ChatLPT does not copy them: a message's or an image's network cost is the engine's
``costs.for_job`` for its ``job_id``, and a user's network totals are the engine's cost summary. The
retail book stays in ChatLPT's ledger; the two join on the job id. A failed paid reply keeps its
``job_id`` on the message, so its cost shows too, and the engine's summary counts it.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from chatlpt.contracts import GeneratedImage, Message, Money, NetworkTotals, UsageTotals, User, WholesaleCost
from chatlpt.errors import ChatUnavailable, NotFound
from chatlpt.protocols import ChatBackend, UsageLedger

_LOG = logging.getLogger(__name__)
_ZERO = Money(amount=Decimal(0), currency="USD")
_FAILED = ("failed_after_payment", "uncertain")


class NetworkCostService:
    def __init__(self, ledger: UsageLedger, backend: ChatBackend | None) -> None:
        self._ledger = ledger
        self._backend = backend

    async def cost(self, user_id: UUID, job_id: UUID, *, paid: bool) -> WholesaleCost:
        """One job's network cost. ``unknown`` when the engine has no record of it, never $0."""
        if self._backend is None:
            return WholesaleCost(status="unknown")
        try:
            cost = await self._backend.wholesale(user_id, job_id)
        except (NotFound, ChatUnavailable) as exc:
            _LOG.warning(
                "network cost unknown",
                extra={"event": "billing.network_unknown", "job_id": str(job_id), "error": str(exc)},
            )
            return WholesaleCost(status="unknown")
        if cost.status == "none" and paid:
            _LOG.warning(
                "the engine reports no payment for a job the app believed paid",
                extra={"event": "billing.network_none_but_paid", "job_id": str(job_id)},
            )
        return cost

    async def with_costs(self, user_id: UUID, messages: Sequence[Message]) -> list[Message]:
        """The messages with the network cost of each job they ran, and of each image they made."""
        filled: list[Message] = []
        for message in messages:
            update: dict[str, object] = {}
            if message.job_id is not None:
                paid = message.state in ("complete", "uncertain")
                cost = await self.cost(user_id, message.job_id, paid=paid)
                update["wholesale"] = cost.model_copy(update={"orchestrator_url": message.orchestrator_url})
            if message.images:
                update["images"] = tuple([await self._image_cost(user_id, image) for image in message.images])
            filled.append(message.model_copy(update=update) if update else message)
        return filled

    async def _image_cost(self, user_id: UUID, image: GeneratedImage) -> GeneratedImage:
        if image.job_id is None:
            return image
        cost = await self.cost(user_id, image.job_id, paid=True)
        return image.model_copy(
            update={"wholesale": cost.model_copy(update={"orchestrator_url": image.orchestrator_url})}
        )

    @staticmethod
    def conversation_totals(retail: UsageTotals, messages: Sequence[Message]) -> UsageTotals:
        """Retail from the ledger; network summed over the costs ``with_costs`` filled in."""
        costs = [m.wholesale for m in messages if m.wholesale is not None]
        costs += [i.wholesale for m in messages for i in m.images if i.wholesale is not None]
        return _merge(retail, _sum(costs))

    async def user_totals(self, user_id: UUID, start: datetime, end: datetime) -> UsageTotals:
        retail = await self._ledger.totals(user_id, start, end)
        return _merge(retail, await self._network(user_id, start, end))

    async def totals_by_user(
        self, users: Sequence[User], start: datetime, end: datetime
    ) -> list[UsageTotals]:
        """One row per user, including users whose every reply failed (no retail, still network spend)."""
        retail = {t.user_id: t for t in await self._ledger.totals_by_user(start, end)}
        rows: list[UsageTotals] = []
        for user in users:
            base = retail.get(user.id) or await self._ledger.totals(user.id, start, end)
            rows.append(_merge(base, await self._network(user.id, start, end)))
        return rows

    async def _network(self, user_id: UUID, start: datetime, end: datetime) -> NetworkTotals:
        if self._backend is None:
            return NetworkTotals(delivered=_ZERO, failed=_ZERO)
        try:
            return await self._backend.network_totals(user_id, start, end)
        except ChatUnavailable as exc:
            _LOG.warning(
                "network totals unavailable", extra={"event": "billing.network_unknown", "error": str(exc)}
            )
            return NetworkTotals(delivered=_ZERO, failed=_ZERO)


def _sum(costs: Sequence[WholesaleCost]) -> NetworkTotals:
    def usd(*statuses: str) -> Money:
        amounts = (c.amount.amount for c in costs if c.status in statuses and c.amount is not None)
        return Money(amount=sum(amounts, Decimal(0)), currency="USD")

    return NetworkTotals(
        delivered=usd("delivered"),
        failed=usd(*_FAILED),
        pending=sum(1 for c in costs if c.status == "pending"),
    )


def _merge(retail: UsageTotals, network: NetworkTotals) -> UsageTotals:
    return retail.model_copy(
        update={
            "wholesale": network.delivered,
            "wholesale_failed": network.failed,
            "wholesale_pending": network.pending,
        }
    )
