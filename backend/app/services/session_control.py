from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.agents.runner import agent_runner
from app.api.deps import SessionContext
from app.models.session import AgentStatus
from app.schemas.session import StateResponse
from app.services import event_service
from app.websocket.events import EventType

# action -> (allowed current states, new state, specific event, system message)
TRANSITIONS: dict[str, tuple[set[AgentStatus], AgentStatus, EventType | None, str]] = {
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
    "resume": ({AgentStatus.PAUSED}, AgentStatus.RUNNING, EventType.RESUMED, "Resumed by {user}."),
    "stop": (
        {AgentStatus.CREATED, AgentStatus.RUNNING, AgentStatus.PLANNING, AgentStatus.PAUSED},
        AgentStatus.CANCELLED,
        None,
        "Stopped by {user}.",
    ),
}


async def apply_transition(action: str, ctx: SessionContext, db: Session) -> StateResponse:
    allowed_from, target, event_type, template = TRANSITIONS[action]
    session = ctx.session
    session_id = session.id
    previous = session.status

    if previous not in allowed_from:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot {action} a session that is {previous.value}"
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
        agent_runner.pause(session_id)
    elif action == "resume":
        agent_runner.resume(session_id)
    elif action == "stop":
        await agent_runner.stop(session_id)

    user = ctx.user
    if event_type is not None:
        await event_service.publish(db, session_id, event_type, {}, user)
    await event_service.publish(
        db,
        session_id,
        EventType.STATUS_CHANGED,
        {"status": target.value, "previous_status": previous.value},
        user,
    )
    await event_service.publish(
        db,
        session_id,
        EventType.AGENT_MESSAGE,
        {"kind": "system", "text": template.format(user=user.username)},
        user,
    )

    if action == "start":
        await agent_runner.start(session_id)

    return StateResponse(session_id=session_id, status=target, previous_status=previous)