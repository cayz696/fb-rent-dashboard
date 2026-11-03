from __future__ import annotations
"""add per-user theme preference

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-03 14:32:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("theme", sa.String(16), nullable=False, server_default=sa.text("'dark'")),
    )


def downgrade() -> None:
    op.drop_column("users", "theme")
