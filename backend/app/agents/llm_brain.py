
import json

from app.agents.brain import (
    AgentAction,
    AgentBrain,
    Evaluation,
    FinalAnswer,
    StepResult,
    ToolCall,
    ToolObservation,
)
from app.agents.prompts import (
    EVALUATE_INSTRUCTION,
    EXECUTE_INSTRUCTION,
    EXECUTE_WITH_DOCS_INSTRUCTION,
    PLAN_INSTRUCTION,
    SUMMARY_INSTRUCTION,
    build_messages,
    build_tool_messages,
    fence,
    REPORT_INSTRUCTION,
)
from app.llm.base import LLMProvider, LLMResponseError
from app.llm.utils import extract_json
from app.tools.base import ToolSpec, describe_tools


def _as_text(item: object) -> str:
    if isinstance(item, dict):
        for key in ("step", "title", "description", "task"):
            if isinstance(item.get(key), str):
                return item[key]
    return str(item)


def _history_snippets(history: list[dict], limit: int = 5) -> list[str]:
    return [
        f"Step {h['step_index']} ({h['step']}): {h['finding'][:300]}"
        for h in history[-limit:]
    ]


class LLMBrain(AgentBrain):
    """Real model reasoning through an LLMProvider.

    Supports both the existing single-shot execution mode and
    Phase 11 controlled tool execution.
    """

    simulated = False
    uses_tools = True

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.engine = f"{provider.name}:{provider.model}"
        self.description = (
            f"{provider.name} / {provider.model} "
            "(LLM reasoning with controlled tools and document retrieval)"
        )

    async def make_plan(
        self,
        task,
        constraints,
        max_steps,
        notes=None,
    ) -> list[str]:
        messages = build_messages(
            task,
            PLAN_INSTRUCTION.format(max_steps=max_steps),
            constraints,
            human_notes=notes,
        )

        raw = await self.provider.generate(
            messages,
            json_mode=True,
            max_tokens=500,
        )

        data = extract_json(raw)

        steps = data.get("steps") if isinstance(data, dict) else data

        if not isinstance(steps, list):
            raise LLMResponseError("Plan JSON has no 'steps' list")

        cleaned = [
            _as_text(s).strip()[:200]
            for s in steps
            if _as_text(s).strip()
        ]

        if not cleaned:
            raise LLMResponseError("The model produced an empty plan")

        return cleaned[:max_steps]

    def tool_for_step(self, step: str) -> str:
        return "llm_reasoning"

    async def execute_step(
        self,
        task,
        step,
        history,
        constraints,
        notes=None,
        documents=None,
    ) -> StepResult:
        """Existing single-shot execution mode.

        This method is retained for compatibility with the earlier
        agent workflow when AGENT_TOOLS_ENABLED=false.
        """

        passages = [
            (
                f"[{i}] {d['title']} ({d['source_name']}"
                + (f", page {d['page']}" if d.get("page") else "")
                + f")\n{d['text']}"
            )
            for i, d in enumerate(documents or [], start=1)
        ]

        template = (
            EXECUTE_WITH_DOCS_INSTRUCTION
            if passages
            else EXECUTE_INSTRUCTION
        )

        messages = build_messages(
            task,
            template.format(step=fence(step)),
            constraints,
            documents=passages or None,
            tool_results=_history_snippets(history),
            human_notes=notes,
        )

        text = await self.provider.generate(
            messages,
            max_tokens=400,
        )

        return StepResult(
            tool="llm_reasoning",
            output=text,
            simulated=False,
            input={"step": step},
        )

    # ============================================================
    # Phase 11 — Controlled Tool Execution
    # ============================================================

    async def next_action(
        self,
        task,
        step,
        observations: list[ToolObservation],
        constraints,
        notes=None,
        tools: list[ToolSpec] | tuple[ToolSpec, ...] = (),
        force_final=False,
    ) -> AgentAction:
        """Ask the LLM to select an approved tool or provide final findings.

        The orchestrator remains responsible for validating and
        executing tool calls. The LLM cannot execute tools directly.
        """

        seen = [
            (
                f"Call {i}: "
                f"{o.tool}({json.dumps(o.arguments, default=str)[:200]}) "
                f"-> {'OK' if o.ok else 'FAILED'}\n"
                f"{o.output[:1200]}"
            )
            for i, o in enumerate(
                observations[-4:],
                start=max(1, len(observations) - 3),
            )
        ]

        messages = build_tool_messages(
            task,
            step,
            describe_tools(tools),
            constraints,
            notes,
            seen,
            force_final,
        )

        def interpret(raw: str) -> AgentAction:
            try:
                data = extract_json(raw)
            except LLMResponseError:
                # A genuinely plain-text answer can be used as findings, but
                # malformed JSON and partial tool calls must be repaired.
                text = raw.strip()
                if len(text) >= 30 and not text.startswith(("{", "[", "```")):
                    return FinalAnswer(text[:1500])
                raise

            if not isinstance(data, dict):
                raise LLMResponseError("The reply is not a JSON object")

            action_value = data.get("action")
            action = action_value.strip().lower() if isinstance(action_value, str) else ""
            if action == "final":
                findings = data.get("findings") or data.get("answer") or data.get("final")
                if not isinstance(findings, str) or not findings.strip():
                    raise LLMResponseError("The final reply has no findings")
                return FinalAnswer(findings.strip()[:1500])

            if action == "tool":
                if force_final:
                    raise LLMResponseError("The model called a tool although it had to answer now")
                tool = data.get("tool")
                arguments = data.get("arguments", {})
                if not isinstance(tool, str) or not tool.strip():
                    raise LLMResponseError("The tool call has no tool name")
                if not isinstance(arguments, dict):
                    raise LLMResponseError("The tool arguments must be a JSON object")
                return ToolCall(tool=tool.strip(), arguments=arguments)

            # A missing discriminator with clear findings can be interpreted
            # safely. Never guess tool calls, fabricate evidence, or accept an
            # unknown action label as a final answer.
            if not action:
                for key in ("findings", "answer", "final", "response", "content", "text"):
                    candidate = data.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        return FinalAnswer(candidate.strip()[:1500])
            raise LLMResponseError("The reply has no valid 'action'")

        raw = await self.provider.generate(messages, json_mode=True, max_tokens=500)
        try:
            return interpret(raw)
        except LLMResponseError as first_error:
            # Small local models frequently ignore the action discriminator.
            # Give ONE targeted correction, using the same original constraints
            # and observations. The orchestrator still validates tool calls.
            correction = (
                "Your previous reply was invalid: " + str(first_error) + ". "
                "Reply with one valid JSON object ONLY. Choose EXACTLY one shape: "
                '{"action":"final","findings":"Grounded findings for this step"} '
                "or "
                '{"action":"tool","tool":"an available tool name","arguments":{}}. '
                "Do not invent evidence or a tool name. If a tool failed, use "
                "the observations and explain limitations. "
                + ('You MUST use action=final; do not request tools.' if force_final else '')
            )
            repair_messages = [*messages, {"role": "assistant", "content": raw[:1500]},
                               {"role": "user", "content": correction}]
            repaired = await self.provider.generate(
                repair_messages, json_mode=True, max_tokens=350, temperature=0.0
            )
            return interpret(repaired)

    async def evaluate(
        self,
        task,
        step,
        result,
        history,
    ) -> Evaluation:
        messages = build_messages(
            task,
            EVALUATE_INSTRUCTION.format(
                step=fence(step)
            ),
            tool_results=[result.output[:1500]],
        )

        raw = await self.provider.generate(
            messages,
            json_mode=True,
            max_tokens=200,
        )

        data = extract_json(raw)

        if not isinstance(data, dict) or "confidence" not in data:
            raise LLMResponseError(
                "Evaluation JSON has no 'confidence'"
            )

        try:
            confidence = float(data["confidence"])
        except (TypeError, ValueError) as exc:
            raise LLMResponseError(
                "Evaluation confidence is not a number"
            ) from exc

        if 10.0 < confidence <= 100.0:
            confidence /= 100.0

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        ok = bool(
            data.get("ok", confidence >= 0.4)
        )

        return Evaluation(
            confidence=round(confidence, 2),
            ok=ok,
            note=str(data.get("note", ""))[:200],
        )

    async def summarize(
        self,
        task,
        history,
        constraints=None,
        notes=None,
    ) -> str:
        messages = build_messages(
            task,
            SUMMARY_INSTRUCTION,
            constraints,
            tool_results=_history_snippets(
                history,
                limit=12,
            ),
            human_notes=notes,
        )

        return await self.provider.generate(
            messages,
            max_tokens=500,
        )

    # ============================================================
    # Phase 14 - Final Research Report
    # ============================================================

    async def write_report(
        self,
        task,
        history,
        constraints=None,
        notes=None,
    ) -> dict[str, str]:
        material = [
            f"Step {h['step_index']} ({h['step']}): {h['finding'][:400]}"
            + (
                " | sources: "
                + ", ".join(
                    f"{s['title']} ({s['publisher']})"
                    for s in h.get("sources", [])[:4]
                )
                if h.get("sources")
                else ""
            )
            for h in history[-12:]
        ]

        messages = build_messages(
            task,
            REPORT_INSTRUCTION,
            constraints,
            tool_results=material,
            human_notes=notes,
        )

        raw = await self.provider.generate(
            messages,
            json_mode=True,
            max_tokens=900,
        )

        data = extract_json(raw)

        if not isinstance(data, dict):
            raise LLMResponseError(
                "The report reply is not a JSON object"
            )

        def readable(value: object) -> str:
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, list):
                return "\n".join(f"- {item.strip()}" for item in value if isinstance(item, str) and item.strip())
            # Reject unsupported structures rather than printing Python representations.
            return ""

        return {
            key: readable(data.get(key))
            for key in (
                "executive_summary", "findings", "comparison", "conclusion"
            )
        }
