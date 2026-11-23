import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import session as db_session
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.rag.chunking import chunk_pages
from app.rag.embeddings import Embedder, get_embedder
from app.rag.extract import ExtractionError, extract_pages
from app.rag.injection import looks_like_injection
from app.rag.vector_store import vector_stores
from app.services.constraint_manager import ConstraintManager, ConstraintView

logger = logging.getLogger("copilothub.rag")

PREFERRED_BOOST = 0.15  # added to the similarity score of chunks from preferred sources
_ingest_lock = threading.Lock()  # serialises writes to the index and the vector-id counter


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    source_name: str
    source_type: str
    page: int | None
    text: str
    score: float
    preferred: bool

    def as_prompt(self) -> dict:
        return {"title": self.title, "source_name": self.source_name, "page": self.page, "text": self.text}


def doc_source(doc: Document) -> dict:
    """The document described the way constraints see a source."""
    return {"title": doc.title, "publisher": doc.source_name, "source_type": doc.source_type}


# ----------------------------------------------------------------------- ingestion
def _mark_failed(document_id: uuid.UUID, message: str) -> None:
    with db_session.SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = DocumentStatus.FAILED
            doc.error = message[:500]
            db.commit()


def ingest_document_sync(document_id: uuid.UUID) -> tuple[str, str | None]:
    """Extract -> chunk -> embed -> index. Runs in a worker thread.
    Returns (status, error) where status is READY, FAILED or MISSING (deleted meanwhile)."""
    settings = get_settings()
    with db_session.SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return "MISSING", None
        path, session_id = Path(doc.storage_path), doc.session_id

    try:
        pages = extract_pages(path)
        drafts = chunk_pages(pages, settings.rag_chunk_size, settings.rag_chunk_overlap)
        if not drafts:
            raise ExtractionError("No text could be extracted from this file")
        if len(drafts) > settings.rag_max_chunks_per_document:
            raise ExtractionError(
                f"The document is too large ({len(drafts)} chunks; the limit is {settings.rag_max_chunks_per_document})"
            )
        embedder = get_embedder()
        vectors = embedder.embed([d.text for d in drafts])
        dim = embedder.dim
    except ExtractionError as exc:
        _mark_failed(document_id, str(exc))
        return "FAILED", str(exc)
    except Exception as exc:
        logger.exception("Embedding/extraction failed for document %s", document_id)
        message = (
            f"Processing failed ({exc.__class__.__name__}: {str(exc)[:150]}). If the embedding model "
            "could not be loaded, check your internet connection or set EMBEDDING_BACKEND=hashing."
        )
        _mark_failed(document_id, message)
        return "FAILED", message

    ids: list[int] = []
    store = None
    try:
        with _ingest_lock, db_session.SessionLocal() as db:
            doc = db.get(Document, document_id)
            if doc is None:
                return "MISSING", None
            current_max = db.scalar(
                select(func.max(DocumentChunk.vector_id)).where(DocumentChunk.session_id == session_id)
            ) or 0
            ids = list(range(current_max + 1, current_max + 1 + len(drafts)))
            flagged = 0
            for index, (draft, vector_id) in enumerate(zip(drafts, ids)):
                is_flagged = looks_like_injection(draft.text)
                flagged += int(is_flagged)
                db.add(DocumentChunk(
                    document_id=doc.id, session_id=session_id, chunk_index=index,
                    page=draft.page, text=draft.text, vector_id=vector_id, flagged=is_flagged,
                ))
            db.flush()
            store = vector_stores.get(session_id, dim)
            store.add(ids, vectors)
            doc.status = DocumentStatus.READY
            doc.error = None
            doc.page_count = len(pages) if path.suffix.lower() == ".pdf" else None
            doc.chunk_count = len(drafts)
            doc.flagged_chunks = flagged
            doc.embedding_backend = embedder.name
            db.commit()
        return "READY", None
    except Exception as exc:
        logger.exception("Indexing failed for document %s", document_id)
        if store is not None and ids:
            try:
                store.remove(ids)
            except Exception:
                logger.exception("Could not roll back vectors for document %s", document_id)
        message = f"Indexing failed ({exc.__class__.__name__})"
        _mark_failed(document_id, message)
        return "FAILED", message


def delete_document_sync(document_id: uuid.UUID) -> bool:
    with _ingest_lock, db_session.SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return False
        ids = list(db.scalars(select(DocumentChunk.vector_id).where(DocumentChunk.document_id == doc.id)).all())
        store = vector_stores.get_existing(doc.session_id)
        if store is not None and ids:
            store.remove(ids)
        path = Path(doc.storage_path)
        db.delete(doc)  # chunks are removed through the ORM cascade
        db.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete file %s", path)
    return True


# ----------------------------------------------------------------------- retrieval
def _ensure_index(db: Session, session_id: uuid.UUID, embedder: Embedder):
    """Make sure the FAISS index has a vector for every stored chunk; rebuild it from
    the stored chunk text if the file was lost or the embedding dimension changed."""
    store = vector_stores.get(session_id, embedder.dim)
    chunk_rows = db.scalar(
        select(func.count()).select_from(DocumentChunk).where(DocumentChunk.session_id == session_id)
    ) or 0
    if store.count < chunk_rows:
        logger.warning("Rebuilding FAISS index for session %s", session_id)
        rows = db.execute(
            select(DocumentChunk.vector_id, DocumentChunk.text)
            .where(DocumentChunk.session_id == session_id)
            .order_by(DocumentChunk.vector_id)
        ).all()
        with _ingest_lock:
            store.reset()
            store.add([r[0] for r in rows], embedder.embed([r[1] for r in rows]))
    return store


def retrieve_chunks(
    db: Session,
    session_id: uuid.UUID,
    query: str,
    k: int,
    views: list[ConstraintView],
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """Semantic search over a session's documents.

    Sources excluded by the active constraints are NEVER returned; preferred
    sources get a score boost; flagged (possibly injected) chunks are skipped."""
    settings = get_settings()
    min_score = settings.rag_min_score if min_score is None else min_score
    documents = {
        d.id: d
        for d in db.scalars(
            select(Document).where(Document.session_id == session_id, Document.status == DocumentStatus.READY)
        ).all()
    }
    if not documents:
        return []

    usable: set[uuid.UUID] = set()
    preferred: set[uuid.UUID] = set()
    for doc_id, doc in documents.items():
        allowed, rejected = ConstraintManager.filter_sources(views, [doc_source(doc)])
        if rejected:
            continue
        usable.add(doc_id)
        if allowed and allowed[0].get("preferred"):
            preferred.add(doc_id)
    if not usable:
        return []

    embedder = get_embedder()
    store = _ensure_index(db, session_id, embedder)
    hits = store.search(embedder.embed([query])[0], k * 5 + 10)
    if not hits:
        return []
    scores = dict(hits)
    rows = db.scalars(
        select(DocumentChunk).where(
            DocumentChunk.session_id == session_id,
            DocumentChunk.vector_id.in_(list(scores)),
            DocumentChunk.flagged.is_(False),
        )
    ).all()

    results: list[RetrievedChunk] = []
    for chunk in rows:
        raw = scores[chunk.vector_id]
        if chunk.document_id not in usable or raw < min_score:
            continue
        doc = documents[chunk.document_id]
        is_preferred = chunk.document_id in preferred
        results.append(RetrievedChunk(
            chunk_id=chunk.id, document_id=doc.id, title=doc.title, source_name=doc.source_name,
            source_type=doc.source_type, page=chunk.page, text=chunk.text,
            score=raw + (PREFERRED_BOOST if is_preferred else 0.0), preferred=is_preferred,
        ))
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:k]
def document_sources(chunks: list[RetrievedChunk]) -> list[dict]:
    """One source entry per document, with its best score, in the shape constraints understand."""
    by_doc: dict[uuid.UUID, dict] = {}
    for c in chunks:
        entry = by_doc.get(c.document_id)
        if entry is None or c.score > entry["score"]:
            by_doc[c.document_id] = {
                "title": c.title, "publisher": c.source_name, "source_type": c.source_type,
                "document_id": str(c.document_id), "origin": "document", "simulated": False,
                "score": round(c.score, 3), "page": c.page, "excerpt": c.text[:160],
            }
    return list(by_doc.values())