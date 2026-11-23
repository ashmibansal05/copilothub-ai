import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.conflict import ConflictKind, ConflictResolution, ConflictStatus
from app.models.constraint import ConstraintAction
from app.models.intervention import Priority


class ConflictSide(BaseModel):
    constraint_id: uuid.UUID
    action: ConstraintAction
    target: str
    description: str
    priority: Priority
    created_by_username: str | None
    created_by_role: str | None
    still_active: bool


class ConflictRead(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    kind: ConflictKind
    status: ConflictStatus
    constraint_a: ConflictSide  # the older instruction
    constraint_b: ConflictSide  # the newer instruction
    requires_resolution: bool
    rule_applied: str
    provisional: str | None  # what is enforced right now while the conflict is open
    suggested_winner_id: uuid.UUID | None
    resolution: ConflictResolution | None
    resolution_note: str | None
    resolved_by_username: str | None
    created_at: datetime
    resolved_at: datetime | None


class ResolveRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    # One of the two constraints to keep, or null to remove both
    winner_constraint_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)