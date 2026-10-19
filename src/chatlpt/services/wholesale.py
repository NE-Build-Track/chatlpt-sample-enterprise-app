"""The wholesale book's catch-up: ask the engine for costs that have arrived and record them (D3)."""

import logging
from datetime import timedelta

from chatlpt.errors import AppError
from chatlpt.protocols import ChatBackend, Clock, UsageLedger

_LOG = logging.getLogger(__name__)


class WholesaleSync:
    def __init__(
        self, ledger: UsageLedger, backend: ChatBackend | None, clock: Clock, *, settle_window: timedelta
    ) -> None:
        self._ledger = ledger
        self._backend = backend
        self._clock = clock
        self._settle_window = settle_window

    async def sync_once(self) -> int:
        """Ask the engine for every pending wholesale cost and fill the ones that arrived.

        Returns the number filled.
        """
        if self._backend is None:
            return 0
        filled = 0
        since = self._clock.now() - self._settle_window
        for record in await self._ledger.pending_wholesale(settling_since=since):
            if record.job_id is None:
                continue
            try:
                cost = await self._backend.wholesale(record.user_id, record.job_id)
            except AppError as error:
                _LOG.warning(
                    "wholesale lookup failed",
                    extra={"event": "billing.wholesale_failed", "error": str(error)},
                )
                continue
            if cost.status in ("pending", "none"):
                continue  # "none" is the engine's "not yet known" for a paid job; never a zero
            if cost.status == record.wholesale.status and cost.amount == record.wholesale.amount:
                continue  # settled and unchanged
            filled_cost = cost.model_copy(
                update={
                    "updated_at": self._clock.now(),
                    "orchestrator_url": record.wholesale.orchestrator_url,
                }
            )
            await self._ledger.update_wholesale(record.message_id, filled_cost)
            filled += 1
        return filled
