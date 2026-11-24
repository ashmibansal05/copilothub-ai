
import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.agents.runner import agent_runner
from app.api.deps import SessionContext
from app.models.session import AgentStatus
from app.schemas.session import StateResponse
from app.services import approval_service, analytics_service, event_service
from app.websocket.events import EventType


# action -> (allowed current states, new state, specific event, system message)
TRANSITIONS: dict[
    str,
    tuple[set[AgentStatus], AgentStatus, EventType | None, str]
] = {
    "start": (
        {AgentStatus.CREATED},
        AgentStatus.RUNNING,
        EventType.AGENT_STARTED,
        "Session started by {user}.",
    ),
    "pause": (
        {AgentStatus.RUNNING, AgentStatus.PLANNING},
        AgentStatus.PAUSED,
        EventType.PAUSED,
        "Paused by {user}. The agent stops after its current step.",
    ),
    "resume": (
        {AgentStatus.PAUSED},
        AgentStatus.RUNNING,
        EventType.RESUMED,
        "Resumed by {user}.",
    ),
    "stop": (
        {
            AgentStatus.CREATED,
            AgentStatus.RUNNING,
            AgentStatus.PLANNING,
            AgentStatus.PAUSED,
            AgentStatus.WAITING_FOR_APPROVAL,
        },
        AgentStatus.CANCELLED,
        None,
        "Stopped by {user}.",
    ),
}


async def apply_transition(
    action: str,
    ctx: SessionContext,
    db: Session,
) -> StateResponse:
    allowed_from, target, event_type, template = TRANSITIONS[action]

    session = ctx.session
    session_id = session.id
    previous = session.status

    if previous not in allowed_from:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot {action} a session that is {previous.value}",
        )

    now = datetime.now(timezone.utc)
    session.status = target

    if action == "start":
        session.started_at = now

    if target == AgentStatus.CANCELLED:
        session.ended_at = now

    db.commit()

    # Tell the agent runner right after the DB change.
    if action == "pause":
        from app.api.code import pause_automatic_code
        pause_automatic_code(session_id)
        agent_runner.pause(session_id)

    elif action == "resume":
        from app.api.code import resume_automatic_code, start_automatic_code, code_generation_active
        from app.services.coding_agent import classify_task
        from app.services.workflow_service import start_hybrid, is_hybrid_active, consume_code_request
        resume_automatic_code(session_id)
        agent_runner.resume(session_id)
        kind = classify_task(session.task)
        # When a Docker restart destroyed the previous in-memory job, Resume
        # actually creates the missing worker rather than only opening a gate.
        if kind == "CODING" and not code_generation_active(session_id):
            start_automatic_code(session_id, session.task,
                                 instruction=consume_code_request(session_id))
        elif kind == "HYBRID" and not is_hybrid_active(session_id) and not code_generation_active(session_id):
            from app.models.report import Report
            from sqlalchemy import select
            research_report = db.scalar(select(Report).where(
                Report.session_id == session_id,
                Report.kind.in_(["DRAFT", "FINAL"]),
            ).order_by(Report.created_at.desc()).limit(1))
            if research_report is None:
                start_hybrid(session_id, session.task)
            else:
                start_automatic_code(session_id, session.task,
                                     instruction=consume_code_request(session_id))
        elif kind == "RESEARCH" and not agent_runner.is_active(session_id):
            await agent_runner.start(session_id)

    elif action == "stop":
        from app.api.code import cancel_automatic_code
        from app.services.workflow_service import stop_hybrid
        cancel_automatic_code(session_id)
        stop_hybrid(session_id)
        await agent_runner.stop(session_id)

    user = ctx.user

    if event_type is not None:
        await event_service.publish(
            db,
            session_id,
            event_type,
            {},
            user,
        )

    await event_service.publish(
        db,
        session_id,
        EventType.STATUS_CHANGED,
        {
            "status": target.value,
            "previous_status": previous.value,
        },
        user,
    )

    await event_service.publish(
        db,
        session_id,
        EventType.AGENT_MESSAGE,
        {
            "kind": "system",
            "text": template.format(user=user.username),
        },
        user,
    )

    if action == "stop" and approval_service.expire_pending(
        db, session_id
    ):
        await event_service.publish(
            db,
            session_id,
            EventType.APPROVAL_COMPLETED,
            {"expired": True},
            user,
        )

    # -------------------------------------------------------------
    # Phase 14 - Record session analytics when stopped
    # -------------------------------------------------------------
    if action == "stop":
        try:
            await asyncio.to_thread(
                analytics_service.record_session_end,
                session_id,
            )
        except Exception:
            pass  # Analytics must never block stopping a session.

    if action == "start":
        from app.services.coding_agent import classify_task
        from app.api.code import start_automatic_code
        from app.services.workflow_service import start_hybrid
        kind = classify_task(session.task)
        if kind == "CODING":
            # Skip the research-only ACT/tool loop for programming tasks.
            start_automatic_code(session_id, session.task)
        elif kind == "HYBRID":
            # Keep the workflow simple: research first, then automatic code generation.
            start_hybrid(session_id, session.task)
        else:
            await agent_runner.start(session_id)

    return StateResponse(
        session_id=session_id,
        status=target,
        previous_status=previous,
    )