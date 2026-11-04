import secrets
import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.session import AgentSession, SessionMember
from app.models.user import User, UserRole
from app.schemas.session import (
    MemberRead,
    SessionCreate,
    SessionDetail,
    SessionSummary,
)

# No 0/O/1/I so codes are easy to read aloud and type.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


def _code_exists(db: Session, code: str) -> bool:
    stmt = select(AgentSession.id).where(
        or_(AgentSession.editor_code == code, AgentSession.viewer_code == code)
    )
    return db.scalar(stmt) is not None


def generate_code(db: Session, avoid: str | None = None) -> str:
    for _ in range(20):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code != avoid and not _code_exists(db, code):
            return code
    raise RuntimeError("Could not generate a unique invite code")


def create_session(db: Session, owner: User, data: SessionCreate) -> AgentSession:
    editor_code = generate_code(db)
    viewer_code = generate_code(db, avoid=editor_code)
    session = AgentSession(
        name=data.name,
        task=data.task,
        owner_id=owner.id,
        editor_code=editor_code,
        viewer_code=viewer_code,
    )
    session.members.append(SessionMember(user_id=owner.id, role=UserRole.OWNER))
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_membership(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> SessionMember | None:
    return db.scalar(
        select(SessionMember).where(
            SessionMember.session_id == session_id, SessionMember.user_id == user_id
        )
    )


def find_by_code(db: Session, code: str) -> tuple[AgentSession, UserRole] | None:
    code = code.strip().upper()
    session = db.scalar(select(AgentSession).where(AgentSession.editor_code == code))
    if session:
        return session, UserRole.EDITOR
    session = db.scalar(select(AgentSession).where(AgentSession.viewer_code == code))
    if session:
        return session, UserRole.VIEWER
    return None


def join(db: Session, user: User, code: str) -> tuple[AgentSession, SessionMember, bool]:
    """Join via invite code. Returns (session, member, created).
    Joining twice is idempotent and never changes an existing role."""
    found = find_by_code(db, code)
    if found is None:
        raise LookupError("invalid code")
    session, role = found

    existing = get_membership(db, session.id, user.id)
    if existing:
        return session, existing, False

    member = SessionMember(session_id=session.id, user_id=user.id, role=role)
    db.add(member)
    try:
        db.commit()
    except IntegrityError:  # two simultaneous joins
        db.rollback()
        existing = get_membership(db, session.id, user.id)
        if existing is None:
            raise
        return session, existing, False
    db.refresh(member)
    return session, member, True


def list_for_user(db: Session, user: User) -> list[SessionSummary]:
    stmt = (
        select(AgentSession)
        .join(SessionMember, SessionMember.session_id == AgentSession.id)
        .where(SessionMember.user_id == user.id)
        .options(selectinload(AgentSession.members), selectinload(AgentSession.owner))
        .order_by(AgentSession.created_at.desc())
    )
    result = []
    for s in db.scalars(stmt).all():
        my_role = next(m.role for m in s.members if m.user_id == user.id)
        result.append(build_summary(s, my_role))
    return result


def build_summary(session: AgentSession, my_role: UserRole) -> SessionSummary:
    return SessionSummary(
        id=session.id,
        name=session.name,
        task=session.task,
        status=session.status,
        my_role=my_role,
        member_count=len(session.members),
        owner_username=session.owner.username,
        created_at=session.created_at,
    )


def build_detail(session: AgentSession, my_role: UserRole) -> SessionDetail:
    is_owner = my_role == UserRole.OWNER
    members = sorted(session.members, key=lambda m: m.created_at)
    return SessionDetail(
        **build_summary(session, my_role).model_dump(),
        owner_id=session.owner_id,
        members=[
            MemberRead(
                user_id=m.user_id,
                username=m.user.username,
                full_name=m.user.full_name,
                role=m.role,
                joined_at=m.created_at,
            )
            for m in members
        ],
        editor_code=session.editor_code if is_owner else None,
        viewer_code=session.viewer_code if is_owner else None,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )