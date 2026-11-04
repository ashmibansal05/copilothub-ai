import asyncio

from app.agents.brain import AgentBrain, Evaluation, StepResult

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

# Placeholder source names. Nothing here is fetched from the internet.
SOURCE_BANK: dict[str, list[tuple[str, str]]] = {
    "aws": [("AWS pricing overview", "Amazon Web Services"), ("AWS Free Tier summary", "Amazon Web Services")],
    "azure": [("Azure pricing overview", "Microsoft"), ("Azure for startups summary", "Microsoft")],
    "google": [("Google Cloud pricing overview", "Google Cloud"), ("Google Cloud free program summary", "Google Cloud")],
    "criteria": [("Cloud computing overview", "Wikipedia"), ("Choosing a cloud provider: startup guide", "Industry blog")],
    "compare": [("Cloud provider comparison notes", "Analyst blog")],
    "default": [("Background overview", "Wikipedia"), ("Topic explainer", "Industry blog")],
}


class MockBrain(AgentBrain):
    """Deterministic demo agent. It does NOT call a model and its tools are
    SIMULATED. Everything it produces is flagged simulated=True."""

    engine = "demo"
    description = "demo mode (deterministic, tools are simulated)"
    simulated = True

    def __init__(self, delay: float = 1.5) -> None:
        self.delay = delay

    async def _pause(self) -> None:
        if self.delay > 0:
            await asyncio.sleep(self.delay)

    async def make_plan(self, task: str, constraints: list[str], max_steps: int) -> list[str]:
        await self._pause()
        lowered = task.lower()
        is_cloud = any(k in lowered for k in ("aws", "azure", "google cloud", "cloud platform"))
        return list((CLOUD_PLAN if is_cloud else GENERIC_PLAN)[:max_steps])

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

    def _sources_for(self, step: str) -> list[dict]:
        s = step.lower()
        if "aws" in s:
            key = "aws"
        elif "azure" in s:
            key = "azure"
        elif "google" in s:
            key = "google"
        elif "criteria" in s or "identify" in s:
            key = "criteria"
        elif "compare" in s or "analyse" in s:
            key = "compare"
        else:
            key = "default"
        return [{"title": t, "publisher": p, "simulated": True} for t, p in SOURCE_BANK[key]]

    async def execute_step(self, task, step, history, constraints) -> StepResult:
        await self._pause()
        sources = self._sources_for(step)
        return StepResult(
            tool=self.tool_for_step(step),
            output=(
                f"[SIMULATED] {step}: collected {len(sources)} placeholder sources and drafted notes. "
                "No real web or document access happened in demo mode."
            ),
            sources=sources,
            simulated=True,
            input={"step": step},
        )

    async def evaluate(self, task, step, result, history) -> Evaluation:
        confidence = min(0.92, 0.6 + 0.05 * (len(history) + 1))
        return Evaluation(confidence=round(confidence, 2), ok=True, note="Simulated evaluation (demo mode)")

    async def summarize(self, task, history) -> str:
        await self._pause()
        lines = "\n".join(f"- {h['step']}" for h in history if h.get("success"))
        return (
            "[Demo mode] This is a placeholder summary produced without a language model.\n"
            f"Steps completed:\n{lines}\n"
            "Switch DEMO_MODE=false with Ollama running to get real model output."
        )