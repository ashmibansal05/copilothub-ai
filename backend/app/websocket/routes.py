
import asyncio
import logging
import time
import uuid

from dataclasses import dataclass
from datetime import timezone

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.session import AgentSession
from app.models.user import User
from app.services import session_service
from app.websocket.events import EventType, make_event
from app.websocket.manager import Connection, manager


logger = logging.getLogger("copilothub.ws")
router = APIRouter()

AUTH_TIMEOUT_SECONDS = 5
WS_UNAUTHENTICATED = 4401
WS_FORBIDDEN = 4403


# ============================================================
# WebSocket Identity
# ============================================================

@dataclass
class WSIdentity:
    user_id: str
    username: str
    role: str
    session_status: str

    # Phase 15: JWT expiration timestamp
    expires_at: float


# ============================================================
# WebSocket Authentication
# ============================================================

def authenticate_ws(
    token: str,
    session_id: uuid.UUID,
) -> tuple[WSIdentity | None, int | None]:
    """
    Validate the JWT and the user's session membership.

    Phase 15:
    - Reject tokens issued before the latest password change.
    - Store the JWT expiration time for automatic disconnection.

    Returns:
        (identity, error_code)
    """

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])

        # JWT expiration is required for the expiry timer.
        expires_at = float(payload["exp"])

    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        return None, WS_UNAUTHENTICATED

    with SessionLocal() as db:
        user = db.get(User, user_id)

        # ----------------------------------------------------
        # Phase 15: Password Change Token Revocation
        # ----------------------------------------------------

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
            return None, WS_UNAUTHENTICATED

        # ----------------------------------------------------
        # Session Membership
        # ----------------------------------------------------

        member = session_service.get_membership(
            db,
            session_id,
            user_id,
        )

        session = db.get(
            AgentSession,
            session_id,
        )

        if member is None or session is None:
            return None, WS_FORBIDDEN

        return (
            WSIdentity(
                user_id=str(user.id),
                username=user.username,
                role=member.role.value,
                session_status=session.status.value,
                expires_at=expires_at,
            ),
            None,
        )


# ============================================================
# Close WebSocket When JWT Expires (Phase 15)
# ============================================================

async def _close_at_expiry(
    websocket: WebSocket,
    expires_at: float,
) -> None:
    """
    A WebSocket connection must not outlive the JWT
    used to authenticate it.
    """

    await asyncio.sleep(
        max(
            0.0,
            expires_at - time.time(),
        )
    )

    await _safe_close(
        websocket,
        WS_UNAUTHENTICATED,
    )


# ============================================================
# Session WebSocket Route
# ============================================================

@router.websocket("/ws/sessions/{session_id}")
async def session_socket(
    websocket: WebSocket,
    session_id: uuid.UUID,
) -> None:

    settings = get_settings()

    # --------------------------------------------------------
    # Origin Validation
    # --------------------------------------------------------

    # Reject browser connections from unknown origins.
    # Non-browser clients may send no origin header.
    origin = websocket.headers.get("origin")

    if origin and origin not in settings.cors_origin_list:
        await websocket.close(
            code=WS_FORBIDDEN,
        )
        return

    await websocket.accept()

    sid = str(session_id)

    # --------------------------------------------------------
    # Step 1: First-message authentication
    # --------------------------------------------------------

    # JWT is sent as the first WebSocket message.
    # It does not appear in the URL.

    try:
        raw = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=AUTH_TIMEOUT_SECONDS,
        )

    except (
        asyncio.TimeoutError,
        WebSocketDisconnect,
        ValueError,
        KeyError,
        RuntimeError,
    ):
        await _safe_close(
            websocket,
            WS_UNAUTHENTICATED,
        )
        return

    if (
        not isinstance(raw, dict)
        or raw.get("type") != "AUTH"
        or not isinstance(raw.get("token"), str)
    ):
        await _safe_close(
            websocket,
            WS_UNAUTHENTICATED,
        )
        return

    identity, error_code = await run_in_threadpool(
        authenticate_ws,
        raw["token"],
        session_id,
    )

    if identity is None:
        await _safe_close(
            websocket,
            error_code or WS_UNAUTHENTICATED,
        )
        return

    # --------------------------------------------------------
    # Step 2: Join the Session Room
    # --------------------------------------------------------

    conn = Connection(
        connection_id=uuid.uuid4().hex,
        websocket=websocket,
        user_id=identity.user_id,
        username=identity.username,
        role=identity.role,
    )

    first_connection = not manager.is_user_online(
        sid,
        identity.user_id,
    )

    manager.connect(
        sid,
        conn,
    )

    await manager.send(
        conn,
        make_event(
            EventType.CONNECTED,
            sid,
            {
                "my_role": identity.role,
                "status": identity.session_status,
                "online_users": manager.online_users(sid),
            },
        ),
    )

    if first_connection:
        await manager.broadcast(
            sid,
            make_event(
                EventType.USER_JOINED,
                sid,
                {
                    "user": {
                        "user_id": identity.user_id,
                        "username": identity.username,
                        "role": identity.role,
                    }
                },
                identity.user_id,
            ),
            exclude=conn.connection_id,
        )

    # --------------------------------------------------------
    # Phase 15: Start JWT Expiration Task
    # --------------------------------------------------------

    expiry_task = asyncio.create_task(
        _close_at_expiry(
            websocket,
            identity.expires_at,
        )
    )

    # --------------------------------------------------------
    # Step 3: Serve WebSocket Messages
    # --------------------------------------------------------

    # Clients may only send PING messages.
    # Mutations must use REST APIs, where role checks occur.

    try:
        while True:
            try:
                message = await websocket.receive_json()

            except (ValueError, KeyError):
                # Ignore malformed messages.
                continue

            if (
                isinstance(message, dict)
                and message.get("type") == "PING"
            ):
                await manager.send(
                    conn,
                    make_event(
                        EventType.PONG,
                        sid,
                    ),
                )

    except WebSocketDisconnect:
        pass

    except Exception:
        logger.exception(
            "WebSocket error for user %s",
            identity.username,
        )

    finally:
        # ----------------------------------------------------
        # Phase 15: Cancel Expiration Timer
        # ----------------------------------------------------

        expiry_task.cancel()

        # ----------------------------------------------------
        # Disconnect the User
        # ----------------------------------------------------

        fully_offline = manager.disconnect(
            sid,
            conn.connection_id,
        )

        if fully_offline:
            await manager.broadcast(
                sid,
                make_event(
                    EventType.USER_LEFT,
                    sid,
                    {
                        "user": {
                            "user_id": identity.user_id,
                            "username": identity.username,
                        }
                    },
                    identity.user_id,
                ),
            )


# ============================================================
# Safe WebSocket Closure
# ============================================================

async def _safe_close(
    websocket: WebSocket,
    code: int,
) -> None:
    """
    Safely close a WebSocket connection.

    Ignore RuntimeError if the socket has already closed.
    """

    try:
        await websocket.close(
            code=code,
        )

    except RuntimeError:
        pass