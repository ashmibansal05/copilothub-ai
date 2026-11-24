"""Durable collaborator requests used by the shared AI workflow."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class WorkflowRequest(Base):
    __tablename__ = "workflow_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
