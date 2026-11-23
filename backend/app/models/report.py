import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    """Either a draft saved by the agent's save_report tool (kind DRAFT) or the structured
    final research report (kind FINAL, with `sections`)."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)  # Markdown rendering, shown as plain text
    format: Mapped[str] = mapped_column(String(12), default="markdown")
    origin: Mapped[str] = mapped_column(String(12), default="AGENT")  # AGENT | SYSTEM
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")
    kind: Mapped[str] = mapped_column(String(10), default="DRAFT", server_default="DRAFT")  # DRAFT | FINAL
    engine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sections: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{key, title, body}]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )