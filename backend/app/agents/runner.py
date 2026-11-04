import asyncio
import logging
import uuid

from app.agents.factory import create_brain
from app.agents.orchestrator import AgentOrchestrator

logger = logging.getLogger("copilothub.agent")


class AgentRunner:
    """Keeps one background task per running session (in-memory, single process)."""

    def __init__(self) -> None:
        self.brain_factory = create_brain  # replaceable in tests
        self._orchestrators: dict[uuid.UUID, AgentOrchestrator] = {}
        self._tasks: dict[uuid.UUID, asyncio.Task] = {}

    def is_active(self, session_id: uuid.UUID) -> bool:
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

    async def start(self, session_id: uuid.UUID) -> bool:
        if self.is_active(session_id):
            return False
        orchestrator = AgentOrchestrator(session_id, brain_factory=lambda: self.brain_factory())
        task = asyncio.create_task(orchestrator.run(), name=f"agent-{session_id}")
        self._orchestrators[session_id] = orchestrator
        self._tasks[session_id] = task
        task.add_done_callback(lambda t, sid=session_id: self._cleanup(sid, t))
        return True

    def pause(self, session_id: uuid.UUID) -> None:
        if (orch := self._orchestrators.get(session_id)) is not None:
            orch.pause()

    def resume(self, session_id: uuid.UUID) -> None:
        if (orch := self._orchestrators.get(session_id)) is not None:
            orch.resume()

    async def stop(self, session_id: uuid.UUID) -> None:
        task = self._tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.wait({task}, timeout=3)

    def _cleanup(self, session_id: uuid.UUID, task: asyncio.Task) -> None:
        if self._tasks.get(session_id) is task:
            self._tasks.pop(session_id, None)
            self._orchestrators.pop(session_id, None)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Agent task crashed: %r", task.exception())


agent_runner = AgentRunner()