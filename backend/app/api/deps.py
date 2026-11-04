import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.session import AgentSession, SessionMember
from app.models.user import User, UserRole
from app.services import session_service

bearer_scheme = HTTPBearer(auto_error=False)

_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise _credentials_error

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_error
    return user


def require_roles(*allowed: UserRole):
    """Account-level role check (kept from Phase 2)."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return checker


# ---------- Per-session authorization (Phase 3) ----------


@dataclass
class SessionContext:
    session: AgentSession
    member: SessionMember
    user: User

    @property
    def role(self) -> UserRole:
        return self.member.role


def get_session_context(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionContext:
    """Loads the session and the caller's membership. Non-members get 404 so
    session IDs cannot be probed."""
    session = db.get(AgentSession, session_id)
    member = session_service.get_membership(db, session_id, user.id) if session else None
    if session is None or member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return SessionContext(session=session, member=member, user=user)


def require_session_role(*allowed: UserRole):
    """Dependency factory: caller must hold one of `allowed` roles IN THIS SESSION.
    The role always comes from the database, never from the client."""

    def checker(ctx: SessionContext = Depends(get_session_context)) -> SessionContext:
        if ctx.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Your role ({ctx.role.value}) is not allowed to do this",
            )
        return ctx

    return checker