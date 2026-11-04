from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepResult:
    tool: str
    output: str
    success: bool = True
    sources: list[dict[str, Any]] = field(default_factory=list)
    simulated: bool = False
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class Evaluation:
    confidence: float
    ok: bool
    note: str = ""


class AgentBrain(ABC):
    """The 'thinking' part of the agent. The orchestrator (LangGraph) owns the
    loop, limits and events; a brain only answers four questions."""

    engine: str  # short id stored in the DB, e.g. "demo" or "ollama:qwen3"
    description: str  # shown to humans
    simulated: bool

    @abstractmethod
    async def make_plan(self, task: str, constraints: list[str], max_steps: int) -> list[str]: ...

    @abstractmethod
    def tool_for_step(self, step: str) -> str: ...

    @abstractmethod
    async def execute_step(
        self, task: str, step: str, history: list[dict], constraints: list[str]
    ) -> StepResult: ...

    @abstractmethod
    async def evaluate(
        self, task: str, step: str, result: StepResult, history: list[dict]
    ) -> Evaluation: ...

    @abstractmethod
    async def summarize(self, task: str, history: list[dict]) -> str: ...