"""telegram forum topic on messages and tasks

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-16 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Union[str, Sequence[str], None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("telegram_message_logs", sa.Column("topic_id", sa.BigInteger(), nullable=True))
    op.add_column("telegram_message_logs", sa.Column("topic_title", sa.String(length=256), nullable=True))
    op.add_column("team_tasks", sa.Column("telegram_topic_id", sa.BigInteger(), nullable=True))
    op.add_column("team_tasks", sa.Column("telegram_topic_title", sa.String(length=256), nullable=True))
    op.create_index("ix_telegram_message_logs_topic_id", "telegram_message_logs", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_telegram_message_logs_topic_id", table_name="telegram_message_logs")
    op.drop_column("team_tasks", "telegram_topic_title")
    op.drop_column("team_tasks", "telegram_topic_id")
    op.drop_column("telegram_message_logs", "topic_title")
    op.drop_column("telegram_message_logs", "topic_id")
