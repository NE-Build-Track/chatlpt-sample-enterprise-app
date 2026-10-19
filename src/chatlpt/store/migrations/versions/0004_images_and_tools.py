"""Tool-call messages, generated images and the ledger kind (D25).

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("kind", sa.String(16), nullable=False, server_default="text"))
        batch.add_column(sa.Column("tool_calls", sa.Text, nullable=True))
    with op.batch_alter_table("usage_records") as batch:
        batch.add_column(sa.Column("kind", sa.String(8), nullable=False, server_default="chat"))
    op.create_table(
        "images",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("image_size", sa.String(32), nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("seed", sa.Integer, nullable=True),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=True),
        sa.Column("orchestrator_url", sa.String(255), nullable=True),
        sa.Column("retail_usd", sa.String(64), nullable=True),
        sa.Column("wholesale_status", sa.String(24), nullable=True),
        sa.Column("wholesale_usd", sa.String(64), nullable=True),
        sa.Column("wholesale_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_images_message", "images", ["message_id"])
    op.create_index("ix_images_created", "images", ["created_at"])


def downgrade() -> None:
    op.drop_table("images")
    with op.batch_alter_table("usage_records") as batch:
        batch.drop_column("kind")
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("tool_calls")
        batch.drop_column("kind")
