import asyncio
import hashlib
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import SessionContext, get_session_context, require_session_role
from app.core.config import get_settings
from app.db import session as db_session
from app.db.session import get_db
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.session import AgentStatus
from app.models.source import Source
from app.models.user import UserRole
from app.rag import service as rag_service
from app.rag.tasks import start_ingest
from app.rag.validation import UploadRejected, safe_display_name, validate_upload
from app.schemas.document import ChunkRead, DocumentRead, SearchHit, SearchRequest, SourceRead
from app.services import event_service
from app.services.conflict_manager import ConflictManager
from app.services.constraint_manager import ConstraintManager
from app.services.readers import document_read
from app.websocket.events import EventType

logger = logging.getLogger("copilothub.documents")
router = APIRouter(prefix="/sessions", tags=["documents"])

CanManage = Depends(require_session_role(UserRole.OWNER, UserRole.EDITOR))
ENDED = {AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED}


def _get_document(db: Session, ctx: SessionContext, document_id: uuid.UUID) -> Document:
    doc = db.scalar(
        select(Document)
        .options(joinedload(Document.uploader))
        .where(Document.id == document_id, Document.session_id == ctx.session.id)
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.post("/{session_id}/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    source_name: str | None = Form(None),
    source_type: str | None = Form(None),
    ctx: SessionContext = CanManage,
    db: Session = Depends(get_db),
) -> DocumentRead:
    settings = get_settings()
    session = ctx.session
    if session.status in ENDED:
        raise HTTPException(status.HTTP_409_CONFLICT, "The session has ended")
    existing = db.scalar(select(func.count()).select_from(Document).where(Document.session_id == session.id)) or 0
    if existing >= settings.max_documents_per_session:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A session can hold at most {settings.max_documents_per_session} documents")

    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"The file is larger than {settings.max_upload_mb} MB")
    try:
        ext = validate_upload(file.filename, data)
    except UploadRejected as exc:
        raise HTTPException(exc.status_code, exc.message)

    sha = hashlib.sha256(data).hexdigest()
    if db.scalar(select(Document.id).where(Document.session_id == session.id, Document.sha256 == sha)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This file was already uploaded to the session")

    display = safe_display_name(file.filename)
    document_id = uuid.uuid4()
    folder = settings.data_path / "documents" / str(session.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{document_id}{ext}"  # server-generated name: the client name is never a path
    path.write_bytes(data)

    doc = Document(
        id=document_id,
        session_id=session.id,
        uploaded_by=ctx.user.id,
        title=((title or "").strip() or display.rsplit(".", 1)[0])[:200],
        filename=display,
        source_name=((source_name or "").strip() or "Uploaded document")[:120],
        source_type=((source_type or "").strip() or "uploaded document")[:60],
        mime=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        sha256=sha,
        status=DocumentStatus.PROCESSING,
        storage_path=str(path),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    read = document_read(doc)
    logger.info("document %s uploaded by %s to session %s", display, ctx.user.username, session.id)
    await event_service.publish(db, session.id, EventType.DOCUMENT_ADDED, {"document": read.model_dump(mode="json")}, ctx.user)
    start_ingest(doc.id, session.id)
    return read


@router.get("/{session_id}/documents", response_model=list[DocumentRead])
async def list_documents(
    ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)
) -> list[DocumentRead]:
    docs = db.scalars(
        select(Document)
        .options(joinedload(Document.uploader))
        .where(Document.session_id == ctx.session.id)
        .order_by(Document.created_at)
    ).all()
    return [document_read(d) for d in docs]


@router.get("/{session_id}/documents/{document_id}/chunks", response_model=list[ChunkRead])
async def list_chunks(
    document_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> list[DocumentChunk]:
    doc = _get_document(db, ctx, document_id)
    return list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
            .offset(offset)
            .limit(limit)
        ).all()
    )


@router.delete("/{session_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, ctx: SessionContext = CanManage, db: Session = Depends(get_db)
) -> None:
    doc = _get_document(db, ctx, document_id)
    title = doc.title
    if not await asyncio.to_thread(rag_service.delete_document_sync, doc.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    await event_service.publish(
        db, ctx.session.id, EventType.DOCUMENT_REMOVED,
        {"document_id": str(document_id), "title": title}, ctx.user,
    )


def _search_sync(session_id: uuid.UUID, query: str, k: int) -> list[rag_service.RetrievedChunk]:
    with db_session.SessionLocal() as db:
        views = ConstraintManager.to_views(ConflictManager.effective_constraints(db, session_id))
        return rag_service.retrieve_chunks(db, session_id, query, k, views)


@router.post("/{session_id}/documents/search", response_model=list[SearchHit])
async def search_documents(
    data: SearchRequest, ctx: SessionContext = Depends(get_session_context)
) -> list[SearchHit]:
    """Semantic search. Respects the session's constraints, exactly as the agent does."""
    try:
        chunks = await asyncio.to_thread(_search_sync, ctx.session.id, data.query, data.k)
    except Exception as exc:
        logger.exception("Document search failed")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Search is unavailable ({exc.__class__.__name__})")
    return [
        SearchHit(
            chunk_id=c.chunk_id, document_id=c.document_id, title=c.title, source_name=c.source_name,
            source_type=c.source_type, page=c.page, text=c.text, score=round(c.score, 4), preferred=c.preferred,
        )
        for c in chunks
    ]


@router.get("/{session_id}/sources", response_model=list[SourceRead])
async def list_sources(
    status_filter: str = Query("all", alias="status", pattern="^(all|USED|REJECTED)$"),
    limit: int = Query(200, ge=1, le=500),
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> list[Source]:
    stmt = select(Source).where(Source.session_id == ctx.session.id)
    if status_filter != "all":
        stmt = stmt.where(Source.status == status_filter)
    return list(reversed(db.scalars(stmt.order_by(Source.created_at.desc()).limit(limit)).all()))