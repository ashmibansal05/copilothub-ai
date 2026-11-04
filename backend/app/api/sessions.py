import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, get_current_user, get_session_context
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
from app.services import session_service
from app.websocket.events import EventType, make_event
from app.websocket.manager import manager

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionDetail, status_code=status.HTTP_201_CREATED)
def create_session(
    data: SessionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionDetail:
    session = session_service.create_session(db, user, data)
    return session_service.build_detail(session, UserRole.OWNER)


@router.get("", response_model=list[SessionSummary])
def list_sessions(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[SessionSummary]:
    return session_service.list_for_user(db, user)


@router.get("/invite/{code}", response_model=InvitePreview)
def preview_invite(
    code: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvitePreview:
    found = session_service.find_by_code(db, code)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired invite code")
    session, role = found
    member = session_service.get_membership(db, session.id, user.id)
    return InvitePreview(
        session_name=session.name,
        task=session.task,
        owner_name=session.owner.full_name,
        role=member.role if member else role,
        already_member=member is not None,
        session_id=session.id if member else None,
    )


@router.post("/join", response_model=SessionDetail)
async def join_session(
    data: JoinRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionDetail:
    try:
        session, member, created = session_service.join(db, user, data.code)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired invite code")

    if created:
        await manager.broadcast(
            str(session.id),
            make_event(
                EventType.MEMBER_JOINED,
                session.id,
                {"user": {"id": str(user.id), "username": user.username}, "role": member.role.value},
                user.id,
            ),
        )
    return session_service.build_detail(session, member.role)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(ctx: SessionContext = Depends(get_session_context)) -> SessionDetail:
    return session_service.build_detail(ctx.session, ctx.role)


@router.get("/{session_id}/events", response_model=list[EventRead])
def list_events(
    limit: int = Query(200, ge=1, le=500),
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> list[AgentEvent]:
    stmt = (
        select(AgentEvent)
        .where(AgentEvent.session_id == ctx.session.id)
        .order_by(AgentEvent.created_at.desc())
        .limit(limit)
    )
    return list(reversed(db.scalars(stmt).all()))  # oldest first