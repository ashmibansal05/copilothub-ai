"""CoPilotHub's shared multi-step workflow coordinator.

Research and code generation run sequentially for HYBRID tasks. Collaborators
may queue code changes while research or another code pass runs. Requests live in
the database, survive server restarts, and are versioned by the existing code
artifact service. No parallel local-LLM jobs are launched for one session.

The in-process supervisor is designed for a single backend worker. Research
itself is not restartable mid-inference: interrupted sessions are recoverable
through the existing controls, not silently represented as completed work.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from sqlalchemy import select

from app.agents.runner import agent_runner
from app.db import session as db_session
from app.models.session import AgentSession, AgentStatus
from app.models.workflow_request import WorkflowRequest
from app.services import event_service
from app.websocket.events import EventType

_hybrid_jobs: dict[uuid.UUID, asyncio.Task] = {}
_claimed: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)


def queue_code_request(session_id: uuid.UUID, instruction: str,
                       requested_by: uuid.UUID | None = None) -> int:
    text = (instruction or "").strip()
    with db_session.SessionLocal() as db:
        db.add(WorkflowRequest(session_id=session_id, instruction=text, requested_by=requested_by,
                               status="QUEUED", attempts=0))
        db.commit()
        return len(queued_code_requests(session_id))


def queued_code_requests(session_id: uuid.UUID) -> list[str]:
    with db_session.SessionLocal() as db:
        rows = db.scalars(select(WorkflowRequest).where(
            WorkflowRequest.session_id == session_id,
            WorkflowRequest.status == "QUEUED",
        ).order_by(WorkflowRequest.created_at, WorkflowRequest.id)).all()
        return [r.instruction for r in rows]


def consume_code_request(session_id: uuid.UUID) -> str:
    with db_session.SessionLocal() as db:
        rows = db.scalars(select(WorkflowRequest).where(
            WorkflowRequest.session_id == session_id,
            WorkflowRequest.status == "QUEUED",
        ).order_by(WorkflowRequest.created_at, WorkflowRequest.id).with_for_update()).all()
        for row in rows:
            row.status = "IN_PROGRESS"
            row.attempts += 1
        ids = [r.id for r in rows]
        texts = [r.instruction.strip() for r in rows if r.instruction.strip()]
        db.commit()
    if ids:
        _claimed[session_id].extend(ids)
    if not texts:
        return ""
    if len(texts) == 1:
        return texts[0]
    return "Queued revision requests from collaborators:\n" + "\n".join(f"- {s}" for s in texts)


def finish_claimed_requests(session_id: uuid.UUID, success: bool) -> None:
    ids = _claimed.pop(session_id, [])
    if not ids:
        return
    with db_session.SessionLocal() as db:
        rows = db.scalars(select(WorkflowRequest).where(WorkflowRequest.id.in_(ids))).all()
        for row in rows:
            row.status = "DONE" if success else "QUEUED"
        db.commit()


def recover_interrupted_requests() -> int:
    """Requeue interrupted instructions; never lose human instructions on restart."""
    with db_session.SessionLocal() as db:
        rows = db.scalars(select(WorkflowRequest).where(WorkflowRequest.status == "IN_PROGRESS")).all()
        for row in rows:
            row.status = "QUEUED"
        db.commit()
        return len(rows)


def is_hybrid_active(session_id: uuid.UUID) -> bool:
    task = _hybrid_jobs.get(session_id)
    return task is not None and not task.done()


def stop_hybrid(session_id: uuid.UUID) -> None:
    task = _hybrid_jobs.get(session_id)
    if task is not None and not task.done():
        task.cancel()
    finish_claimed_requests(session_id, success=False)


async def _run_hybrid(session_id: uuid.UUID, task: str) -> None:
    from app.api.code import start_automatic_code
    try:
        started = await agent_runner.start(session_id)
        if not started:
            return
        with db_session.SessionLocal() as db:
            await event_service.publish(db, session_id, EventType.AGENT_MESSAGE, {
                "kind": "system", "text":
                "Research runs first. Code generation starts when research finishes. "
                "You can add code requests at any time.",
            })
        while agent_runner.is_active(session_id):
            await asyncio.sleep(1)

        with db_session.SessionLocal() as db:
            session = db.get(AgentSession, session_id)
            if session is None or session.status in (AgentStatus.CANCELLED, AgentStatus.FAILED):
                return
            if session.status != AgentStatus.COMPLETED:
                # Do not start a code phase while a research review is pending.
                return
            previous = session.status
            session.status = AgentStatus.RUNNING
            session.ended_at = None
            db.commit()
            await event_service.publish(db, session_id, EventType.STATUS_CHANGED,
                                        {"status": "RUNNING", "previous_status": previous.value})
            await event_service.publish(db, session_id, EventType.AGENT_MESSAGE,
                {"kind": "system", "text": "Research finished. Preparing the project files now."})
        start_automatic_code(session_id, task, instruction=consume_code_request(session_id))
    except asyncio.CancelledError:
        raise
    finally:
        _hybrid_jobs.pop(session_id, None)


def start_hybrid(session_id: uuid.UUID, task: str) -> bool:
    current = _hybrid_jobs.get(session_id)
    if current is not None and not current.done():
        return False
    _hybrid_jobs[session_id] = asyncio.create_task(_run_hybrid(session_id, task), name=f"hybrid-{session_id}")
    return True
