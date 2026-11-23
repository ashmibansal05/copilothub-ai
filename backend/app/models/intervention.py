import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class InterventionType(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CORRECT = "CORRECT"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    MODIFY_TASK = "MODIFY_TASK"
    ADD_INFORMATION = "ADD_INFORMATION"
    ADD_CONSTRAINT = "ADD_CONSTRAINT"
    REMOVE_CONSTRAINT = "REMOVE_CONSTRAINT"
    REJECT_SOURCE = "REJECT_SOURCE"
    CHANGE_SOURCE = "CHANGE_SOURCE"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    COMMENT = "COMMENT"
    RESOLVE_CONFLICT = "RESOLVE_CONFLICT"


class Priority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class InterventionStatus(str, enum.Enum):
    PENDING = "PENDING"  # reserved for the Phase 12 "ask for confirmation" flow
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"


class Intervention(Base):
    """One human action on a session. Doubles as the audit log of who did what."""

    __tablename__ = "interventions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[InterventionType] = mapped_column(
        Enum(InterventionType, native_enum=False, length=30), index=True
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    target: Mapped[str | None] = mapped_column(String(300), nullable=True)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, native_enum=False, length=10), default=Priority.MEDIUM
    )
    status: Mapped[InterventionStatus] = mapped_column(
        Enum(InterventionStatus, native_enum=False, length=12), default=InterventionStatus.APPLIED
    )
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User | None] = relationship()