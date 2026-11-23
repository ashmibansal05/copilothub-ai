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

OFFICIAL = "official documentation"

# Placeholder sources (title, publisher, source_type). Nothing is fetched from the
# internet; they exist so source constraints can be demonstrated.
SOURCE_BANK: dict[str, list[tuple[str, str, str]]] = {
    "aws": [
        ("Cloud cost tips for founders", "Startup blog", "blog"),
        ("AWS pricing overview", "Amazon Web Services", OFFICIAL),
        ("AWS Free Tier summary", "Amazon Web Services", OFFICIAL),
        ("Amazon Web Services - Wikipedia", "Wikipedia", "encyclopedia"),
    ],
    "azure": [
        ("Azure vs the rest: a founder's view", "Startup blog", "blog"),
        ("Azure pricing overview", "Microsoft", OFFICIAL),
        ("Azure for startups summary", "Microsoft", OFFICIAL),
        ("Microsoft Azure - Wikipedia", "Wikipedia", "encyclopedia"),
    ],
    "google": [
        ("Google Cloud in five minutes", "Startup blog", "blog"),
        ("Google Cloud pricing overview", "Google Cloud", OFFICIAL),
        ("Google Cloud free program summary", "Google Cloud", OFFICIAL),
        ("Google Cloud Platform - Wikipedia", "Wikipedia", "encyclopedia"),
    ],
    "criteria": [
        ("Cloud computing - Wikipedia", "Wikipedia", "encyclopedia"),
        ("Choosing a cloud provider: startup guide", "Industry blog", "blog"),
    ],
    "compare": [("Cloud provider comparison notes", "Analyst blog", "analyst")],
    "default": [
        ("Background overview", "Wikipedia", "encyclopedia"),
        ("Topic explainer", "Industry blog", "blog"),
    ],
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

    async def make_plan(self, task, constraints, max_steps, notes=None) -> list[str]:
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
        return [
            {"title": t, "publisher": p, "source_type": st, "simulated": True}
            for t, p, st in SOURCE_BANK[key]
        ]

    async def execute_step(self, task, step, history, constraints, notes=None, documents=None) -> StepResult:
        await self._pause()
        sources = self._sources_for(step)
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
            "Sources used (simulated):\n" + ("\n".join(source_lines) or "- none"),
        ]
        if constraints:
            parts.append("Human constraints in force:\n" + "\n".join(f"- {c}" for c in constraints))
        if notes:
            parts.append("Human guidance taken into account:\n" + "\n".join(f"- {n}" for n in notes))
        parts.append("Switch DEMO_MODE=false with Ollama running to get real model output.")
        return "\n\n".join(parts)