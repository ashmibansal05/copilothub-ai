import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalyticsRecord(Base):
    """A durable snapshot of a session's metrics, written when the session ends. This is the
    table to export for the research evaluation."""

    __tablename__ = "analytics_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24))
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    steps_completed: Mapped[int] = mapped_column(Integer, default=0)
    interventions: Mapped[int] = mapped_column(Integer, default=0)
    corrective: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_failures: Mapped[int] = mapped_column(Integer, default=0)
    conflicts: Mapped[int] = mapped_column(Integer, default=0)
    approvals_requested: Mapped[int] = mapped_column(Integer, default=0)
    approvals_approved: Mapped[int] = mapped_column(Integer, default=0)
    sources_used: Mapped[int] = mapped_column(Integer, default=0)
    sources_rejected: Mapped[int] = mapped_column(Integer, default=0)
    final_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )