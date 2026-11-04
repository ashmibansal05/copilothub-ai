import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.session import AgentStatus
from app.models.user import UserRole


class SessionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=3, max_length=120)
    task: str = Field(min_length=10, max_length=2000)


class JoinRequest(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def normalise_code(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{6,12}", v):
            raise ValueError("Invalid invite code format")
        return v


class MemberRead(BaseModel):
    user_id: uuid.UUID
    username: str
    full_name: str
    role: UserRole
    joined_at: datetime


class SessionSummary(BaseModel):
    id: uuid.UUID
    name: str
    task: str
    status: AgentStatus
    my_role: UserRole
    member_count: int
    owner_username: str
    created_at: datetime


class SessionDetail(SessionSummary):
    owner_id: uuid.UUID
    members: list[MemberRead]
    # Only populated for the OWNER; null for everyone else.
    editor_code: str | None = None
    viewer_code: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class InvitePreview(BaseModel):
    session_name: str
    task: str
    owner_name: str
    role: UserRole
    already_member: bool
    session_id: uuid.UUID | None = None  # only revealed if already a member


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    type: str
    payload: dict[str, Any]
    user_id: uuid.UUID | None
    created_at: datetime


class StateResponse(BaseModel):
    session_id: uuid.UUID
    status: AgentStatus
    previous_status: AgentStatus