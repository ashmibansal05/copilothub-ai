"""final report columns on reports

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("kind", sa.String(length=10), nullable=False, server_default="DRAFT"))
    op.add_column("reports", sa.Column("engine", sa.String(length=80), nullable=True))
    op.add_column("reports", sa.Column("sections", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("reports", "sections")
    op.drop_column("reports", "engine")
    op.drop_column("reports", "kind")