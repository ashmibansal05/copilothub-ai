
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runner import agent_runner
from app.api.deps import (
    SessionContext,
    get_current_user,
    get_session_context,
    require_session_role,
)
from app.api.limits import user_limit
from app.db.session import get_db
from app.models.event import AgentEvent
from app.models.user import User, UserRole
from app.schemas.session import (
    EventRead,
    InvitePreview,
    JoinRequest,
    SessionCreate,
    SessionDetail,
    SessionSummary,
)
from app.services import cleanup, session_service
from app.websocket.events import EventType, make_event
from app.websocket.manager import manager


router = APIRouter(prefix="/sessions", tags=["sessions"])


# ============================================================
# Existing: Create Session
# ============================================================

@router.post(
    "",
    response_model=SessionDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    data: SessionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionDetail:
    session = session_service.create_session(db, user, data)
    return session_service.build_detail(session, UserRole.OWNER)


# ============================================================
# Existing: List Sessions
# ============================================================

@router.get("", response_model=list[SessionSummary])
def list_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionSummary]:
    return session_service.list_for_user(db, user)


# ============================================================
# Phase 15: Rate-Limited Invitation Preview
# ============================================================

@router.get(
    "/invite/{code}",
    response_model=InvitePreview,
    dependencies=[
        Depends(user_limit("invite", 30, 60))
    ],
)
def preview_invite(
    code: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvitePreview:
    found = session_service.find_by_code(db, code)

    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Invalid or expired invite code",
        )

    session, role = found

    member = session_service.get_membership(
        db,
        session.id,
        user.id,
    )

    return InvitePreview(
        session_name=session.name,
        task=session.task,
        owner_name=session.owner.full_name,
        role=member.role if member else role,
        already_member=member is not None,
        session_id=session.id if member else None,
    )


# ============================================================
# Phase 15: Rate-Limited Session Joining
# ============================================================

@router.post(
    "/join",
    response_model=SessionDetail,
    dependencies=[
        Depends(user_limit("join", 20, 60))
    ],
)
async def join_session(
    data: JoinRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionDetail:
    try:
        session, member, created = session_service.join(
            db,
            user,
            data.code,
        )

    except LookupError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Invalid or expired invite code",
        )

    if created:
        await manager.broadcast(
            str(session.id),
            make_event(
                EventType.MEMBER_JOINED,
                session.id,
                {
                    "user": {
                        "id": str(user.id),
                        "username": user.username,
                    },
                    "role": member.role.value,
                },
                user.id,
            ),
        )

    return session_service.build_detail(session, member.role)


# ============================================================
# Existing: Get Session Details
# ============================================================

@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    ctx: SessionContext = Depends(get_session_context),
) -> SessionDetail:
    return session_service.build_detail(
        ctx.session,
        ctx.role,
    )


# ============================================================
# Existing: Session Event History
# ============================================================

@router.get(
    "/{session_id}/events",
    response_model=list[EventRead],
)
def list_events(
    limit: int = Query(200, ge=1, le=500),
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> list[AgentEvent]:
    stmt = (
        select(AgentEvent)
        .where(
            AgentEvent.session_id == ctx.session.id
        )
        .order_by(
            AgentEvent.created_at.desc(),
            AgentEvent.id.desc(),
        )
        .limit(limit)
    )

    # Return the selected events in chronological order.
    return list(reversed(db.scalars(stmt).all()))


# ============================================================
# Phase 15: Owner-Only Session Deletion
# ============================================================

@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session(
    ctx: SessionContext = Depends(
        require_session_role(UserRole.OWNER)
    ),
    db: Session = Depends(get_db),
) -> None:
    """
    Permanently delete a session and its associated data.

    Only the session owner may perform this operation.

    Steps:
    1. Stop the running agent.
    2. Disconnect session WebSocket clients.
    3. Delete the session and associated database records.
    4. Remove uploaded documents and vector indexes.
    """

    sid = ctx.session.id

    # Stop any running agent.
    await agent_runner.stop(sid)

    # Disconnect all active WebSocket connections.
    await manager.close_room(
        str(sid),
        4404,
    )

    # Delete session data from the database.
    # Related records must have appropriate cascade rules.
    db.delete(ctx.session)
    db.commit()

    # Remove uploaded documents and the vector index.
    await asyncio.to_thread(
        cleanup.purge_session_files,
        sid,
    )