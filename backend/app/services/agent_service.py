import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import session as db_session
from app.models.agent import AgentState
from app.models.intervention import Intervention
from app.models.session import AgentSession, AgentStatus
from app.schemas.agent import AgentStateRead
from app.services import approval_service, event_service
from app.services.constraint_manager import ConstraintManager
from app.services.readers import approval_read, constraint_read, intervention_read
from app.websocket.events import EventType

logger = logging.getLogger("copilothub.agent")


def get_state_row(db: Session, session_id: uuid.UUID) -> AgentState | None:
    return db.scalar(select(AgentState).where(AgentState.session_id == session_id))


def build_state_read(db: Session, session: AgentSession) -> AgentStateRead:
    st = get_state_row(db, session.id)
    interventions = db.scalars(
        select(Intervention)
        .options(joinedload(Intervention.user))
        .where(Intervention.session_id == session.id)
        .order_by(Intervention.created_at.desc())
        .limit(20)
    ).all()
    pending = approval_service.get_pending(db, session.id)
    return AgentStateRead(
        session_id=session.id,
        status=session.status,
        current_task=session.task,
        current_step=st.current_step if st else None,
        step_index=st.step_index if st else 0,
        total_steps=st.total_steps if st else 0,
        progress=st.progress if st else 0,
        confidence=st.confidence if st else None,
        engine=st.engine if st else None,
        plan=list(st.plan or []) if st else [],
        recent_actions=list(st.recent_actions or []) if st else [],
        tool_results=list(st.tool_results or []) if st else [],
        active_constraints=[constraint_read(c) for c in ConstraintManager.active(db, session.id)],
        human_interventions=[intervention_read(i) for i in interventions],
        pending_approval=approval_read(pending) if pending else None,
    )


async def recover_orphaned_sessions() -> int:
    """Agent tasks live in memory. After a server restart, any session still
    marked as running can never finish, so mark it FAILED and tell its members."""
    stuck = [
        AgentStatus.RUNNING,
        AgentStatus.PLANNING,
        AgentStatus.PAUSED,
        AgentStatus.WAITING_FOR_APPROVAL,
    ]
    with db_session.SessionLocal() as db:
        ids = list(db.scalars(select(AgentSession.id).where(AgentSession.status.in_(stuck))).all())

    for sid in ids:
        with db_session.SessionLocal() as db:
            row = db.get(AgentSession, sid)
            if row is None:
                continue
            previous = row.status
            row.status = AgentStatus.FAILED
            row.ended_at = datetime.now(timezone.utc)
            db.commit()
            if approval_service.expire_pending(db, sid):
                await event_service.publish(db, sid, EventType.APPROVAL_COMPLETED, {"expired": True})
            await event_service.publish(
                db, sid, EventType.AGENT_MESSAGE,
                {"kind": "escalation", "text": "The server restarted while the agent was running, so the run was interrupted."},
            )
            await event_service.publish(
                db, sid, EventType.STATUS_CHANGED,
                {"status": AgentStatus.FAILED.value, "previous_status": previous.value},
            )
            await event_service.publish(db, sid, EventType.FAILED, {"error": "Interrupted by server restart"})
    if ids:
        logger.warning("Marked %d interrupted session(s) as FAILED", len(ids))
    return len(ids)