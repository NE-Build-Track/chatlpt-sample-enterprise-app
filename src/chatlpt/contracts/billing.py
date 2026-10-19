"""Billing contracts: tokens, prices and the two books (docs/product-specs/chatlpt.md#usage-and-cost).

Retail is tokens times list price. Wholesale is the engine's network cost. Neither is derived from the
other, and a wholesale cost that has not arrived is ``pending``, never zero.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from chatlpt.contracts.common import Contract, Currency, Money


class TokenUsage(Contract):
    """Token counts as the runner reported them in its final chunk (D19)."""

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)  # included in completion_tokens when reported
    cached_prompt_tokens: int = Field(default=0, ge=0)  # included in prompt_tokens when reported

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class PriceTable(Contract):
    """List prices per million tokens for one model, with provenance (D4)."""

    model: str
    vendor: str
    region: str
    currency: Currency
    input_per_m: Decimal
    output_per_m: Decimal
    cached_input_per_m: Decimal | None = None
    thinking_output_per_m: Decimal | None = None
    source_url: str
    observed_at: datetime


WholesaleStatus = Literal["none", "pending", "delivered", "failed_after_payment", "uncertain"]


class WholesaleCost(Contract):
    """The engine's network cost for one job. ``none`` means the job never reached payment."""

    status: WholesaleStatus
    amount: Money | None = None  # present only when status is delivered, failed_after_payment or uncertain
    orchestrator_url: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def pending(cls) -> "WholesaleCost":
        return cls(status="pending")


LedgerKind = Literal["chat", "image"]


class ImagePriceTable(Contract):
    """A vendor's list price per megapixel for an image model, with provenance (D25)."""

    model: str
    vendor: str
    region: str
    currency: Currency
    unit: Literal["megapixel"]
    price_per_unit: Decimal
    rounding: str
    source_url: str
    observed_at: datetime


class UsageRecord(Contract):
    """One paid job's entry in the ledger: both books, one job id.

    ``message_id`` is the record key: the assistant message for a chat job, the image id for an
    image job (``kind``).
    """

    message_id: UUID
    kind: LedgerKind = "chat"
    user_id: UUID
    conversation_id: UUID
    job_id: UUID | None
    usage: TokenUsage
    retail: Money
    wholesale: WholesaleCost
    created_at: datetime


class UsageTotals(Contract):
    """Aggregates over a period. Pending wholesale rows are counted, never folded into the total."""

    user_id: UUID | None
    start: datetime
    end: datetime
    replies: int
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    retail: Money
    wholesale: Money
    wholesale_pending: int
    images: int = 0
