"""Persistent coding artifacts and revisions.
Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("code_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(320), nullable=False),
        sa.Column("language", sa.String(40), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("validation_status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "path", name="uq_code_session_path"))
    op.create_index("ix_code_artifacts_session_id", "code_artifacts", ["session_id"])
    op.create_table("code_artifact_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("code_artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("validation_status", sa.String(30), nullable=False),
        sa.Column("validation_details", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("artifact_id", "version", name="uq_code_artifact_version"))
    op.create_index("ix_code_artifact_versions_artifact_id", "code_artifact_versions", ["artifact_id"])

def downgrade():
    op.drop_index("ix_code_artifact_versions_artifact_id", table_name="code_artifact_versions")
    op.drop_table("code_artifact_versions")
    op.drop_index("ix_code_artifacts_session_id", table_name="code_artifacts")
    op.drop_table("code_artifacts")
