from app.agents.brain import AgentBrain, Evaluation, StepResult
from app.agents.prompts import (
    EVALUATE_INSTRUCTION,
    EXECUTE_INSTRUCTION,
    PLAN_INSTRUCTION,
    SUMMARY_INSTRUCTION,
    build_messages,
    fence,
)
from app.llm.base import LLMProvider, LLMResponseError
from app.llm.utils import extract_json


def _as_text(item: object) -> str:
    if isinstance(item, dict):
        for key in ("step", "title", "description", "task"):
            if isinstance(item.get(key), str):
                return item[key]
    return str(item)


def _history_snippets(history: list[dict], limit: int = 5) -> list[str]:
    return [f"Step {h['step_index']} ({h['step']}): {h['finding'][:300]}" for h in history[-limit:]]


class LLMBrain(AgentBrain):
    """Real model reasoning through an LLMProvider. No retrieval or tools yet
    (Phases 10-11), so findings come from the model's own knowledge."""

    simulated = False

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.engine = f"{provider.name}:{provider.model}"
        self.description = f"{provider.name} / {provider.model} (model knowledge only, no retrieval yet)"

    async def make_plan(self, task: str, constraints: list[str], max_steps: int) -> list[str]:
        messages = build_messages(task, PLAN_INSTRUCTION.format(max_steps=max_steps), constraints)
        raw = await self.provider.generate(messages, json_mode=True, max_tokens=500)
        data = extract_json(raw)
        steps = data.get("steps") if isinstance(data, dict) else data
        if not isinstance(steps, list):
            raise LLMResponseError("Plan JSON has no 'steps' list")
        cleaned = [_as_text(s).strip()[:200] for s in steps if _as_text(s).strip()]
        if not cleaned:
            raise LLMResponseError("The model produced an empty plan")
        return cleaned[:max_steps]

    def tool_for_step(self, step: str) -> str:
        return "llm_reasoning"

    async def execute_step(self, task, step, history, constraints) -> StepResult:
        messages = build_messages(
            task,
            EXECUTE_INSTRUCTION.format(step=fence(step)),
            constraints,
            tool_results=_history_snippets(history),
        )
        text = await self.provider.generate(messages, max_tokens=400)
        return StepResult(tool="llm_reasoning", output=text, simulated=False, input={"step": step})

    async def evaluate(self, task, step, result, history) -> Evaluation:
        messages = build_messages(
            task,
            EVALUATE_INSTRUCTION.format(step=fence(step)),
            tool_results=[result.output[:1500]],
        )
        raw = await self.provider.generate(messages, json_mode=True, max_tokens=200)
        data = extract_json(raw)
        if not isinstance(data, dict) or "confidence" not in data:
            raise LLMResponseError("Evaluation JSON has no 'confidence'")
        try:
            confidence = float(data["confidence"])
        except (TypeError, ValueError) as exc:
            raise LLMResponseError("Evaluation confidence is not a number") from exc
        if 1.0 < confidence <= 100.0:  # model answered as a percentage
            confidence /= 100.0
        confidence = max(0.0, min(1.0, confidence))
        ok = bool(data.get("ok", confidence >= 0.4))
        return Evaluation(confidence=round(confidence, 2), ok=ok, note=str(data.get("note", ""))[:200])

    async def summarize(self, task, history) -> str:
        messages = build_messages(task, SUMMARY_INSTRUCTION, tool_results=_history_snippets(history, limit=12))
        return await self.provider.generate(messages, max_tokens=500)