from pydantic import BaseModel, ConfigDict, Field
import uuid

from app.models.constraint import ConstraintAction
from app.models.intervention import InterventionType, Priority
from app.schemas.intervention import InterventionRead


class InstructionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=2, max_length=1000)
    dry_run: bool = False  # classify only; never apply


class Alternative(BaseModel):
    intent: str
    confidence: float


class Candidate(BaseModel):
    id: uuid.UUID
    description: str


class Proposal(BaseModel):
    """What the system would do. Becomes a normal intervention when applied or confirmed."""

    type: InterventionType
    content: str | None = None
    target: str | None = None
    action: ConstraintAction | None = None
    priority: Priority | None = None
    constraint_id: uuid.UUID | None = None
    candidates: list[Candidate] = []


class InstructionResult(BaseModel):
    text: str
    intent: str
    confidence: float
    method: str  # "model" or "rule"
    alternatives: list[Alternative]
    proposal: Proposal
    allowed: bool  # does the caller's role permit the proposed action?
    needs_confirmation: bool
    reason: str | None
    note: str | None
    applied: bool
    intervention: InterventionRead | None


class NLPStatus(BaseModel):
    available: bool
    embedder: str | None = None
    trained_at: str | None = None
    n_train: int | None = None
    n_test: int | None = None
    cv_accuracy: float | None = None
    cv_macro_f1: float | None = None
    held_out_accuracy: float | None = None
    dataset: str | None = None