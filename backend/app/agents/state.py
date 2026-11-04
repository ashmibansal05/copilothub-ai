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
    decision: str  # "continue" | "retry" | "complete"
    summary: str