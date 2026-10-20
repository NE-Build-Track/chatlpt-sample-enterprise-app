"""The engine adapter's pure parts: completion parsing, usage parsing, cost mapping and failure mapping."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from livepeer_builder.contracts import CostSummary, Failure, Job
from livepeer_builder.contracts.costs import AttemptCost, Fees, JobCost
from livepeer_builder.errors import JobFailed

from chatlpt.adapters.engine import (
    failure_from,
    network_totals_from,
    parse_completion,
    parse_usage,
    wholesale_from,
)
from chatlpt.contracts import Money, ReplyChunk, TokenUsage
from chatlpt.errors import ChatUnavailable, ReplyFailed

COMPLETION = {
    "id": "chatcmpl-1",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "Hi!", "reasoning": "greet back"},
        }
    ],
    "usage": {
        "prompt_tokens": 20,
        "completion_tokens": 7,
        "total_tokens": 27,
        "completion_tokens_details": {"reasoning_tokens": 4},
        "prompt_tokens_details": {"cached_tokens": 8},
    },
}


def test_parse_completion_emits_reasoning_content_usage_done() -> None:
    chunks = parse_completion(COMPLETION)
    assert chunks == [
        ReplyChunk(kind="reasoning", text="greet back"),
        ReplyChunk(kind="content", text="Hi!"),
        ReplyChunk(
            kind="usage",
            usage=TokenUsage(
                prompt_tokens=20, completion_tokens=7, reasoning_tokens=4, cached_prompt_tokens=8
            ),
        ),
        ReplyChunk(kind="done", finish_reason="stop"),
    ]


def test_parse_completion_tolerates_a_bare_or_odd_body() -> None:
    assert parse_completion({}) == [ReplyChunk(kind="done")]
    assert parse_usage({"prompt_tokens": "x", "completion_tokens": 1}) is None
    assert parse_usage(None) is None


def test_wholesale_from_maps_none_to_a_settled_zero_and_pending_to_pending() -> None:
    now = datetime.now(UTC)
    job_id = uuid4()
    none = JobCost(
        job_id=job_id, status="none", fees=Fees(), attempts=(), first_observed_at=None, updated_at=None
    )
    pending = none.model_copy(update={"status": "pending"})
    # builder-core's "none" means no attempt was paid: $0, settled (D29). Pending is still unknown.
    assert wholesale_from(none).status == "none" and wholesale_from(none).amount == Money(amount=Decimal(0))
    assert wholesale_from(pending).status == "pending" and wholesale_from(pending).amount is None
    observed = JobCost(
        job_id=job_id,
        status="observed",
        fees=Fees(fee_eth=Decimal("0.0000001"), fee_usd=Decimal("0.000111"), row_count=2),
        attempts=(AttemptCost(attempt_number=1, cost_class="delivered", fees=Fees()),),
        first_observed_at=now,
        updated_at=now,
    )
    cost = wholesale_from(observed)
    assert (
        cost.status == "delivered" and cost.amount is not None and cost.amount.amount == Decimal("0.000111")
    )
    uncertain = observed.model_copy(
        update={"attempts": (AttemptCost(attempt_number=1, cost_class="uncertain", fees=Fees()),)}
    )
    assert wholesale_from(uncertain).status == "uncertain"


def _failed_job(kind: str, *, payment_sent: bool, state: str = "failed") -> JobFailed:
    now = datetime.now(UTC)
    job = Job(
        id=uuid4(),
        actor_id="u",
        application_id="chatlpt",
        operation_ref=None,
        mode="immediate",
        app="a",
        capability=None,
        model=None,
        state=state,
        attempts=(),  # type: ignore[arg-type]
        failure=Failure(kind=kind, message=f"{kind} happened", payment_sent=payment_sent),  # type: ignore[arg-type]
        result=None,
        usage=None,
        created_at=now,
        completed_at=now,
    )
    return JobFailed(job)


def test_failure_mapping_distinguishes_unavailable_from_failed_after_payment() -> None:
    assert isinstance(failure_from(_failed_job("no_offering", payment_sent=False)), ChatUnavailable)
    assert isinstance(failure_from(_failed_job("payment", payment_sent=False)), ChatUnavailable)
    error = failure_from(_failed_job("runner_error", payment_sent=True))
    assert isinstance(error, ReplyFailed) and error.payment_sent and not error.uncertain
    timeout = failure_from(_failed_job("timeout", payment_sent=True, state="uncertain"))
    assert isinstance(timeout, ReplyFailed) and timeout.uncertain


def test_network_totals_split_delivered_from_failed_spend() -> None:
    now = datetime.now(UTC)
    summary = CostSummary(
        start=now,
        end=now,
        by_class={
            "delivered": Fees(fee_eth=Decimal(1), fee_usd=Decimal("0.0003"), row_count=3),
            "failed_after_payment": Fees(fee_eth=Decimal(1), fee_usd=Decimal("0.0001"), row_count=1),
            "uncertain": Fees(fee_eth=Decimal(1), fee_usd=Decimal("0.0002"), row_count=1),
            "pending": Fees(),
        },
        jobs_with_cost=5,
        jobs_pending=2,
    )
    totals = network_totals_from(summary)
    assert totals.delivered == Money(amount=Decimal("0.0003"))
    assert totals.failed == Money(amount=Decimal("0.0003")) and totals.pending == 2
