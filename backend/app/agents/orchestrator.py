import asyncio
import logging
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.brain import AgentBrain, StepResult
from app.agents.state import AgentGraphState
from app.core.config import Settings, get_settings
from app.db import session as db_session
from app.models.agent import AgentAction, AgentState
from app.models.session import AgentSession, AgentStatus
from app.services import event_service
from app.websocket.events import EventType

logger = logging.getLogger("copilothub.agent")

BrainFactory = Callable[[], Awaitable[tuple[AgentBrain, str | None]]]

FINISHABLE = {AgentStatus.RUNNING, AgentStatus.PLANNING, AgentStatus.PAUSED}
TERMINAL = {AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED}
PLAN_DONE_PROGRESS = 10


class AgentStepError(Exception):
    """A node failed after exhausting its retries."""


class AgentLimitError(Exception):
    """The run exceeded its time budget."""


class AgentOrchestrator:
    """Runs one session's agent as a LangGraph workflow:

        plan -> act -> observe -> evaluate -+-> act (next step or retry)
                                            +-> finalize -> END
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        brain_factory: BrainFactory,
        settings: Settings | None = None,
    ) -> None:
        self.session_id = session_id
        self.settings = settings or get_settings()
        self.brain_factory = brain_factory
        self.brain: AgentBrain | None = None
        self.resume_event = asyncio.Event()
        self.resume_event.set()  # set = running, cleared = paused
        self._started = time.monotonic()
        self._paused_total = 0.0
        self.graph = self._build_graph()

    # ------------------------------------------------------------------ control
    def pause(self) -> None:
        self.resume_event.clear()

    def resume(self) -> None:
        self.resume_event.set()

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
            "evaluate", self.route_after_evaluate, {"act": "act", "finalize": "finalize"}
        )
        g.add_edge("finalize", END)
        return g.compile()

    @staticmethod
    def route_after_evaluate(state: AgentGraphState) -> str:
        return "finalize" if state.get("decision") == "complete" else "act"

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
                "retries": 0, "observations": [],
            }
            limit = 3 * self.settings.agent_max_steps + 10  # LangGraph counts every node visit
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
        await self._set_status(AgentStatus.PLANNING, {AgentStatus.RUNNING})
        await self._emit(EventType.STEP_STARTED, {
            "phase": "PLAN", "step_index": 0, "total_steps": 0, "step": "Planning the research",
            "progress": 0, "engine": self.brain.engine,
        })
        started = time.monotonic()
        plan = await self._attempt(
            "PLAN",
            lambda: self.brain.make_plan(state["task"], self._constraints(), self.settings.agent_max_steps),
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
        return {"plan": plan, "step_index": 0}

    async def act_node(self, state: AgentGraphState) -> dict[str, Any]:
        await self.checkpoint()
        assert self.brain is not None
        i, plan = state["step_index"], state["plan"]
        n, step = len(plan), plan[i]
        tool = self.brain.tool_for_step(step)
        progress = self._progress(i, n)

        await self._save_state(current_step=step, progress=progress)
        await self._emit(EventType.STEP_STARTED, {
            "phase": "ACT", "step_index": i + 1, "total_steps": n, "step": step, "progress": progress,
        })
        await self._emit(EventType.TOOL_STARTED, {
            "tool": tool, "step_index": i + 1, "input": {"step": step}, "simulated": self.brain.simulated,
        })

        started = time.monotonic()
        result: StepResult = await self._attempt(
            "ACT",
            lambda: self.brain.execute_step(
                state["task"], step, state.get("observations", []), self._constraints()
            ),
            step_index=i + 1, tool_name=tool, input_data={"step": step},
        )
        duration = self._ms(started)
        await self._record_action(
            i + 1, "TOOL_CALL", result.tool, {"step": step},
            {"output": result.output[:2000], "sources": result.sources},
            result.success, None, duration,
        )
        await self._emit(EventType.TOOL_COMPLETED, {
            "tool": result.tool, "step_index": i + 1, "success": result.success,
            "duration_ms": duration, "output": result.output[:500],
            "sources": result.sources, "simulated": result.simulated,
        })
        return {"last_result": asdict(result), "steps_executed": state.get("steps_executed", 0) + 1}

    async def observe_node(self, state: AgentGraphState) -> dict[str, Any]:
        i, plan = state["step_index"], state["plan"]
        res = state["last_result"]
        observation = {
            "step_index": i + 1, "step": plan[i], "tool": res["tool"],
            "finding": res["output"][:1500], "success": res["success"],
            "simulated": res["simulated"], "sources": res["sources"],
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

        progress = self._progress(next_index, n)
        await self._emit(EventType.STEP_COMPLETED, {
            "phase": "ACT", "step_index": i + 1, "total_steps": n, "step": step,
            "confidence": ev.confidence, "ok": ev.ok, "note": ev.note,
            "completed_steps": next_index, "progress": progress, "decision": decision,
        })
        await self._save_state(step_index=next_index, progress=progress, confidence=ev.confidence)
        return {"confidence": ev.confidence, "step_index": next_index, "retries": retries, "decision": decision}

    async def finalize_node(self, state: AgentGraphState) -> dict[str, Any]:
        await self.checkpoint()
        assert self.brain is not None
        started = time.monotonic()
        summary = await self._attempt(
            "FINALIZE", lambda: self.brain.summarize(state["task"], state.get("observations", []))
        )
        await self._record_action(
            len(state["plan"]) + 1, "FINALIZE", None, {}, {"summary": summary[:3000]}, True, None, self._ms(started)
        )
        await self._emit(EventType.AGENT_MESSAGE, {
            "kind": "agent", "simulated": self.brain.simulated, "text": f"Draft summary:\n{summary}",
        })
        return {"summary": summary}

    # ------------------------------------------------------------------ finishing
    async def _complete(self, final: AgentGraphState) -> None:
        await self._save_state(current_step="Completed", progress=100)
        if await self._set_status(AgentStatus.COMPLETED, FINISHABLE):
            await self._emit(EventType.COMPLETED, {
                "summary": final.get("summary", ""), "confidence": final.get("confidence"),
            })

    async def _fail(self, error: str) -> None:
        await self._save_state(current_step="Failed")
        await self._emit(EventType.AGENT_MESSAGE, {
            "kind": "escalation",
            "text": f"The agent stopped because of an error and needs human attention: {error}",
        })
        if await self._set_status(AgentStatus.FAILED, FINISHABLE):
            await self._emit(EventType.FAILED, {"error": error})

    # ------------------------------------------------------------------ helpers
    def _constraints(self) -> list[str]:
        """Active human constraints. Implemented in Phase 8 (always empty for now)."""
        return []

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