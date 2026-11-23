import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntentSample(Base):
    """Every free-text instruction that was classified, and what finally happened to it.
    This is the mechanism for collecting REAL training data for the classifier."""

    __tablename__ = "intent_samples"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text)
    predicted_intent: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(8))  # model | rule
    outcome: Mapped[str] = mapped_column(String(20))  # PROPOSED | AUTO_APPLIED | FAILED | DRY_RUN
    proposed_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # What the human finally did with it (set when a matching intervention is created)
    final_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )