"""Durable queued collaborator requests.

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workflow_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("requested_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_workflow_requests_session_id", "workflow_requests", ["session_id"])


def downgrade():
    op.drop_index("ix_workflow_requests_session_id", table_name="workflow_requests")
    op.drop_table("workflow_requests")
