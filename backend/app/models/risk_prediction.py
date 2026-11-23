import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskPrediction(Base):
    """What the predictor said after each evaluated step. Compared later with what humans
    actually did, this shows how the model behaves on real sessions."""

    __tablename__ = "risk_predictions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    step_index: Mapped[int] = mapped_column(Integer)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # time of the evaluated step
    probability: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(8))
    model_name: Mapped[str] = mapped_column(String(40))
    data_source: Mapped[str] = mapped_column(String(12))  # synthetic | real | mixed
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )