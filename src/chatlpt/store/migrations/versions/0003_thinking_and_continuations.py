"""A thinking level per conversation; continuation segments and dropped-turn counts on messages (D24).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("thinking", sa.String(8), nullable=False, server_default="medium"))
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("continues_message_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("dropped_turns", sa.Integer, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("dropped_turns")
        batch.drop_column("continues_message_id")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("thinking")
