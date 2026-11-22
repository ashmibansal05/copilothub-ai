from dataclasses import dataclass, field
from typing import Any

from typing_extensions import TypedDict


class AgentGraphState(TypedDict, total=False):
    """State passed between LangGraph nodes. Nodes return partial updates."""

    task: str
    plan: list[str]
    step_index: int  # index (0-based) of the step to run next == steps completed
    steps_executed: int  # total act executions, including retries
    retries: int  # retries used for the current step
    observations: list[dict[str, Any]]
    last_result: dict[str, Any]
    confidence: float
    decision: str  # "continue" | "retry" | "replan" | "complete" | "revise"
    summary: str
    approval_round: int  # how many times the final draft was rejected
    approved: bool


@dataclass
class ApprovalDecision:
    approved: bool
    note: str | None = None
    by: str = ""


@dataclass
class HumanContext:
    """What humans have told the agent, selected for the current prompt."""

    constraints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)