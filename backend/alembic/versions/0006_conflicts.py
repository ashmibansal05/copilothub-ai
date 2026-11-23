"""conflicts

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conflicts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("constraint_a_id", sa.Uuid(), nullable=False),
        sa.Column("constraint_b_id", sa.Uuid(), nullable=False),
        sa.Column("suggested_winner_id", sa.Uuid(), nullable=True),
        sa.Column("requires_resolution", sa.Boolean(), nullable=False),
        sa.Column("rule_applied", sa.Text(), nullable=False),
        sa.Column("resolution", sa.String(length=12), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["constraint_a_id"], ["constraints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["constraint_b_id"], ["constraints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suggested_winner_id"], ["constraints.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conflicts_session_id"), "conflicts", ["session_id"])
    op.create_index(op.f("ix_conflicts_status"), "conflicts", ["status"])


def downgrade() -> None:
    op.drop_table("conflicts")