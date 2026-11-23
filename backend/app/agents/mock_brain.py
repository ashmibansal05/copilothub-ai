import asyncio

from app.agents.brain import (
    AgentAction, AgentBrain, Evaluation, FinalAnswer, StepResult, ToolCall, ToolObservation,
)
from app.tools.base import ToolSpec
from app.tools.demo_data import demo_sources

CLOUD_PLAN = [
    "Understand the research objective and scope",
    "Identify evaluation criteria for a small startup (cost, ease of use, scalability, support)",
    "Gather information on AWS",
    "Gather information on Microsoft Azure",
    "Gather information on Google Cloud",
    "Compare the providers against the criteria",
    "Draft the final recommendation",
]

GENERIC_PLAN = [
    "Clarify the objective and scope",
    "Identify the key questions to answer",
    "Collect relevant information",
    "Analyse and compare the findings",
    "Draft conclusions",
]


def _is_cloud_task(task: str) -> bool:
    lowered = task.lower()
    return any(k in lowered for k in ("aws", "azure", "google cloud", "cloud platform"))


class MockBrain(AgentBrain):
    """Deterministic demo agent. It does NOT call a language model.

    In tool mode it follows a fixed script of REAL tool calls (search_web uses the
    simulated demo provider unless you configured another one; retrieve_documents and
    compare_sources search your uploaded documents). Its notes are written by code, not
    by a model."""

    engine = "demo"
    description = "demo mode (deterministic script; web results are simulated)"
    simulated = True
    uses_tools = True

    def __init__(self, delay: float = 1.5) -> None:
        self.delay = delay

    async def _pause(self) -> None:
        if self.delay > 0:
            await asyncio.sleep(self.delay)

    async def make_plan(self, task, constraints, max_steps, notes=None) -> list[str]:
        await self._pause()
        return list((CLOUD_PLAN if _is_cloud_task(task) else GENERIC_PLAN)[:max_steps])

    def tool_for_step(self, step: str) -> str:
        s = step.lower()
        if "compare" in s or "analyse" in s:
            return "compare_sources"
        if "gather" in s or "collect" in s:
            return "search_web"
        if "identify" in s or "understand" in s or "clarify" in s:
            return "retrieve_documents"
        if "draft" in s:
            return "summarize_document"
        return "read_document"

    # ------------------------------------------------------------- tool mode
    def _script(self, task: str, step: str) -> list[ToolCall]:
        s = step.lower()
        if "draft" in s:
            return []
        if ("compare" in s or "analyse" in s) and _is_cloud_task(task):
            return [ToolCall("compare_sources", {
                "topics": ["AWS", "Azure", "Google Cloud"], "criteria": ["cost", "support"],
            })]
        return [
            ToolCall("search_web", {"query": step[:150]}),
            ToolCall("retrieve_documents", {"query": f"{task[:100]} {step}"[:250]}),
        ]

    async def next_action(
        self, task, step, observations: list[ToolObservation], constraints, notes=None,
        tools: list[ToolSpec] | tuple[ToolSpec, ...] = (), force_final=False,
    ) -> AgentAction:
        await self._pause()
        script = self._script(task, step)
        if force_final or len(observations) >= len(script):
            used = ", ".join(dict.fromkeys(o.tool for o in observations)) or "no tools"
            ok = sum(1 for o in observations if o.ok)
            return FinalAnswer(
                f"Step '{step}' completed using {used} ({ok}/{len(observations)} calls succeeded). "
                "This note was written by the demo script, not by a language model."
            )
        return script[len(observations)]

    # ------------------------------------------------------------- single-shot mode
    async def execute_step(self, task, step, history, constraints, notes=None, documents=None) -> StepResult:
        await self._pause()
        sources = demo_sources(step)
        extra = f" It also received {len(documents)} passage(s) from uploaded documents." if documents else ""
        return StepResult(
            tool=self.tool_for_step(step),
            output=(
                f"[SIMULATED] {step}: collected {len(sources)} placeholder sources and drafted notes. "
                f"No real web access happened in demo mode.{extra}"
            ),
            sources=sources,
            simulated=True,
            input={"step": step},
        )

    async def evaluate(self, task, step, result, history) -> Evaluation:
        confidence = min(0.92, 0.6 + 0.05 * (len(history) + 1))
        return Evaluation(confidence=round(confidence, 2), ok=True, note="Simulated evaluation (demo mode)")

    async def summarize(self, task, history, constraints=None, notes=None) -> str:
        await self._pause()
        steps = "\n".join(f"- {h['step']}" for h in history if h.get("success"))
        seen: set[tuple[str, str]] = set()
        source_lines: list[str] = []
        for h in history:
            for s in h.get("sources", []):
                key = (s["title"], s["publisher"])
                if key not in seen:
                    seen.add(key)
                    flag = " (preferred)" if s.get("preferred") else ""
                    source_lines.append(f"- {s['title']} [{s['publisher']}]{flag}")
        parts = [
            "[Demo mode] This is a placeholder summary produced without a language model.",
            f"Steps completed:\n{steps}",
            "Sources used:\n" + ("\n".join(source_lines) or "- none"),
        ]
        if constraints:
            parts.append("Human constraints in force:\n" + "\n".join(f"- {c}" for c in constraints))
        if notes:
            parts.append("Human guidance taken into account:\n" + "\n".join(f"- {n}" for n in notes))
        parts.append("Switch DEMO_MODE=false with Ollama running to get real model output.")
        return "\n\n".join(parts)