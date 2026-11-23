import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.session import AgentSession
from app.rag.vector_store import vector_stores

logger = logging.getLogger("copilothub.cleanup")


def _as_uuid(name: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(name)
    except ValueError:
        return None


def find_orphans(db: Session) -> list[Path]:
    """Upload folders and FAISS files whose session no longer exists. Only names that are
    UUIDs are considered, so unrelated files in the data folder are never touched."""
    base = get_settings().data_path
    known = set(db.scalars(select(AgentSession.id)).all())
    orphans: list[Path] = []
    documents = base / "documents"
    if documents.is_dir():
        for child in documents.iterdir():
            sid = _as_uuid(child.name)
            if child.is_dir() and sid is not None and sid not in known:
                orphans.append(child)
    embeddings = base / "embeddings"
    if embeddings.is_dir():
        for file in embeddings.iterdir():
            sid = _as_uuid(file.stem)
            if file.is_file() and file.suffix in (".faiss", ".tmp") and sid is not None and sid not in known:
                orphans.append(file)
    return orphans


def purge(paths: list[Path]) -> int:
    removed = 0
    for path in paths:
        try:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
            removed += 1
        except OSError:
            logger.warning("Could not remove %s", path)
    return removed


def purge_session_files(session_id: uuid.UUID) -> None:
    """Delete everything stored on disk for one session."""
    folder = get_settings().data_path / "documents" / str(session_id)
    shutil.rmtree(folder, ignore_errors=True)
    vector_stores.drop(session_id)