import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MemoryKind(str, enum.Enum):
    FACT = "FACT"
    CORRECTION = "CORRECTION"
    DECISION = "DECISION"
    REJECTED_SOURCE = "REJECTED_SOURCE"
    APPROVED_SOURCE = "APPROVED_SOURCE"


class MemoryItem(Base):
    """Structured long-term memory for a session. (Constraints live in their own table.)"""

    __tablename__ = "memory_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[MemoryKind] = mapped_column(Enum(MemoryKind, native_enum=False, length=20))
    key: Mapped[str | None] = mapped_column(String(300), nullable=True)  # source name for source kinds
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 1 (minor) .. 5 (critical)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    author: Mapped[str | None] = mapped_column(String(50), nullable=True)  # username snapshot
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    intervention_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interventions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )