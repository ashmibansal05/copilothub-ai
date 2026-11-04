import enum
import uuid
from datetime import datetime, timezone

from app.models.event import AgentEvent


class EventType(str, enum.Enum):
    # Persisted agent/session events
    AGENT_STARTED = "AGENT_STARTED"
    STATUS_CHANGED = "STATUS_CHANGED"
    AGENT_MESSAGE = "AGENT_MESSAGE"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    TOOL_STARTED = "TOOL_STARTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    # Ephemeral connection / presence events (not stored)
    CONNECTED = "CONNECTED"
    PONG = "PONG"
    USER_JOINED = "USER_JOINED"
    USER_LEFT = "USER_LEFT"
    MEMBER_JOINED = "MEMBER_JOINED"


def make_event(
    event_type: EventType,
    session_id: uuid.UUID | str,
    payload: dict | None = None,
    user_id: uuid.UUID | str | None = None,
) -> dict:
    """Build an ephemeral (non-persisted) event message."""
    return {
        "id": str(uuid.uuid4()),
        "session_id": str(session_id),
        "type": event_type.value,
        "payload": payload or {},
        "user_id": str(user_id) if user_id else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def serialize_event(event: AgentEvent) -> dict:
    """Same wire format as make_event, built from a stored event."""
    return {
        "id": str(event.id),
        "session_id": str(event.session_id),
        "type": event.type,
        "payload": event.payload,
        "user_id": str(event.user_id) if event.user_id else None,
        "created_at": event.created_at.isoformat(),
    }