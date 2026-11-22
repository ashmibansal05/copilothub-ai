import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.intervention import Priority
from app.models.user import User


class ConstraintAction(str, enum.Enum):
    EXCLUDE_SOURCE = "EXCLUDE_SOURCE"  # never use this source (enforced in code)
    INCLUDE_SOURCE = "INCLUDE_SOURCE"  # explicitly allowed / approved source
    PREFER_SOURCE = "PREFER_SOURCE"  # rank matching sources first (enforced in code)
    INSTRUCTION = "INSTRUCTION"  # free-text rule, advisory (followed by the LLM)


class ConstraintStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"
    # Phase 9 adds SUPERSEDED for constraints replaced by a conflict resolution.


class Constraint(Base):
    __tablename__ = "constraints"
    __table_args__ = (Index("ix_constraints_session_status", "session_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    intervention_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interventions.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[ConstraintAction] = mapped_column(
        Enum(ConstraintAction, native_enum=False, length=20)
    )
    target: Mapped[str] = mapped_column(String(300))
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, native_enum=False, length=10), default=Priority.MEDIUM
    )
    status: Mapped[ConstraintStatus] = mapped_column(
        Enum(ConstraintStatus, native_enum=False, length=12), default=ConstraintStatus.ACTIVE
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    removed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped[User | None] = relationship(foreign_keys="Constraint.created_by")