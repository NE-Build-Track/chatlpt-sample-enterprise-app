"""The app database schema. Decimals are stored as text so they stay exact in SQLite.

A schema change needs a migration in ``migrations/versions`` and ``chatlpt gen-docs``
(tests/store/test_durability.py catches drift).
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, MetaData, String, Table, Text

VERSION_TABLE = "chatlpt_alembic_version"
ID = 36
DEC = 64  # a Decimal as text

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("display_name", String(120), nullable=False, server_default=""),
    Column("password_hash", String(255), nullable=True),
    Column("is_admin", Boolean, nullable=False, server_default="0"),
    Column("disabled", Boolean, nullable=False, server_default="0"),
    Column("email_verified", Boolean, nullable=False, server_default="0"),  # a provider confirmed it (D26)
    Column("created_at", DateTime(timezone=True), nullable=False),
)

identities = Table(
    "identities",
    metadata,
    Column("provider", String(16), primary_key=True),
    Column("subject", String(255), primary_key=True),
    Column("user_id", String(ID), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("email", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_identities_user", "user_id"),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("user_id", String(ID), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("title", String(200), nullable=False),
    Column("thinking", String(8), nullable=False, server_default="medium"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_conversations_user_updated", "user_id", "updated_at"),
)

messages = Table(
    "messages",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("conversation_id", String(ID), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
    Column("role", String(16), nullable=False),
    Column("kind", String(16), nullable=False, server_default="text"),
    Column("content", Text, nullable=False),
    Column("reasoning", Text, nullable=True),
    Column("tool_calls", Text, nullable=True),  # JSON list of {id, name, arguments}
    Column("state", String(16), nullable=False),
    Column("job_id", String(ID), nullable=True),
    Column("orchestrator_url", String(255), nullable=True),
    Column("prompt_tokens", Integer, nullable=True),
    Column("completion_tokens", Integer, nullable=True),
    Column("reasoning_tokens", Integer, nullable=True),
    Column("cached_prompt_tokens", Integer, nullable=True),
    Column("retail_usd", String(DEC), nullable=True),
    Column("wholesale_status", String(24), nullable=True),
    Column("wholesale_usd", String(DEC), nullable=True),
    Column("wholesale_updated_at", DateTime(timezone=True), nullable=True),
    Column("finish_reason", String(32), nullable=True),
    Column("continues_message_id", String(ID), nullable=True),
    Column("dropped_turns", Integer, nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_messages_conversation_created", "conversation_id", "created_at"),
)

# The ledger outlives conversations (deleting a chat keeps its usage), so no foreign keys here.
usage_records = Table(
    "usage_records",
    metadata,
    Column("message_id", String(ID), primary_key=True),  # the record key: message id or image id
    Column("kind", String(8), nullable=False, server_default="chat"),
    Column("user_id", String(ID), nullable=False),
    Column("conversation_id", String(ID), nullable=False),
    Column("job_id", String(ID), nullable=True),
    Column("prompt_tokens", Integer, nullable=False),
    Column("completion_tokens", Integer, nullable=False),
    Column("reasoning_tokens", Integer, nullable=False, server_default="0"),
    Column("cached_prompt_tokens", Integer, nullable=False, server_default="0"),
    Column("retail_usd", String(DEC), nullable=False),
    Column("wholesale_status", String(24), nullable=False),
    Column("wholesale_usd", String(DEC), nullable=True),
    Column("wholesale_orchestrator_url", String(255), nullable=True),
    Column("wholesale_updated_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_usage_user_created", "user_id", "created_at"),
    Index("ix_usage_conversation", "conversation_id"),
    Index("ix_usage_wholesale_status", "wholesale_status"),
)

images = Table(
    "images",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("message_id", String(ID), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
    Column("conversation_id", String(ID), nullable=False),
    Column("user_id", String(ID), nullable=False),
    Column("prompt", Text, nullable=False),
    Column("image_size", String(32), nullable=False),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column("seed", Integer, nullable=True),
    Column("content_type", String(64), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("path", String(255), nullable=False),
    Column("job_id", String(ID), nullable=True),
    Column("orchestrator_url", String(255), nullable=True),
    Column("retail_usd", String(DEC), nullable=True),
    Column("wholesale_status", String(24), nullable=True),
    Column("wholesale_usd", String(DEC), nullable=True),
    Column("wholesale_updated_at", DateTime(timezone=True), nullable=True),
    Column("expired_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_images_message", "message_id"),
    Index("ix_images_created", "created_at"),
)

model_info = Table(
    "model_info",
    metadata,
    Column("app", String(200), primary_key=True),
    Column("model_id", String(200), nullable=False),
    Column("max_model_len", Integer, nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
)
