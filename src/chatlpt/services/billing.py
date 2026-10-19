"""The retail book: tokens times list price (D4). Exact Decimal arithmetic; never derived from wholesale."""

from decimal import Decimal

from chatlpt.contracts import Money, TokenUsage
from chatlpt.protocols import PriceSource

MILLION = Decimal(1_000_000)


class BillingService:
    def __init__(self, prices: PriceSource) -> None:
        self._prices = prices

    def retail(self, usage: TokenUsage, *, thinking: bool) -> Money:
        """Prompt tokens split into cached and uncached; output at the thinking rate when reasoning ran."""
        table = self._prices.table()
        cached = min(usage.cached_prompt_tokens, usage.prompt_tokens)
        uncached = usage.prompt_tokens - cached
        cached_rate = table.cached_input_per_m if table.cached_input_per_m is not None else table.input_per_m
        output_rate = (
            table.thinking_output_per_m
            if thinking and table.thinking_output_per_m is not None
            else table.output_per_m
        )
        amount = (
            Decimal(uncached) * table.input_per_m
            + Decimal(cached) * cached_rate
            + Decimal(usage.completion_tokens) * output_rate
        ) / MILLION
        return Money(amount=amount, currency=table.currency)
