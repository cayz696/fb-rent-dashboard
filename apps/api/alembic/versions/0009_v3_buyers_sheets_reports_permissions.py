"""v3 buyers teams sheets reports permissions

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-16 10:53:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("allowed_sections", postgresql.ARRAY(sa.String()), nullable=True))

    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("sheet_url", sa.Text(), nullable=True),
        sa.Column("sheet_gid", sa.String(length=32), nullable=True),
        sa.Column("sheet_balance", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("topup_total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("spend_total_sheet", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("fee_percent", sa.Numeric(precision=5, scale=2), server_default=sa.text("7.00"), nullable=False),
        sa.Column("last_sheet_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "buyers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("is_priority", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fbm_owner", sa.String(length=128), nullable=True),
        sa.Column("accounts_count", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_buyers_name", "buyers", ["name"])
    op.create_index("ix_buyers_team_id", "buyers", ["team_id"])

    op.create_table(
        "card_spend_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("card_id", sa.String(length=64), nullable=False),
        sa.Column("last4", sa.String(length=8), nullable=True),
        sa.Column("card_name", sa.Text(), nullable=True),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buyers.id"), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("account_name", sa.String(length=64), nullable=True),
        sa.Column("account_balance", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("spend_cumulative", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("spend_delta", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_card_spend_logs_card_id", "card_spend_logs", ["card_id"])
    op.create_index("ix_card_spend_logs_buyer_id", "card_spend_logs", ["buyer_id"])
    op.create_index("ix_card_spend_logs_team_id", "card_spend_logs", ["team_id"])
    op.create_index("ix_card_spend_logs_date", "card_spend_logs", ["date"])
    op.create_index("ix_card_spend_logs_recorded_at", "card_spend_logs", ["recorded_at"])

    op.create_table(
        "buyer_daily_spends",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buyers.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("spend_fbm", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("spend_sheet", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_buyer_daily_spends_buyer_id", "buyer_daily_spends", ["buyer_id"])
    op.create_index("ix_buyer_daily_spends_date", "buyer_daily_spends", ["date"])

    op.create_table(
        "fbm_reconciliations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("db_total_spend", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("fbm_total_spend", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("diff_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("discrepancies", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_index("ix_fbm_reconciliations_checked_at", "fbm_reconciliations", ["checked_at"])

    op.create_table(
        "expense_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("color", sa.String(length=32), nullable=False, server_default="#f59e0b"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("expense_categories.id"), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("spent_at", sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_expenses_category_id", "expenses", ["category_id"])
    op.create_index("ix_expenses_spent_at", "expenses", ["spent_at"])


def downgrade() -> None:
    op.drop_index("ix_expenses_spent_at", table_name="expenses")
    op.drop_index("ix_expenses_category_id", table_name="expenses")
    op.drop_table("expenses")
    op.drop_table("expense_categories")
    op.drop_index("ix_fbm_reconciliations_checked_at", table_name="fbm_reconciliations")
    op.drop_table("fbm_reconciliations")
    op.drop_index("ix_buyer_daily_spends_date", table_name="buyer_daily_spends")
    op.drop_index("ix_buyer_daily_spends_buyer_id", table_name="buyer_daily_spends")
    op.drop_table("buyer_daily_spends")
    op.drop_index("ix_card_spend_logs_recorded_at", table_name="card_spend_logs")
    op.drop_index("ix_card_spend_logs_date", table_name="card_spend_logs")
    op.drop_index("ix_card_spend_logs_team_id", table_name="card_spend_logs")
    op.drop_index("ix_card_spend_logs_buyer_id", table_name="card_spend_logs")
    op.drop_index("ix_card_spend_logs_card_id", table_name="card_spend_logs")
    op.drop_table("card_spend_logs")
    op.drop_index("ix_buyers_team_id", table_name="buyers")
    op.drop_index("ix_buyers_name", table_name="buyers")
    op.drop_table("buyers")
    op.drop_table("teams")
    op.drop_column("users", "allowed_sections")
