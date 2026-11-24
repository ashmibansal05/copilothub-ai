import asyncio
import ast
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.services.constraint_manager import ConstraintManager
from app.tools.base import Tool, ToolContext, ToolError, ToolSpec

logger = logging.getLogger("copilothub.tools")

MAX_ARGUMENT_CHARS = 4000


@dataclass
class ToolOutcome:
    tool: str
    ok: bool
    status: str  # SUCCESS | ERROR | REJECTED | TIMEOUT
    output: str
    arguments: dict
    sources: list = field(default_factory=list)
    rejected_sources: list = field(default_factory=list)
    simulated: bool = False
    retrieved_chunks: int = 0
    duration_ms: int = 0
    error: str | None = None
    data: dict = field(default_factory=dict)


def preview_arguments(raw: Any) -> dict:
    """A short, safe copy of the arguments for logs and events."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for key, value in list(raw.items())[:8]:
        if isinstance(value, str):
            out[str(key)[:40]] = value[:200]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[str(key)[:40]] = value
        else:
            out[str(key)[:40]] = str(value)[:200]
    return out


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:5]:
        where = ".".join(str(p) for p in err["loc"]) or "arguments"
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)


def normalize_known_llm_mistakes(name: str, raw: dict) -> tuple[dict, list[str]]:
    """Repair only known, low-risk model formatting errors.

    This is NOT a validation bypass; the result must still pass the original
    Pydantic schema. Do not correct unknown tools or unknown parameters.
    """
    args = dict(raw)
    repairs: list[str] = []

    bounds = {"search_web": "max_results", "retrieve_documents": "k"}
    bound_name = bounds.get(name)
    if bound_name and type(args.get(bound_name)) is int and args[bound_name] > 8:
        repairs.append(f"{bound_name}: {args[bound_name]} -> 8")
        args[bound_name] = 8

    if name == "compare_sources":
        for key in ("topics", "criteria"):
            value = args.get(key)
            if not isinstance(value, str) or len(value) > 1000:
                continue
            stripped = value.strip()
            if not (stripped.startswith("[") and stripped.endswith("]")):
                continue
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                try:
                    parsed = ast.literal_eval(stripped)
                except (ValueError, SyntaxError, TypeError, RecursionError):
                    continue
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                args[key] = parsed
                repairs.append(f"{key}: encoded string -> JSON array")

    return args, repairs


class ToolRegistry:
    """The ONLY way the agent can act. Anything that is not registered here does not exist
    for the model: there is no shell, no arbitrary file access, no URL fetching."""

    def __init__(self, tools: list[Tool], enabled: set[str] | None = None) -> None:
        self._tools = {t.name: t for t in tools if enabled is None or t.name in enabled}

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [t.spec() for t in self._tools.values()]

    async def execute(self, name: Any, raw_arguments: Any, ctx: ToolContext) -> ToolOutcome:
        """Look up, validate, run (with timeout), filter sources, cap output. Never raises
        (except for cancellation): every failure becomes an outcome the model can read."""
        started = time.monotonic()
        label = str(name)[:60]
        preview = preview_arguments(raw_arguments)

        def done(status: str, output: str = "", error: str | None = None, **extra) -> ToolOutcome:
            return ToolOutcome(
                tool=label, ok=status == "SUCCESS", status=status,
                output=output if status == "SUCCESS" else (error or output),
                arguments=preview, error=error,
                duration_ms=int((time.monotonic() - started) * 1000), **extra,
            )

        tool = self._tools.get(name) if isinstance(name, str) else None
        if tool is None:
            return done("REJECTED", error=f"Unknown or disabled tool '{label}'. Available tools: {', '.join(self._tools)}")
        if not isinstance(raw_arguments, dict):
            return done("REJECTED", error="Tool arguments must be a JSON object")
        try:
            if len(json.dumps(raw_arguments, default=str)) > MAX_ARGUMENT_CHARS:
                return done("REJECTED", error="Tool arguments are too large")
        except (TypeError, ValueError):
            return done("REJECTED", error="Tool arguments are not valid JSON")
        effective, repairs = normalize_known_llm_mistakes(name, raw_arguments)
        if repairs:
            logger.info("Normalized tool %s arguments: %s", label, "; ".join(repairs))
            preview = preview_arguments(effective)
        try:
            args = tool.args_model.model_validate(effective)
        except ValidationError as exc:
            return done("REJECTED", error=f"Invalid arguments: {_format_validation_error(exc)}")

        try:
            result = await asyncio.wait_for(tool.run(args, ctx), timeout=ctx.settings.tool_timeout_seconds)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return done("TIMEOUT", error=f"The tool timed out after {ctx.settings.tool_timeout_seconds:g}s")
        except ToolError as exc:
            return done("ERROR", error=str(exc) or "The tool failed")
        except Exception:
            logger.exception("Tool %s crashed", label)
            return done("ERROR", error="The tool failed unexpectedly")  # internals are never shown to the model

        # Enforcement point: the CURRENT human rules decide which sources survive,
        # whatever the tool returned.
        allowed, rejected = ConstraintManager.filter_sources(ctx.views, result.sources)
        return done(
            "SUCCESS",
            output=result.output[: ctx.settings.tool_output_max_chars],
            sources=allowed, rejected_sources=rejected,
            simulated=result.simulated, retrieved_chunks=result.retrieved_chunks, data=result.data,
        )