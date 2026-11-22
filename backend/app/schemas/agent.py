import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.session import AgentStatus
from app.schemas.intervention import ApprovalRead, ConstraintRead, InterventionRead


class AgentStateRead(BaseModel):
    session_id: uuid.UUID
    status: AgentStatus
    current_task: str
    current_step: str | None = None
    step_index: int = 0  # steps completed so far
    total_steps: int = 0
    progress: int = 0
    confidence: float | None = None
    engine: str | None = None
    plan: list[str] = []
    recent_actions: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    active_constraints: list[ConstraintRead] = []
    human_interventions: list[InterventionRead] = []  # most recent first
    pending_approval: ApprovalRead | None = None


class AgentActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    step_index: int
    action_type: str
    tool_name: str | None
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    success: bool
    error: str | None
    duration_ms: int | None
    created_at: datetime


class LLMStatus(BaseModel):
    provider: str
    model: str
    demo_mode: bool
    reachable: bool
    model_available: bool
    ready: bool
    detail: str