from __future__ import annotations
"""team tasks, telegram groups, and message logs

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-28 17:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS task_code_seq START 1")

    op.create_table(
        "telegram_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("chat_type", sa.String(length=32), nullable=False, server_default="supergroup"),
        sa.Column("is_monitored", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("auto_create_tasks", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("default_assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("topic_filter", sa.Text(), nullable=True),
        sa.Column("messages_parsed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tasks_created", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_telegram_groups_chat_id", "telegram_groups", ["chat_id"])
    op.create_index("ix_telegram_groups_team_id", "telegram_groups", ["team_id"])
    op.create_index("ix_telegram_groups_client_id", "telegram_groups", ["client_id"])

    op.create_table(
        "team_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "code",
            sa.String(length=20),
            nullable=False,
            unique=True,
            server_default=sa.text("'TSK-' || lpad(nextval('task_code_seq')::text, 4, '0')"),
        ),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("raw_source_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="inbox"),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("category", sa.String(length=48), nullable=False, server_default="general"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("telegram_group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("telegram_groups.id"), nullable=True),
        sa.Column("telegram_chat_title", sa.String(length=256), nullable=True),
        sa.Column("telegram_sender", sa.String(length=128), nullable=True),
        sa.Column("telegram_message_link", sa.Text(), nullable=True),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("creator_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buyers.id"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("linked_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("requests.id"), nullable=True),
        sa.Column("checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("ai_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("comments", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_team_tasks_status", "team_tasks", ["status"])
    op.create_index("ix_team_tasks_priority", "team_tasks", ["priority"])
    op.create_index("ix_team_tasks_category", "team_tasks", ["category"])
    op.create_index("ix_team_tasks_telegram_group_id", "team_tasks", ["telegram_group_id"])
    op.create_index("ix_team_tasks_assignee_id", "team_tasks", ["assignee_id"])
    op.create_index("ix_team_tasks_team_id", "team_tasks", ["team_id"])
    op.create_index("ix_team_tasks_buyer_id", "team_tasks", ["buyer_id"])
    op.create_index("ix_team_tasks_client_id", "team_tasks", ["client_id"])

    op.create_table(
        "telegram_message_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("telegram_groups.id"), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_title", sa.String(length=256), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("reply_to_msg_id", sa.BigInteger(), nullable=True),
        sa.Column("sender_id", sa.BigInteger(), nullable=True),
        sa.Column("sender_username", sa.String(length=128), nullable=True),
        sa.Column("sender_name", sa.String(length=128), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("message_link", sa.Text(), nullable=True),
        sa.Column("is_actionable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ai_intent", sa.String(length=64), nullable=True),
        sa.Column("ai_confidence", sa.Integer(), nullable=True),
        sa.Column("ai_extracted", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("team_tasks.id"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_telegram_message_logs_group_id", "telegram_message_logs", ["group_id"])
    op.create_index("ix_telegram_message_logs_chat_id", "telegram_message_logs", ["chat_id"])
    op.create_index("ix_telegram_message_logs_message_id", "telegram_message_logs", ["message_id"])
    op.create_index("ix_telegram_message_logs_task_id", "telegram_message_logs", ["task_id"])
    op.create_index("ix_telegram_message_logs_sent_at", "telegram_message_logs", ["sent_at"])


def downgrade() -> None:
    op.drop_table("telegram_message_logs")
    op.drop_table("team_tasks")
    op.drop_table("telegram_groups")
    op.execute("DROP SEQUENCE IF EXISTS task_code_seq")
