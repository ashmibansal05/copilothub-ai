import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConflictKind(str, enum.Enum):
    SOURCE_POLICY = "SOURCE_POLICY"  # two source rules that contradict each other


class ConflictStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class ConflictResolution(str, enum.Enum):
    KEEP_A = "KEEP_A"
    KEEP_B = "KEEP_B"
    REMOVE_BOTH = "REMOVE_BOTH"
    AUTO_CLOSED = "AUTO_CLOSED"  # one of the constraints was removed


class Conflict(Base):
    """Two active human instructions that contradict each other. Constraint A is the
    older one, B the newer one."""

    __tablename__ = "conflicts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ConflictKind] = mapped_column(Enum(ConflictKind, native_enum=False, length=20))
    status: Mapped[ConflictStatus] = mapped_column(
        Enum(ConflictStatus, native_enum=False, length=12), default=ConflictStatus.OPEN, index=True
    )
    constraint_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("constraints.id", ondelete="CASCADE"))
    constraint_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("constraints.id", ondelete="CASCADE"))
    # Result of the predefined priority rules (null = the rules cannot decide)
    suggested_winner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("constraints.id", ondelete="SET NULL"), nullable=True
    )
    requires_resolution: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_applied: Mapped[str] = mapped_column(Text)
    resolution: Mapped[ConflictResolution | None] = mapped_column(
        Enum(ConflictResolution, native_enum=False, length=12), nullable=True
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )