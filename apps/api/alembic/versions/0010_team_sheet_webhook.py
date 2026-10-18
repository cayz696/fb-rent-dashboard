"""team sheet webhook url

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-18 11:46:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("sheet_webhook_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "sheet_webhook_url")
