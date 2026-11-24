import uuid
from datetime import datetime

from pydantic import BaseModel


class ConfidencePoint(BaseModel):
    step_index: int
    confidence: float


class RiskPoint(BaseModel):
    step_index: int
    probability: float
    level: str


class ToolStat(BaseModel):
    tool: str
    calls: int
    failures: int


class RiskSummary(BaseModel):
    data_source: str | None = None
    n: int = 0
    mean: float | None = None
    max: float | None = None
    last: float | None = None
    history: list[RiskPoint] = []
    observed_n: int = 0  # predictions whose outcome is known
    mean_when_intervened: float | None = None
    mean_when_not: float | None = None


class ProjectMetrics(BaseModel):
    """Factual workspace measures; not ML-based risk estimates."""
    files: int = 0
    versions_saved: int = 0
    syntax_validated: int = 0
    validation_failed: int = 0
    not_validated: int = 0
    code_reviews: int = 0
    revisions_requested: int = 0
    approval_status: str = "NONE"
    runtime_tested: bool = False


class SessionAnalytics(BaseModel):
    session_id: uuid.UUID
    name: str
    status: str
    engine: str | None
    created_at: datetime
    duration_seconds: float | None
    steps_planned: int
    steps_completed: int
    confidence_series: list[ConfidencePoint]
    avg_confidence: float | None
    final_confidence: float | None
    min_confidence: float | None
    interventions_total: int  # everything except comments
    comments: int
    corrective: int
    interventions_by_type: dict[str, int]
    interventions_by_user: dict[str, int]
    tool_calls: int
    tool_failures: int  # failed + rejected + timed out
    tool_failure_rate: float | None
    tools: list[ToolStat]
    failed_attempts: int
    repeat_evaluations: int
    recovered: bool  # had failed attempts and still completed
    approvals_requested: int
    approvals_approved: int
    approvals_rejected: int
    approvals_expired: int
    approval_rate: float | None
    conflicts_total: int
    conflicts_open: int
    conflicts_resolved: int
    sources_used: int
    sources_rejected: int
    source_rejection_rate: float | None
    sources_by_origin: dict[str, int]
    documents: int
    risk: RiskSummary
    project_metrics: ProjectMetrics | None = None


class SessionRow(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    duration_seconds: float | None
    interventions: int
    corrective: int
    tool_failures: int
    conflicts: int
    final_confidence: float | None


class HistogramBucket(BaseModel):
    label: str
    count: int


class ResearchGroup(BaseModel):
    label: str
    sessions: int
    completion_rate: float | None
    avg_duration_seconds: float | None
    avg_final_confidence: float | None


class Research(BaseModel):
    task_completion_rate: float | None
    human_correction_rate: float | None  # corrective interventions per completed step
    incorrect_actions_per_session: float | None  # corrective interventions + rejected approvals
    agent_recovery_rate: float | None
    avg_time_to_completion_seconds: float | None
    source_rejection_rate: float | None
    tool_failure_rate: float | None
    conflicts_per_session: float | None
    groups: list[ResearchGroup]
    notes: str


class AnalyticsOverview(BaseModel):
    generated_at: datetime
    sessions_total: int
    sessions_completed: int
    sessions_failed: int
    sessions_cancelled: int
    sessions_active: int
    success_rate: float | None
    avg_duration_seconds: float | None
    interventions_total: int
    interventions_corrective: int
    interventions_per_session: float | None
    interventions_by_type: dict[str, int]
    avg_confidence: float | None
    avg_final_confidence: float | None
    confidence_histogram: list[HistogramBucket]
    tool_calls: int
    tool_failures: int
    tool_failure_rate: float | None
    tools: list[ToolStat]
    approvals_requested: int
    approvals_approved: int
    approvals_rejected: int
    approval_rate: float | None
    conflicts_total: int
    conflicts_open: int
    sources_used: int
    sources_rejected: int
    source_rejection_rate: float | None
    prediction: RiskSummary
    research: Research
    recent_sessions: list[SessionRow]