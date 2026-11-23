import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolSpecRead(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    side_effects: bool


class ToolExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_index: int
    tool_name: str
    arguments: dict[str, Any]
    status: str
    output_summary: str | None
    error: str | None
    simulated: bool
    duration_ms: int
    sources_count: int
    rejected_count: int
    created_at: datetime


class ReportSummary(BaseModel):
    id: uuid.UUID
    title: str
    format: str
    origin: str
    status: str
    chars: int
    created_at: datetime


class ReportDetail(ReportSummary):
    content: str