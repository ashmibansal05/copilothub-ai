import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.approval import ApprovalKind, ApprovalStatus
from app.models.constraint import ConstraintAction, ConstraintStatus
from app.models.intervention import InterventionStatus, InterventionType, Priority
from app.models.memory import MemoryKind


class InterventionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    type: InterventionType
    content: str | None = Field(default=None, max_length=2000)
    target: str | None = Field(default=None, max_length=300)
    priority: Priority | None = None
    action: ConstraintAction | None = None  # for ADD_CONSTRAINT
    constraint_id: uuid.UUID | None = None  # for REMOVE_CONSTRAINT
    conflict_id: uuid.UUID | None = None  # for RESOLVE_CONFLICT
    winner_constraint_id: uuid.UUID | None = None  # for RESOLVE_CONFLICT (null = remove both)


class InterventionRead(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID | None
    username: str | None
    type: InterventionType
    content: str | None
    target: str | None
    priority: Priority
    status: InterventionStatus
    details: dict[str, Any]
    result: str | None
    created_at: datetime


class ConstraintCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    action: ConstraintAction
    target: str = Field(min_length=2, max_length=300)
    priority: Priority = Priority.MEDIUM


class ConstraintRead(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    type: Literal["CONSTRAINT"] = "CONSTRAINT"
    action: ConstraintAction
    target: str
    description: str
    priority: Priority
    status: ConstraintStatus
    created_by: uuid.UUID | None
    created_by_username: str | None
    created_at: datetime


class MemoryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: MemoryKind
    key: str | None
    content: str
    importance: int
    author: str | None
    created_at: datetime


class MemoryRead(BaseModel):
    constraints: list[ConstraintRead]
    items: list[MemoryItemRead]


class ApprovalRead(BaseModel):
    id: uuid.UUID
    kind: ApprovalKind
    status: ApprovalStatus
    payload: dict[str, Any]
    created_at: datetime