"""The retail book: tokens times list price, exact Decimal, thinking and cache aware."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from chatlpt.contracts import TokenUsage
from chatlpt.services.billing import BillingService
from chatlpt.testing import StaticPrices


def test_retail_prices_input_and_output_separately() -> None:
    billing = BillingService(StaticPrices())
    cost = billing.retail(TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000), thinking=False)
    assert cost.amount == Decimal("3.50")
    assert cost.currency == "USD"


def test_cached_prompt_tokens_use_the_cache_rate() -> None:
    billing = BillingService(StaticPrices())
    usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=0, cached_prompt_tokens=500_000)
    assert billing.retail(usage, thinking=False).amount == Decimal("0.30")  # 0.5M*0.50 + 0.5M*0.10


def test_reasoning_tokens_are_output_when_no_thinking_rate_is_listed() -> None:
    billing = BillingService(StaticPrices())
    usage = TokenUsage(prompt_tokens=0, completion_tokens=200, reasoning_tokens=150)
    assert billing.retail(usage, thinking=True).amount == Decimal("200") * Decimal("3.00") / Decimal(
        1_000_000
    )


def test_thinking_rate_applies_when_listed_and_reasoning_ran() -> None:
    table = StaticPrices().table().model_copy(update={"thinking_output_per_m": Decimal("6.00")})
    billing = BillingService(StaticPrices(table))
    usage = TokenUsage(prompt_tokens=0, completion_tokens=1_000_000)
    assert billing.retail(usage, thinking=True).amount == Decimal("6.00")
    assert billing.retail(usage, thinking=False).amount == Decimal("3.00")


@given(
    prompt=st.integers(min_value=0, max_value=10**7),
    completion=st.integers(min_value=0, max_value=10**7),
    cached=st.integers(min_value=0, max_value=10**7),
)
def test_retail_is_exact_and_never_negative(prompt: int, completion: int, cached: int) -> None:
    billing = BillingService(StaticPrices())
    usage = TokenUsage(prompt_tokens=prompt, completion_tokens=completion, cached_prompt_tokens=cached)
    cost = billing.retail(usage, thinking=False)
    assert cost.amount >= 0
    assert cost.amount == cost.amount.quantize(
        Decimal("0.0000000001")
    )  # no binary noise: exact tenths of a micro-dollar
