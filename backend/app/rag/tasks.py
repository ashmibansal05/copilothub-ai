import asyncio
import logging
import uuid

from app.db import session as db_session
from app.models.document import Document
from app.rag.service import ingest_document_sync
from app.services import event_service
from app.services.readers import document_read
from app.websocket.events import EventType

logger = logging.getLogger("copilothub.rag")
_tasks: set[asyncio.Task] = set()  # keep references so tasks are not garbage collected


async def _run(document_id: uuid.UUID, session_id: uuid.UUID) -> None:
    status, _ = await asyncio.to_thread(ingest_document_sync, document_id)
    if status == "MISSING":
        return
    with db_session.SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        event_type = EventType.DOCUMENT_READY if status == "READY" else EventType.DOCUMENT_FAILED
        await event_service.publish(
            db, session_id, event_type, {"document": document_read(doc).model_dump(mode="json")}
        )


def start_ingest(document_id: uuid.UUID, session_id: uuid.UUID) -> None:
    task = asyncio.create_task(_run(document_id, session_id), name=f"ingest-{document_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)