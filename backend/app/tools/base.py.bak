import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.services.constraint_manager import ConstraintView


class ToolArgs(BaseModel):
    """Base class for every tool's arguments. Unknown fields are an error."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ToolError(Exception):
    """An expected, user-presentable failure (bad input, missing document, ...)."""


@dataclass
class ToolContext:
    """Everything a tool may know. Note what is NOT here: no database session, no user,
    no file paths. Tools open their own short-lived sessions and only see their session."""

    session_id: uuid.UUID
    settings: Settings
    views: list[ConstraintView]  # constraints in force at the moment of the call
    step_index: int = 0
    task: str = ""
    history: list[dict] = field(default_factory=list)


@dataclass
class ToolResult:
    output: str
    sources: list[dict] = field(default_factory=list)
    simulated: bool = False
    retrieved_chunks: int = 0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema of the arguments
    side_effects: bool = False


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[ToolArgs]]
    side_effects: ClassVar[bool] = False  # True if the tool changes anything

    @abstractmethod
    async def run(self, args: Any, ctx: ToolContext) -> ToolResult: ...

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.args_model.model_json_schema(),
            side_effects=self.side_effects,
        )


def describe_tools(specs: list[ToolSpec] | tuple[ToolSpec, ...]) -> str:
    """Compact, model-readable list of the approved tools (built from our own schemas)."""
    lines = []
    for spec in specs:
        props = spec.parameters.get("properties", {})
        required = set(spec.parameters.get("required", []))
        parts = []
        for name, prop in props.items():
            kind = prop.get("type", "any")
            if kind == "array":
                kind = f"array of {prop.get('items', {}).get('type', 'any')}"
            optional = "" if name in required else f" (optional, default {prop.get('default')!r})"
            parts.append(f"{name}: {kind}{optional}")
        lines.append(f"- {spec.name}({', '.join(parts)}): {spec.description}")
    return "\n".join(lines)