"""Row ↔ contract conversion. Decimals are text in SQLite; datetimes come back naive and are made UTC."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from chatlpt.contracts import (
    Conversation,
    Message,
    ModelInfo,
    Money,
    TokenUsage,
    UsageRecord,
    User,
    WholesaleCost,
)
from chatlpt.utils import utc


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _money(value: Any) -> Money | None:
    amount = _dec(value)
    return None if amount is None else Money(amount=amount, currency="USD")


def user_from(row: Mapping[Any, Any]) -> User:
    return User(
        id=UUID(row["id"]),
        email=row["email"],
        display_name=row["display_name"],
        is_admin=bool(row["is_admin"]),
        disabled=bool(row["disabled"]),
        created_at=utc(row["created_at"]),
    )


def conversation_from(row: Mapping[Any, Any]) -> Conversation:
    return Conversation(
        id=UUID(row["id"]),
        user_id=UUID(row["user_id"]),
        title=row["title"],
        thinking=row["thinking"] or "medium",
        created_at=utc(row["created_at"]),
        updated_at=utc(row["updated_at"]),
    )


def usage_from(row: Mapping[Any, Any]) -> TokenUsage | None:
    if row["prompt_tokens"] is None or row["completion_tokens"] is None:
        return None
    return TokenUsage(
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        reasoning_tokens=row["reasoning_tokens"] or 0,
        cached_prompt_tokens=row["cached_prompt_tokens"] or 0,
    )


def wholesale_from(row: Mapping[Any, Any], *, url_key: str | None = None) -> WholesaleCost | None:
    status = row["wholesale_status"]
    if status is None:
        return None
    updated = row["wholesale_updated_at"]
    return WholesaleCost(
        status=status,
        amount=_money(row["wholesale_usd"]),
        orchestrator_url=row.get(url_key) if url_key else None,
        updated_at=None if updated is None else utc(updated),
    )


def message_from(row: Mapping[Any, Any]) -> Message:
    return Message(
        id=UUID(row["id"]),
        conversation_id=UUID(row["conversation_id"]),
        role=row["role"],
        content=row["content"],
        reasoning=row["reasoning"],
        state=row["state"],
        job_id=None if row["job_id"] is None else UUID(row["job_id"]),
        orchestrator_url=row["orchestrator_url"],
        usage=usage_from(row),
        retail=_money(row["retail_usd"]),
        wholesale=wholesale_from(row),
        finish_reason=row["finish_reason"],
        continues_message_id=None
        if row["continues_message_id"] is None
        else UUID(row["continues_message_id"]),
        dropped_turns=row["dropped_turns"],
        error=row["error"],
        created_at=utc(row["created_at"]),
    )


def message_values(message: Message) -> dict[str, Any]:
    usage = message.usage
    wholesale = message.wholesale
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "role": message.role,
        "content": message.content,
        "reasoning": message.reasoning,
        "state": message.state,
        "job_id": None if message.job_id is None else str(message.job_id),
        "orchestrator_url": message.orchestrator_url,
        "prompt_tokens": None if usage is None else usage.prompt_tokens,
        "completion_tokens": None if usage is None else usage.completion_tokens,
        "reasoning_tokens": None if usage is None else usage.reasoning_tokens,
        "cached_prompt_tokens": None if usage is None else usage.cached_prompt_tokens,
        "retail_usd": None if message.retail is None else str(message.retail.amount),
        "wholesale_status": None if wholesale is None else wholesale.status,
        "wholesale_usd": None
        if wholesale is None or wholesale.amount is None
        else str(wholesale.amount.amount),
        "wholesale_updated_at": None if wholesale is None else wholesale.updated_at,
        "finish_reason": message.finish_reason,
        "continues_message_id": None
        if message.continues_message_id is None
        else str(message.continues_message_id),
        "dropped_turns": message.dropped_turns,
        "error": message.error,
        "created_at": message.created_at,
    }


def usage_record_from(row: Mapping[Any, Any]) -> UsageRecord:
    usage = usage_from(row)
    assert usage is not None  # the ledger columns are NOT NULL
    wholesale = wholesale_from(row, url_key="wholesale_orchestrator_url")
    assert wholesale is not None
    return UsageRecord(
        message_id=UUID(row["message_id"]),
        user_id=UUID(row["user_id"]),
        conversation_id=UUID(row["conversation_id"]),
        job_id=None if row["job_id"] is None else UUID(row["job_id"]),
        usage=usage,
        retail=Money(amount=Decimal(row["retail_usd"]), currency="USD"),
        wholesale=wholesale,
        created_at=utc(row["created_at"]),
    )


def usage_record_values(record: UsageRecord) -> dict[str, Any]:
    return {
        "message_id": str(record.message_id),
        "user_id": str(record.user_id),
        "conversation_id": str(record.conversation_id),
        "job_id": None if record.job_id is None else str(record.job_id),
        "prompt_tokens": record.usage.prompt_tokens,
        "completion_tokens": record.usage.completion_tokens,
        "reasoning_tokens": record.usage.reasoning_tokens,
        "cached_prompt_tokens": record.usage.cached_prompt_tokens,
        "retail_usd": str(record.retail.amount),
        "wholesale_status": record.wholesale.status,
        "wholesale_usd": None if record.wholesale.amount is None else str(record.wholesale.amount.amount),
        "wholesale_orchestrator_url": record.wholesale.orchestrator_url,
        "wholesale_updated_at": record.wholesale.updated_at,
        "created_at": record.created_at,
    }


def model_info_from(row: Mapping[Any, Any]) -> ModelInfo:
    return ModelInfo(
        app=row["app"],
        model_id=row["model_id"],
        max_model_len=row["max_model_len"],
        observed_at=utc(row["observed_at"]),
    )
