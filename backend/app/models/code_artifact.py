"""Session-scoped code files and immutable historical versions."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class CodeArtifact(Base):
    __tablename__ = "code_artifacts"
    __table_args__ = (UniqueConstraint("session_id", "path", name="uq_code_session_path"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(320))
    language: Mapped[str] = mapped_column(String(40), default="text")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    validation_status: Mapped[str] = mapped_column(String(30), default="NOT_VALIDATED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class CodeArtifactVersion(Base):
    __tablename__ = "code_artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "version", name="uq_code_artifact_version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("code_artifacts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="AI")
    validation_status: Mapped[str] = mapped_column(String(30), default="NOT_VALIDATED")
    validation_details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
