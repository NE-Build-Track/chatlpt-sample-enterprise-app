"""Users, identities, conversations, messages, the usage ledger and the model info cache.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("disabled", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "identities",
        sa.Column("provider", sa.String(16), primary_key=True),
        sa.Column("subject", sa.String(255), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_identities_user", "identities", ["user_id"])
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_user_updated", "conversations", ["user_id", "updated_at"])
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=True),
        sa.Column("orchestrator_url", sa.String(255), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("reasoning_tokens", sa.Integer, nullable=True),
        sa.Column("cached_prompt_tokens", sa.Integer, nullable=True),
        sa.Column("retail_usd", sa.String(64), nullable=True),
        sa.Column("wholesale_status", sa.String(24), nullable=True),
        sa.Column("wholesale_usd", sa.String(64), nullable=True),
        sa.Column("wholesale_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])
    op.create_table(
        "usage_records",
        sa.Column("message_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False),
        sa.Column("completion_tokens", sa.Integer, nullable=False),
        sa.Column("reasoning_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cached_prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retail_usd", sa.String(64), nullable=False),
        sa.Column("wholesale_status", sa.String(24), nullable=False),
        sa.Column("wholesale_usd", sa.String(64), nullable=True),
        sa.Column("wholesale_orchestrator_url", sa.String(255), nullable=True),
        sa.Column("wholesale_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_usage_user_created", "usage_records", ["user_id", "created_at"])
    op.create_index("ix_usage_conversation", "usage_records", ["conversation_id"])
    op.create_index("ix_usage_wholesale_status", "usage_records", ["wholesale_status"])
    op.create_table(
        "model_info",
        sa.Column("app", sa.String(200), primary_key=True),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("max_model_len", sa.Integer, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in ("model_info", "usage_records", "messages", "conversations", "identities", "users"):
        op.drop_table(table)
