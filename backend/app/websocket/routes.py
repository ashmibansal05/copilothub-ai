import asyncio
import logging
import uuid
from dataclasses import dataclass

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


@dataclass
class WSIdentity:
    user_id: str
    username: str
    role: str
    session_status: str


def authenticate_ws(token: str, session_id: uuid.UUID) -> tuple[WSIdentity | None, int | None]:
    """Validate the JWT and the user's membership. Returns (identity, error_code)."""
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None, WS_UNAUTHENTICATED

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return None, WS_UNAUTHENTICATED
        member = session_service.get_membership(db, session_id, user_id)
        session = db.get(AgentSession, session_id)
        if member is None or session is None:
            return None, WS_FORBIDDEN
        return (
            WSIdentity(
                user_id=str(user.id),
                username=user.username,
                role=member.role.value,
                session_status=session.status.value,
            ),
            None,
        )


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: uuid.UUID) -> None:
    settings = get_settings()

    # Reject browser connections from unknown origins (non-browser clients send none).
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.cors_origin_list:
        await websocket.close(code=WS_FORBIDDEN)
        return

    await websocket.accept()
    sid = str(session_id)

    # --- Step 1: first-message authentication (token never appears in the URL) ---
    try:
        raw = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, KeyError, RuntimeError):
        await _safe_close(websocket, WS_UNAUTHENTICATED)
        return

    if not isinstance(raw, dict) or raw.get("type") != "AUTH" or not isinstance(raw.get("token"), str):
        await _safe_close(websocket, WS_UNAUTHENTICATED)
        return

    identity, error_code = await run_in_threadpool(authenticate_ws, raw["token"], session_id)
    if identity is None:
        await _safe_close(websocket, error_code or WS_UNAUTHENTICATED)
        return

    # --- Step 2: join the room ---
    conn = Connection(
        connection_id=uuid.uuid4().hex,
        websocket=websocket,
        user_id=identity.user_id,
        username=identity.username,
        role=identity.role,
    )
    first_connection = not manager.is_user_online(sid, identity.user_id)
    manager.connect(sid, conn)

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
                {"user": {"user_id": identity.user_id, "username": identity.username, "role": identity.role}},
                identity.user_id,
            ),
            exclude=conn.connection_id,
        )

    # --- Step 3: serve. Clients may only PING; all mutations go through REST
    #     so that role checks happen in exactly one place. ---
    try:
        while True:
            try:
                message = await websocket.receive_json()
            except (ValueError, KeyError):
                continue  # ignore malformed / binary frames
            if isinstance(message, dict) and message.get("type") == "PING":
                await manager.send(conn, make_event(EventType.PONG, sid))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for user %s", identity.username)
    finally:
        fully_offline = manager.disconnect(sid, conn.connection_id)
        if fully_offline:
            await manager.broadcast(
                sid,
                make_event(
                    EventType.USER_LEFT,
                    sid,
                    {"user": {"user_id": identity.user_id, "username": identity.username}},
                    identity.user_id,
                ),
            )


async def _safe_close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except RuntimeError:
        pass