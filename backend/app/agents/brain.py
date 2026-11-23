from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.tools.base import ToolSpec


@dataclass
class StepResult:
    tool: str
    output: str
    success: bool = True
    sources: list[dict[str, Any]] = field(default_factory=list)
    rejected_sources: list[dict[str, Any]] = field(default_factory=list)  # filled by the orchestrator
    simulated: bool = False
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class Evaluation:
    confidence: float
    ok: bool
    note: str = ""


# ---- the tool-use protocol between a brain and the orchestrator ----
@dataclass
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class FinalAnswer:
    text: str


@dataclass
class ToolObservation:
    """What a brain sees of an earlier tool call in the same step."""

    tool: str
    arguments: dict[str, Any]
    ok: bool
    output: str


AgentAction = ToolCall | FinalAnswer


class AgentBrain(ABC):
    """The 'thinking' part of the agent. The orchestrator (LangGraph) owns the loop, limits,
    tool execution, constraint enforcement and events; a brain only decides things.

    `constraints` are human rules rendered as text; `notes` are relevant human corrections
    chosen by the MemoryManager."""

    engine: str  # short id stored in the DB, e.g. "demo" or "ollama:qwen3"
    description: str  # shown to humans
    simulated: bool
    uses_tools: bool = False  # True: the orchestrator runs the tool loop (next_action)

    @abstractmethod
    async def make_plan(
        self, task: str, constraints: list[str], max_steps: int, notes: list[str] | None = None
    ) -> list[str]: ...

    @abstractmethod
    def tool_for_step(self, step: str) -> str: ...

    @abstractmethod
    async def execute_step(
        self, task: str, step: str, history: list[dict], constraints: list[str],
        notes: list[str] | None = None, documents: list[dict] | None = None,
    ) -> StepResult:
        """Single-shot step (no tool loop). Used when AGENT_TOOLS_ENABLED=false."""

    async def next_action(
        self, task: str, step: str, observations: list[ToolObservation], constraints: list[str],
        notes: list[str] | None = None, tools: list[ToolSpec] | tuple[ToolSpec, ...] = (),
        force_final: bool = False,
    ) -> AgentAction:
        """Tool-use protocol: return ONE tool call, or the final findings for the step.
        With force_final=True the brain must return a FinalAnswer."""
        raise NotImplementedError(f"{type(self).__name__} does not support tools")

    @abstractmethod
    async def evaluate(
        self, task: str, step: str, result: StepResult, history: list[dict]
    ) -> Evaluation: ...

    @abstractmethod
    async def summarize(
        self, task: str, history: list[dict], constraints: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> str: ...