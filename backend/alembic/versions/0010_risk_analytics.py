"""risk_predictions and analytics_records

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_predictions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("model_name", sa.String(length=40), nullable=False),
        sa.Column("data_source", sa.String(length=12), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_predictions_session_id"), "risk_predictions", ["session_id"])
    op.create_index(op.f("ix_risk_predictions_created_at"), "risk_predictions", ["created_at"])

    op.create_table(
        "analytics_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("steps_completed", sa.Integer(), nullable=False),
        sa.Column("interventions", sa.Integer(), nullable=False),
        sa.Column("corrective", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column("tool_failures", sa.Integer(), nullable=False),
        sa.Column("conflicts", sa.Integer(), nullable=False),
        sa.Column("approvals_requested", sa.Integer(), nullable=False),
        sa.Column("approvals_approved", sa.Integer(), nullable=False),
        sa.Column("sources_used", sa.Integer(), nullable=False),
        sa.Column("sources_rejected", sa.Integer(), nullable=False),
        sa.Column("final_confidence", sa.Float(), nullable=True),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analytics_records_session_id"), "analytics_records", ["session_id"], unique=True)


def downgrade() -> None:
    op.drop_table("analytics_records")
    op.drop_table("risk_predictions")