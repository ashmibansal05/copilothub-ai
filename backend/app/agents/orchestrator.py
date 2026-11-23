import asyncio
import logging
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.brain import AgentBrain, FinalAnswer, StepResult, ToolCall, ToolObservation
from app.agents.state import AgentGraphState, ApprovalDecision, HumanContext
from app.core.config import Settings, get_settings
from app.db import session as db_session
from app.models.agent import AgentAction, AgentState
from app.models.approval import Approval, ApprovalKind, ApprovalStatus
from app.models.session import AgentSession, AgentStatus
from app.models.source import Source
from app.models.tool_execution import ToolExecution
from app.ml import service as risk_service
from app.rag import service as rag_service
from app.rag.embeddings import get_embedder
from app.services import approval_service, analytics_service, event_service, report_service
from app.services.conflict_manager import ConflictManager
from app.services.constraint_manager import ConstraintManager, ConstraintView
from app.services.memory_manager import MemoryManager
from app.tools import get_registry
from app.tools.base import ToolContext
from app.tools.registry import ToolOutcome, ToolRegistry, preview_arguments
from app.websocket.events import EventType

logger = logging.getLogger("copilothub.agent")

BrainFactory = Callable[[], Awaitable[tuple[AgentBrain, str | None]]]

FINISHABLE = {
    AgentStatus.RUNNING, AgentStatus.PLANNING, AgentStatus.PAUSED, AgentStatus.WAITING_FOR_APPROVAL,
}
TERMINAL = {AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED}
PLAN_DONE_PROGRESS = 10


class AgentStepError(Exception):
    """A node failed after exhausting its retries (or a human rejected too often)."""


class AgentLimitError(Exception):
    """The run exceeded its time budget."""


class AgentOrchestrator:
    """Runs one session's agent as a LangGraph workflow:

        plan -> act -> observe -> evaluate -+-> act      (next step / retry)
          ^                                 +-> plan     (task changed: re-plan)
          |                                 +-> finalize -+-> END (approved)
          +---------------------------------------------+-> plan (task changed)
                                                         +-> finalize (draft rejected: revise)

    Before acting (and before finalizing) the agent stops while a human review is
    requested or an instruction conflict needs the owner's decision."""

    def __init__(
        self,
        session_id: uuid.UUID,
        brain_factory: BrainFactory,
        settings: Settings | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        self.session_id = session_id
        self.settings = settings or get_settings()
        self.tools = tools or get_registry()
        self._tool_calls_total = 0
        self.brain_factory = brain_factory
        self.brain: AgentBrain | None = None
        self.resume_event = asyncio.Event()
        self.resume_event.set()  # set = running, cleared = paused
        self._started = time.monotonic()
        self._paused_total = 0.0  # time spent paused or waiting for humans (not billed to the budget)
        # human input that arrives while the agent is busy
        self._review_request: tuple[uuid.UUID | None, str, str | None] | None = None
        self._replan_requested = False
        self._replans = 0
        self._approval_future: asyncio.Future[ApprovalDecision] | None = None
        self._pending_approval_id: uuid.UUID | None = None
        self._conflicts_event = asyncio.Event()
        self._retrieval_warned = False
        self.graph = self._build_graph()

    # ------------------------------------------------------------------ control
    def pause(self) -> None:
        self.resume_event.clear()

    def resume(self) -> None:
        self.resume_event.set()

    def request_review(self, user_id: uuid.UUID | None, username: str, note: str | None) -> None:
        self._review_request = (user_id, username, note)

    def request_replan(self) -> None:
        self._replan_requested = True

    def notify_conflicts_changed(self) -> None:
        self._conflicts_event.set()

    def resolve_approval(self, approval_id: uuid.UUID, decision: ApprovalDecision) -> bool:
        future = self._approval_future
        if future is None or future.done() or self._pending_approval_id != approval_id:
            return False
        future.set_result(decision)
        return True

    async def checkpoint(self) -> None:
        """Called before every node: waits while paused, enforces the runtime budget."""
        if not self.resume_event.is_set():
            waited_from = time.monotonic()
            await self.resume_event.wait()
            self._paused_total += time.monotonic() - waited_from
        active = time.monotonic() - self._started - self._paused_total
        if active > self.settings.agent_max_runtime_seconds:
            raise AgentLimitError(
                f"Runtime budget of {self.settings.agent_max_runtime_seconds:.0f}s exceeded"
            )

    # ------------------------------------------------------------------ graph
    def _build_graph(self):
        g = StateGraph(AgentGraphState)
        g.add_node("plan", self.plan_node)
        g.add_node("act", self.act_node)
        g.add_node("observe", self.observe_node)
        g.add_node("evaluate", self.evaluate_node)
        g.add_node("finalize", self.finalize_node)
        g.add_edge(START, "plan")
        g.add_edge("plan", "act")
        g.add_edge("act", "observe")
        g.add_edge("observe", "evaluate")
        g.add_conditional_edges(
            "evaluate", self.route_after_evaluate,
            {"act": "act", "plan": "plan", "finalize": "finalize"},
        )
        g.add_conditional_edges(
            "finalize", self.route_after_finalize,
            {"plan": "plan", "finalize": "finalize", "end": END},
        )
        return g.compile()

    @staticmethod
    def route_after_evaluate(state: AgentGraphState) -> str:
        decision = state.get("decision")
        if decision == "replan":
            return "plan"
        return "finalize" if decision == "complete" else "act"

    @staticmethod
    def route_after_finalize(state: AgentGraphState) -> str:
        decision = state.get("decision")
        if decision == "replan":
            return "plan"
        return "finalize" if decision == "revise" else "end"

    async def run(self) -> None:
        """Entry point used by the runner. Never raises except on cancellation."""
        try:
            task = self._load_task()
            self.brain, notice = await self.brain_factory()
            await self._save_state(
                engine=self.brain.engine, current_step="Starting", step_index=0,
                total_steps=0, progress=0, confidence=None,
                plan=[], recent_actions=[], tool_results=[],
            )
            await self._emit(
                EventType.AGENT_MESSAGE,
                {"kind": "system", "text": f"Agent engine: {self.brain.description}"},
            )
            if notice:
                await self._emit(EventType.AGENT_MESSAGE, {"kind": "warning", "text": notice})

            initial: AgentGraphState = {
                "task": task, "plan": [], "step_index": 0, "steps_executed": 0,
                "retries": 0, "observations": [], "approval_round": 0,
            }
            # LangGraph counts every node visit; leave room for re-plans and revisions.
            limit = 3 * self.settings.agent_max_steps + 60
            final = await self.graph.ainvoke(initial, config={"recursion_limit": limit})
            await self._complete(final)
        except asyncio.CancelledError:
            logger.info("Agent for session %s was cancelled", self.session_id)
            raise
        except Exception as exc:
            logger.exception("Agent for session %s failed", self.session_id)
            await self._fail(str(exc) or exc.__class__.__name__)

    # ------------------------------------------------------------------ nodes
    async def plan_node(self, state: AgentGraphState) -> dict[str, Any]:
        await self.checkpoint()
        assert self.brain is not None
        replanning = bool(state.get("plan"))
        self._replan_requested = False  # a fresh plan reflects the latest task
        task = self._load_task() if replanning else state["task"]
        ctx = await self._human_context(task)

        await self._set_status(AgentStatus.PLANNING, {AgentStatus.RUNNING})
        await self._emit(EventType.STEP_STARTED, {
            "phase": "PLAN", "step_index": 0, "total_steps": 0,
            "step": "Re-planning after a task change" if replanning else "Planning the research",
            "progress": 0, "engine": self.brain.engine,
        })
        started = time.monotonic()
        plan = await self._attempt(
            "PLAN",
            lambda: self.brain.make_plan(task, ctx.constraints, self.settings.agent_max_steps, notes=ctx.notes),
        )
        plan = plan[: self.settings.agent_max_steps]
        await self._record_action(0, "PLAN", None, {}, {"plan": plan}, True, None, self._ms(started))
        await self._save_state(
            plan=plan, total_steps=len(plan), step_index=0,
            progress=PLAN_DONE_PROGRESS, current_step="Planning complete",
        )
        await self._emit(EventType.STEP_COMPLETED, {
            "phase": "PLAN", "step_index": 0, "total_steps": len(plan), "plan": plan,
            "completed_steps": 0, "progress": PLAN_DONE_PROGRESS,
            "summary": f"Created a {len(plan)}-step plan",
        })
        await self._set_status(AgentStatus.RUNNING, {AgentStatus.PLANNING})
        return {
            "plan": plan, "step_index": 0, "task": task, "retries": 0,
            "decision": "continue", "approval_round": 0,
        }

    async def act_node(self, state: AgentGraphState) -> dict[str, Any]:
        await self.checkpoint()
        await self._maybe_review()
        await self._wait_for_conflicts()
        assert self.brain is not None
        i, plan = state["step_index"], state["plan"]
        n, step = len(plan), plan[i]
        progress = self._progress(i, n)
        query = f"{state['task']} {step}"
        ctx = await self._human_context(query)

        await self._save_state(current_step=step, progress=progress)
        await self._emit(EventType.STEP_STARTED, {
            "phase": "ACT", "step_index": i + 1, "total_steps": n, "step": step, "progress": progress,
        })

        started = time.monotonic()
        if self.settings.agent_tools_enabled and self.brain.uses_tools:
            result = await self._act_with_tools(state, step, i, ctx)
        else:
            result = await self._act_single_shot(state, step, i, ctx, query)

        await self._record_action(
            i + 1, "TOOL_CALL", result.tool[:60], {"step": step},
            {"output": result.output[:2000], "sources": result.sources,
             "rejected_sources": result.rejected_sources},
            result.success, None, self._ms(started),
        )
        await self._record_sources(i + 1, result)
        return {"last_result": asdict(result), "steps_executed": state.get("steps_executed", 0) + 1}

    # ------------------------------------------------------------------ tool loop (Phase 11)
    async def _act_with_tools(self, state: AgentGraphState, step: str, i: int, ctx: HumanContext) -> StepResult:
        """The model asks for tools; WE validate and run them; results go back to the model.
        Bounded by max calls per step and per run."""
        assert self.brain is not None
        specs = self.tools.specs()
        observations: list[ToolObservation] = []
        used: list[str] = []
        sources: list[dict] = []
        rejected: list[dict] = []
        simulated = bool(self.brain.simulated)
        per_step = self.settings.agent_max_tool_calls_per_step
        final_text = ""

        for call_number in range(per_step + 1):
            force = (
                call_number >= per_step
                or self._tool_calls_total >= self.settings.agent_max_tool_calls_per_run
            )
            action = await self._attempt(
                "ACT",
                lambda force=force: self.brain.next_action(
                    state["task"], step, list(observations), ctx.constraints,
                    notes=ctx.notes, tools=specs, force_final=force,
                ),
                step_index=i + 1, tool_name="llm_reasoning",
            )
            if isinstance(action, FinalAnswer):
                final_text = action.text
                break
            if force:  # defensive: the brain ignored force_final
                final_text = "(No final answer was produced within the tool-call limit.)"
                break
            outcome = await self._execute_tool(action, state, i + 1)
            observations.append(ToolObservation(
                tool=action.tool, arguments=action.arguments, ok=outcome.ok, output=outcome.output
            ))
            used.append(action.tool)
            sources += outcome.sources
            rejected += outcome.rejected_sources
            simulated = simulated or outcome.simulated

        if rejected:
            names = sorted({s.get("rejected_by", "?") for s in rejected})
            await self._emit(EventType.AGENT_MESSAGE, {
                "kind": "constraint",
                "text": f"Step {i + 1}: filtered {len(rejected)} source(s) because of human constraints ({', '.join(names)}).",
            })
        return StepResult(
            tool="+".join(dict.fromkeys(used)) or "llm_reasoning",
            output=final_text, success=True,
            sources=self._dedupe_sources(sources), rejected_sources=self._dedupe_sources(rejected),
            simulated=simulated, input={"step": step},
        )

    async def _execute_tool(self, call: ToolCall, state: AgentGraphState, step_index: int) -> ToolOutcome:
        self._tool_calls_total += 1
        tool_context = ToolContext(
            session_id=self.session_id, settings=self.settings, views=await self._active_views(),
            step_index=step_index, task=state["task"], history=list(state.get("observations", [])),
        )
        preview = preview_arguments(call.arguments)
        await self._emit(EventType.TOOL_STARTED, {
            "tool": str(call.tool)[:60], "step_index": step_index, "input": preview, "simulated": False,
        })
        outcome = await self.tools.execute(call.tool, call.arguments, tool_context)
        await self._record_tool_execution(step_index, outcome)
        await self._emit(EventType.TOOL_COMPLETED, {
            "tool": outcome.tool, "step_index": step_index, "success": outcome.ok,
            "status": outcome.status, "duration_ms": outcome.duration_ms,
            "output": outcome.output[:500], "arguments": outcome.arguments,
            "sources": outcome.sources, "rejected_sources": outcome.rejected_sources,
            "retrieved_chunks": outcome.retrieved_chunks, "simulated": outcome.simulated,
            "error": outcome.error,
        })
        if outcome.ok and outcome.tool == "save_report":
            await self._emit(EventType.REPORT_SAVED, {"report": outcome.data})
        return outcome

    async def _record_tool_execution(self, step_index: int, outcome: ToolOutcome) -> None:
        try:
            with self._db() as db:
                db.add(ToolExecution(
                    session_id=self.session_id, step_index=step_index, tool_name=outcome.tool,
                    arguments=outcome.arguments, status=outcome.status,
                    output_summary=outcome.output[:500] if outcome.ok else None, error=outcome.error,
                    simulated=outcome.simulated, duration_ms=outcome.duration_ms,
                    sources_count=len(outcome.sources), rejected_count=len(outcome.rejected_sources),
                ))
                db.commit()
        except Exception:
            logger.warning("Could not record tool execution for session %s", self.session_id, exc_info=True)

    # ------------------------------------------------------------------ single-shot step (Phase 5-10 behaviour)
    async def _act_single_shot(
        self, state: AgentGraphState, step: str, i: int, ctx: HumanContext, query: str
    ) -> StepResult:
        assert self.brain is not None
        tool = self.brain.tool_for_step(step)
        # Retrieval already skips excluded sources; the filter below is a second line of defence.
        chunks = await self._retrieve_documents(query, await self._active_views())
        documents = [c.as_prompt() for c in chunks]
        await self._emit(EventType.TOOL_STARTED, {
            "tool": tool, "step_index": i + 1, "input": {"step": step}, "simulated": self.brain.simulated,
        })

        started = time.monotonic()
        result: StepResult = await self._attempt(
            "ACT",
            lambda: self.brain.execute_step(
                state["task"], step, state.get("observations", []), ctx.constraints,
                notes=ctx.notes, documents=documents or None,
            ),
            step_index=i + 1, tool_name=tool, input_data={"step": step},
        )
        result.sources = list(result.sources) + self._document_sources(chunks)

        # Enforcement point: the CURRENT human rules decide which sources the agent may keep.
        views = await self._active_views()
        result.sources, result.rejected_sources = ConstraintManager.filter_sources(views, result.sources)
        if result.rejected_sources:
            names = sorted({s.get("rejected_by", "?") for s in result.rejected_sources})
            await self._emit(EventType.AGENT_MESSAGE, {
                "kind": "constraint",
                "text": f"Step {i + 1}: filtered {len(result.rejected_sources)} source(s) because of human constraints ({', '.join(names)}).",
            })
        await self._emit(EventType.TOOL_COMPLETED, {
            "tool": result.tool, "step_index": i + 1, "success": result.success, "status": "SUCCESS",
            "duration_ms": self._ms(started), "output": result.output[:500],
            "sources": result.sources, "rejected_sources": result.rejected_sources,
            "retrieved_chunks": len(chunks), "simulated": result.simulated,
        })
        return result

    @staticmethod
    def _dedupe_sources(sources: list[dict]) -> list[dict]:
        seen: set[tuple] = set()
        out = []
        for s in sources:
            key = (s.get("title"), s.get("publisher"), s.get("document_id") or s.get("url"))
            if key not in seen:
                seen.add(key)
                out.append(s)
        return out

    async def observe_node(self, state: AgentGraphState) -> dict[str, Any]:
        i, plan = state["step_index"], state["plan"]
        res = state["last_result"]
        observation = {
            "step_index": i + 1, "step": plan[i], "tool": res["tool"],
            "finding": res["output"][:1500], "success": res["success"],
            "simulated": res["simulated"], "sources": res["sources"],
            "rejected_sources": res["rejected_sources"],
        }
        observations = list(state.get("observations", [])) + [observation]
        await self._emit(EventType.AGENT_MESSAGE, {
            "kind": "agent", "simulated": res["simulated"],
            "text": f"Step {i + 1}/{len(plan)}: {plan[i]}\n{res['output'][:400]}",
        })
        await self._save_state(
            recent_actions=[
                {"step_index": o["step_index"], "step": o["step"], "tool": o["tool"], "success": o["success"]}
                for o in observations[-10:]
            ],
            tool_results=[
                {"step_index": o["step_index"], "tool": o["tool"], "summary": o["finding"][:200]}
                for o in observations[-5:]
            ],
        )
        return {"observations": observations}

    async def evaluate_node(self, state: AgentGraphState) -> dict[str, Any]:
        assert self.brain is not None
        i, plan = state["step_index"], state["plan"]
        n, step = len(plan), plan[i]
        result = StepResult(**state["last_result"])

        started = time.monotonic()
        ev = await self._attempt(
            "EVALUATE",
            lambda: self.brain.evaluate(state["task"], step, result, state.get("observations", [])),
            step_index=i + 1,
        )
        await self._record_action(
            i + 1, "EVALUATE", None, {"step": step},
            {"confidence": ev.confidence, "ok": ev.ok, "note": ev.note}, True, None, self._ms(started),
        )

        executed = state.get("steps_executed", 0)
        retries = state.get("retries", 0)
        max_steps = self.settings.agent_max_steps

        if not ev.ok and retries < self.settings.agent_max_retries and executed < max_steps:
            decision, next_index, retries = "retry", i, retries + 1
            await self._emit(EventType.AGENT_MESSAGE, {
                "kind": "warning",
                "text": f"Step {i + 1} was judged unsatisfactory ({ev.note or 'no reason given'}). Retrying ({retries}/{self.settings.agent_max_retries}).",
            })
        else:
            next_index, retries = i + 1, 0
            decision = "complete" if next_index >= n or executed >= max_steps else "continue"
            if not ev.ok:
                await self._emit(EventType.AGENT_MESSAGE, {
                    "kind": "escalation",
                    "text": f"Step {i + 1} is still unsatisfactory after retries. Human review is recommended.",
                })
            if decision == "complete" and next_index < n:
                await self._emit(EventType.AGENT_MESSAGE, {
                    "kind": "warning",
                    "text": f"Step limit ({max_steps}) reached. Remaining plan steps were skipped.",
                })

        if self._consume_replan():
            decision, retries = "replan", 0
            await self._emit(EventType.AGENT_MESSAGE, {
                "kind": "warning", "text": "A human changed the task. The agent is re-planning.",
            })

        progress = self._progress(next_index, n)
        await self._emit(EventType.STEP_COMPLETED, {
            "phase": "ACT", "step_index": i + 1, "total_steps": n, "step": step,
            "confidence": ev.confidence, "ok": ev.ok, "note": ev.note,
            "completed_steps": next_index, "progress": progress, "decision": decision,
        })
        await self._save_state(step_index=next_index, progress=progress, confidence=ev.confidence)
        await self._update_risk()
        return {"confidence": ev.confidence, "step_index": next_index, "retries": retries, "decision": decision}

    async def finalize_node(self, state: AgentGraphState) -> dict[str, Any]:
        await self.checkpoint()
        await self._wait_for_conflicts()
        assert self.brain is not None
        if self._consume_replan():
            return {"decision": "replan", "approved": False}

        ctx = await self._human_context(state["task"])
        views = await self._active_views()
        observations, removed = self._refilter(state.get("observations", []), views)
        if removed:
            await self._emit(EventType.AGENT_MESSAGE, {
                "kind": "constraint",
                "text": f"Removed {removed} previously collected source(s) that violate the current constraints.",
            })

        started = time.monotonic()
        summary = await self._attempt(
            "FINALIZE",
            lambda: self.brain.summarize(state["task"], observations, ctx.constraints, notes=ctx.notes),
        )
        await self._record_action(
            len(state["plan"]) + 1, "FINALIZE", None, {}, {"summary": summary[:3000]}, True, None, self._ms(started)
        )

        round_no = state.get("approval_round", 0)
        await self._emit(EventType.AGENT_MESSAGE, {
            "kind": "agent", "simulated": self.brain.simulated,
            "text": f"Draft summary (round {round_no + 1}):\n{summary}",
        })
        if not self.settings.agent_require_final_approval:
            return {"summary": summary, "approved": True, "decision": "complete"}

        decision = await self.approval_gate(
            ApprovalKind.FINAL_REPORT, {"draft": summary[:4000], "round": round_no + 1}
        )
        if self._consume_replan():  # the task changed while waiting: the decision is void
            return {"decision": "replan", "approved": False}
        if decision.approved:
            await self._emit(EventType.AGENT_MESSAGE, {
                "kind": "system", "text": f"Final draft approved by {decision.by or 'a reviewer'}.",
            })
            return {"summary": summary, "approved": True, "decision": "complete"}

        round_no += 1
        if round_no >= self.settings.agent_max_approval_rounds:
            raise AgentStepError(f"The final draft was rejected {round_no} times")
        await self._emit(EventType.AGENT_MESSAGE, {
            "kind": "warning",
            "text": f"Draft rejected by {decision.by or 'a reviewer'}: {decision.note or 'no reason given'}. Revising.",
        })
        return {"approval_round": round_no, "approved": False, "decision": "revise"}

    # ------------------------------------------------------------------ waiting for humans
    async def approval_gate(
        self, kind: ApprovalKind, payload: dict, requested_by: uuid.UUID | None = None
    ) -> ApprovalDecision:
        """Stop and wait for a human decision. The decision arrives through
        resolve_approval(), called by the intervention API."""
        with self._db() as db:
            approval = Approval(
                session_id=self.session_id, kind=kind, status=ApprovalStatus.PENDING,
                payload=payload, requested_by=requested_by,
            )
            db.add(approval)
            db.commit()
            approval_id = approval.id

        future: asyncio.Future[ApprovalDecision] = asyncio.get_running_loop().create_future()
        self._approval_future, self._pending_approval_id = future, approval_id
        await self._set_status(AgentStatus.WAITING_FOR_APPROVAL, {AgentStatus.RUNNING, AgentStatus.PLANNING})
        await self._emit(EventType.APPROVAL_REQUESTED, {
            "approval_id": str(approval_id), "kind": kind.value, "payload": payload,
        })
        await self._emit(EventType.AGENT_MESSAGE, {
            "kind": "system", "text": "The agent is waiting for human approval.",
        })
        waited_from = time.monotonic()
        try:
            decision = await future
        finally:
            self._paused_total += time.monotonic() - waited_from  # human time is not agent time
            self._approval_future, self._pending_approval_id = None, None
        await self._set_status(AgentStatus.RUNNING, {AgentStatus.WAITING_FOR_APPROVAL})
        return decision

    async def _maybe_review(self) -> None:
        if self._review_request is None:
            return
        user_id, username, note = self._review_request
        self._review_request = None
        await self.approval_gate(
            ApprovalKind.REVIEW, {"requested_by": username, "note": note}, requested_by=user_id
        )

    def _blocking_conflicts(self) -> int:
        with self._db() as db:
            return ConflictManager.count_blocking(db, self.session_id)

    async def _wait_for_conflicts(self) -> None:
        """If two human instructions contradict each other and the priority rules cannot
        decide, the agent stops until the owner resolves the conflict explicitly."""
        if self._blocking_conflicts() == 0:
            return
        waited_from = time.monotonic()
        await self._set_status(AgentStatus.WAITING_FOR_APPROVAL, {AgentStatus.RUNNING, AgentStatus.PLANNING})
        await self._emit(EventType.AGENT_MESSAGE, {
            "kind": "system",
            "text": "The agent is waiting for the owner to resolve a conflict between human instructions.",
        })
        while True:
            self._conflicts_event.clear()
            if self._blocking_conflicts() == 0:
                break
            await self._conflicts_event.wait()
        self._paused_total += time.monotonic() - waited_from
        await self._set_status(AgentStatus.RUNNING, {AgentStatus.WAITING_FOR_APPROVAL})
        await self._emit(EventType.AGENT_MESSAGE, {
            "kind": "system", "text": "The conflict was resolved. The agent continues.",
        })

    def _consume_replan(self) -> bool:
        if not self._replan_requested:
            return False
        self._replan_requested = False
        if self._replans >= self.settings.agent_max_replans:
            logger.warning("Re-plan limit reached for session %s; ignoring request", self.session_id)
            return False
        self._replans += 1
        return True

    # ------------------------------------------------------------------ finishing
    async def _complete(self, final: AgentGraphState) -> None:
        await self._save_state(current_step="Completed", progress=100)
        await self._generate_final_report()
        if await self._set_status(AgentStatus.COMPLETED, FINISHABLE):
            await self._emit(EventType.COMPLETED, {
                "summary": final.get("summary", ""), "confidence": final.get("confidence"),
            })
        await self._record_analytics()

    async def _fail(self, error: str) -> None:
        await self._save_state(current_step="Failed")
        with self._db() as db:
            expired = approval_service.expire_pending(db, self.session_id)
        if expired:
            await self._emit(EventType.APPROVAL_COMPLETED, {"expired": True})
        await self._emit(EventType.AGENT_MESSAGE, {
            "kind": "escalation",
            "text": f"The agent stopped because of an error and needs human attention: {error}",
        })
        if await self._set_status(AgentStatus.FAILED, FINISHABLE):
            await self._emit(EventType.FAILED, {"error": error})
        await self._record_analytics()

    # ------------------------------------------------------------------ ML risk, report, analytics (never fatal)
    async def _update_risk(self) -> None:
        """Estimate human-intervention risk, persist it, and broadcast an update."""
        if not self.settings.risk_prediction_enabled:
            return
        try:
            estimate = await asyncio.to_thread(risk_service.estimate_and_store, self.session_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Risk estimation failed for session %s", self.session_id, exc_info=True)
            return
        if estimate is not None:
            await self._emit(EventType.RISK_UPDATED, estimate.event_payload())

    async def _generate_final_report(self) -> None:
        if not self.settings.agent_generate_final_report or self.brain is None:
            return
        await self._emit(EventType.AGENT_MESSAGE, {"kind": "system", "text": "Generating the final report..."})
        try:
            info = await report_service.generate_report(self.session_id, self.brain)
            await self._emit(EventType.REPORT_SAVED, {"report": info})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Final report generation failed for session %s", self.session_id)
            await self._emit(EventType.AGENT_MESSAGE, {
                "kind": "warning", "text": f"The final report could not be generated ({exc.__class__.__name__}).",
            })

    async def _record_analytics(self) -> None:
        try:
            await asyncio.to_thread(analytics_service.record_session_end, self.session_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Could not record analytics for session %s", self.session_id, exc_info=True)

    # ------------------------------------------------------------------ human context & sources
    def _human_context_sync(self, query: str) -> HumanContext:
        with self._db() as db:
            views = ConstraintManager.to_views(ConflictManager.effective_constraints(db, self.session_id))
            notes = MemoryManager.retrieve(db, self.session_id, query, embedder=get_embedder())
        return HumanContext(constraints=ConstraintManager.prompt_lines(views), notes=notes)

    async def _human_context(self, query: str) -> HumanContext:
        """Effective constraints (always) plus the few relevant memory notes (selected).
        Runs in a worker thread because embedding may load a model."""
        return await asyncio.to_thread(self._human_context_sync, query)

    async def _active_views(self) -> list[ConstraintView]:
        """The constraints the agent must obey RIGHT NOW (losing sides of open conflicts excluded)."""
        with self._db() as db:
            return ConstraintManager.to_views(ConflictManager.effective_constraints(db, self.session_id))

    def _retrieve_sync(self, query: str, views: list[ConstraintView]):
        with self._db() as db:
            return rag_service.retrieve_chunks(db, self.session_id, query, self.settings.rag_top_k, views)

    async def _retrieve_documents(self, query: str, views: list[ConstraintView]):
        try:
            return await asyncio.to_thread(self._retrieve_sync, query, views)
        except Exception as exc:
            logger.warning("Document retrieval failed: %s", exc, exc_info=True)
            if not self._retrieval_warned:
                self._retrieval_warned = True
                await self._emit(EventType.AGENT_MESSAGE, {
                    "kind": "warning",
                    "text": f"Document retrieval failed ({exc.__class__.__name__}); continuing without documents.",
                })
            return []

    @staticmethod
    def _document_sources(chunks) -> list[dict]:
        return rag_service.document_sources(chunks)

    async def _record_sources(self, step_index: int, result: StepResult) -> None:
        def row(source: dict, status: str) -> Source:
            origin = (
                "DOCUMENT" if source.get("origin") == "document"
                else "WEB" if source.get("origin") == "web"
                else "SIMULATED" if source.get("simulated") else "OTHER"
            )
            document_id = uuid.UUID(source["document_id"]) if source.get("document_id") else None
            return Source(
                session_id=self.session_id, document_id=document_id, step_index=step_index,
                title=str(source.get("title", ""))[:300], publisher=str(source.get("publisher", ""))[:200],
                source_type=source.get("source_type") or None, origin=origin, status=status,
                rejected_by=source.get("rejected_by") or None, score=source.get("score"),
            )

        rows = [row(s, "USED") for s in result.sources] + [row(s, "REJECTED") for s in result.rejected_sources]
        if not rows:
            return
        try:
            with self._db() as db:
                db.add_all(rows)
                db.commit()
        except Exception:
            logger.warning("Could not record sources for session %s", self.session_id, exc_info=True)

    @staticmethod
    def _refilter(observations: list[dict], views: list[ConstraintView]) -> tuple[list[dict], int]:
        """Apply today's constraints to everything collected so far (rules may have
        been added after a source was retrieved)."""
        removed = 0
        out = []
        for obs in observations:
            allowed, rejected = ConstraintManager.filter_sources(views, obs.get("sources", []))
            removed += len(rejected)
            out.append({**obs, "sources": allowed})
        return out, removed

    # ------------------------------------------------------------------ plumbing
    @staticmethod
    def _ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    @staticmethod
    def _progress(done: int, total: int) -> int:
        return PLAN_DONE_PROGRESS + int(85 * done / max(total, 1))

    async def _attempt(
        self,
        label: str,
        func: Callable[[], Awaitable[Any]],
        *,
        step_index: int = 0,
        tool_name: str | None = None,
        input_data: dict | None = None,
    ) -> Any:
        """Run a brain call with a timeout, retries and failure bookkeeping."""
        attempts = self.settings.agent_max_retries + 1
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                return await asyncio.wait_for(func(), timeout=self.settings.agent_step_timeout_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                message = str(exc) or exc.__class__.__name__
                logger.warning("%s attempt %d/%d failed: %s", label, attempt, attempts, message)
                await self._record_action(
                    step_index, label, tool_name, input_data or {}, {}, False, message, self._ms(started)
                )
                if label == "ACT":
                    await self._emit(EventType.TOOL_COMPLETED, {
                        "tool": tool_name, "step_index": step_index, "success": False,
                        "error": message, "duration_ms": self._ms(started), "sources": [],
                        "rejected_sources": [], "retrieved_chunks": 0,
                        "simulated": bool(self.brain and self.brain.simulated),
                    })
                else:
                    await self._emit(EventType.AGENT_MESSAGE, {
                        "kind": "warning",
                        "text": f"{label.title()} failed (attempt {attempt}/{attempts}): {message}",
                    })
                if attempt == attempts:
                    raise AgentStepError(f"{label} failed after {attempts} attempts: {message}") from exc
                await asyncio.sleep(self.settings.agent_retry_backoff_seconds * attempt)

    def _db(self):
        return db_session.SessionLocal()

    def _load_task(self) -> str:
        with self._db() as db:
            row = db.get(AgentSession, self.session_id)
            if row is None:
                raise AgentStepError("Session not found")
            return row.task

    async def _emit(self, event_type: EventType, payload: dict) -> None:
        with self._db() as db:
            await event_service.publish(db, self.session_id, event_type, payload, None)

    async def _set_status(self, target: AgentStatus, expected: set[AgentStatus]) -> bool:
        """Change status only if the session is currently in `expected`. This keeps
        the agent from overwriting a PAUSED or CANCELLED set by a human."""
        with self._db() as db:
            row = db.get(AgentSession, self.session_id)
            if row is None or row.status not in expected:
                return False
            previous = row.status
            row.status = target
            if target in TERMINAL:
                row.ended_at = datetime.now(timezone.utc)
            db.commit()
        await self._emit(EventType.STATUS_CHANGED, {"status": target.value, "previous_status": previous.value})
        return True

    async def _save_state(self, **fields: Any) -> None:
        with self._db() as db:
            row = db.scalar(select(AgentState).where(AgentState.session_id == self.session_id))
            if row is None:
                row = AgentState(session_id=self.session_id)
                db.add(row)
            for key, value in fields.items():
                setattr(row, key, value)
            db.commit()

    async def _record_action(
        self, step_index: int, action_type: str, tool_name: str | None,
        input_data: dict, output_data: dict, success: bool, error: str | None, duration_ms: int,
    ) -> None:
        with self._db() as db:
            db.add(AgentAction(
                session_id=self.session_id, step_index=step_index, action_type=action_type,
                tool_name=tool_name, input_data=input_data, output_data=output_data,
                success=success, error=error, duration_ms=duration_ms,
            ))
            db.commit()