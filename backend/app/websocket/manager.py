import logging
from dataclasses import dataclass

from fastapi import WebSocket

logger = logging.getLogger("copilothub.ws")


@dataclass
class Connection:
    connection_id: str
    websocket: WebSocket
    user_id: str
    username: str
    role: str


class ConnectionManager:
    """In-memory rooms: session_id -> {connection_id -> Connection}.
    Single-process only; multiple workers would need Redis pub/sub."""

    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, Connection]] = {}

    def connect(self, session_id: str, conn: Connection) -> None:
        self._rooms.setdefault(session_id, {})[conn.connection_id] = conn

    def disconnect(self, session_id: str, connection_id: str) -> bool:
        """Remove a connection. Returns True if that user has no other open
        connections left in the room (i.e. they are now fully offline)."""
        room = self._rooms.get(session_id, {})
        conn = room.pop(connection_id, None)
        if not room:
            self._rooms.pop(session_id, None)
        if conn is None:
            return False
        return not any(c.user_id == conn.user_id for c in room.values())

    def is_user_online(self, session_id: str, user_id: str) -> bool:
        return any(c.user_id == user_id for c in self._rooms.get(session_id, {}).values())

    def online_users(self, session_id: str) -> list[dict]:
        seen: dict[str, dict] = {}
        for c in self._rooms.get(session_id, {}).values():
            seen.setdefault(
                c.user_id, {"user_id": c.user_id, "username": c.username, "role": c.role}
            )
        return list(seen.values())

    async def send(self, conn: Connection, message: dict) -> None:
        await conn.websocket.send_json(message)

    async def broadcast(
        self, session_id: str, message: dict, exclude: str | None = None
    ) -> None:
        room = self._rooms.get(session_id)
        if not room:
            return
        for conn in list(room.values()):
            if conn.connection_id == exclude:
                continue
            try:
                await conn.websocket.send_json(message)
            except Exception:
                # Dead socket: drop it. Its own handler will clean up presence.
                logger.warning("Dropping dead connection %s", conn.connection_id)
                room.pop(conn.connection_id, None)


manager = ConnectionManager()