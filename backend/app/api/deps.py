
import uuid
from dataclasses import dataclass
from datetime import timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.session import AgentSession, SessionMember
from app.models.user import User, UserRole
from app.services import session_service


# ============================================================
# Authentication
# ============================================================

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
    """
    Authenticate the current user using a JWT access token.

    Phase 15:
    Tokens issued before the user's latest password change
    are rejected.
    """

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

    # ========================================================
    # Phase 15: Password Change Token Revocation
    # ========================================================

    changed = (
        user.password_changed_at
        if user is not None
        else None
    )

    # SQLite may return timezone-naive datetime values.
    if changed is not None and changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)

    if (
        user is None
        or not user.is_active
        or (
            changed is not None
            and int(payload.get("iat", 0))
            < int(changed.timestamp())
        )
    ):
        raise _credentials_error

    return user


# ============================================================
# Account-Level Role Authorization
# ============================================================

def require_roles(*allowed: UserRole):
    """
    Account-level role check (kept from Phase 2).
    """

    def checker(
        user: User = Depends(get_current_user),
    ) -> User:

        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You do not have permission "
                    "to perform this action"
                ),
            )

        return user

    return checker


# ============================================================
# Per-Session Authorization (Phase 3)
# ============================================================

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
    """
    Load the session and the caller's membership.

    Non-members receive HTTP 404 so session IDs
    cannot be probed.
    """

    session = db.get(
        AgentSession,
        session_id,
    )

    member = (
        session_service.get_membership(
            db,
            session_id,
            user.id,
        )
        if session
        else None
    )

    if session is None or member is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Session not found",
        )

    return SessionContext(
        session=session,
        member=member,
        user=user,
    )


# ============================================================
# Session-Level Role Authorization
# ============================================================

def require_session_role(*allowed: UserRole):
    """
    Caller must hold one of the allowed roles
    in the specified session.

    The role is loaded from the database,
    never trusted from the client.
    """

    def checker(
        ctx: SessionContext = Depends(get_session_context),
    ) -> SessionContext:

        if ctx.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                (
                    f"Your role ({ctx.role.value}) "
                    "is not allowed to do this"
                ),
            )

        return ctx

    return checker