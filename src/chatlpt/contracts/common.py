"""Base model and shared value types for every contract that crosses a boundary."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class Contract(BaseModel):
    """Frozen, strict base: the same class is used in-process and as the API schema."""

    model_config = ConfigDict(frozen=True, extra="forbid")


Currency = Literal["USD"]


class Money(Contract):
    """An exact amount in one currency. Serialized as a decimal string, never a float."""

    amount: Decimal
    currency: Currency = "USD"

    @field_validator("amount")
    @classmethod
    def _finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("amount must be finite")
        return value

    @classmethod
    def zero(cls, currency: Currency = "USD") -> "Money":
        return cls(amount=Decimal(0), currency=currency)

    def __add__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise ValueError("cannot add different currencies")
        return Money(amount=self.amount + other.amount, currency=self.currency)
