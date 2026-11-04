import uuid

from sqlalchemy.orm import Session

from app.models.event import AgentEvent
from app.models.user import User
from app.websocket.events import EventType, serialize_event
from app.websocket.manager import manager


async def publish(
    db: Session,
    session_id: uuid.UUID,
    event_type: EventType,
    payload: dict,
    actor: User | None = None,
) -> dict:
    """Persist an event, then broadcast it to everyone in the session room."""
    data = dict(payload)
    if actor is not None:
        data["actor"] = {"id": str(actor.id), "username": actor.username}

    event = AgentEvent(
        session_id=session_id,
        user_id=actor.id if actor else None,
        type=event_type.value,
        payload=data,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    message = serialize_event(event)
    await manager.broadcast(str(session_id), message)
    return message