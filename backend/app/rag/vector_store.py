import logging
import os
import threading
import uuid
from pathlib import Path

import faiss
import numpy as np

from app.core.config import get_settings

logger = logging.getLogger("copilothub.rag")


class SessionVectorStore:
    """One FAISS index per session. IndexFlatIP over normalised vectors = exact cosine
    search; IndexIDMap2 lets us store our own chunk ids and remove documents later."""

    def __init__(self, path: Path, dim: int) -> None:
        self.path = path
        self.dim = dim
        self._lock = threading.RLock()
        self._index = self._load_or_create()

    def _new_index(self):
        return faiss.IndexIDMap2(faiss.IndexFlatIP(self.dim))

    def _load_or_create(self):
        if self.path.exists():
            try:
                index = faiss.read_index(str(self.path))
                if index.d == self.dim:
                    return index
                logger.warning("Index %s has dimension %s, expected %s; starting empty", self.path, index.d, self.dim)
            except Exception:
                logger.exception("Could not read FAISS index %s; starting empty", self.path)
        return self._new_index()

    @property
    def count(self) -> int:
        return int(self._index.ntotal)

    def add(self, ids: list[int], vectors: np.ndarray) -> None:
        with self._lock:
            self._index.add_with_ids(
                np.ascontiguousarray(vectors, dtype=np.float32), np.asarray(ids, dtype=np.int64)
            )
            self._save()

    def remove(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._index.remove_ids(np.asarray(ids, dtype=np.int64))
            self._save()

    def reset(self) -> None:
        with self._lock:
            self._index = self._new_index()
            self._save()

    def search(self, vector: np.ndarray, k: int) -> list[tuple[int, float]]:
        with self._lock:
            if self._index.ntotal == 0:
                return []
            scores, ids = self._index.search(
                np.ascontiguousarray(vector.reshape(1, -1), dtype=np.float32), min(k, self._index.ntotal)
            )
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        faiss.write_index(self._index, str(tmp))
        os.replace(tmp, self.path)


class VectorStoreManager:
    def __init__(self) -> None:
        self._stores: dict[str, SessionVectorStore] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _path(session_id: uuid.UUID) -> Path:
        return get_settings().data_path / "embeddings" / f"{session_id}.faiss"

    def get(self, session_id: uuid.UUID, dim: int) -> SessionVectorStore:
        key = str(session_id)
        with self._lock:
            store = self._stores.get(key)
            if store is None or store.dim != dim:
                store = SessionVectorStore(self._path(session_id), dim)
                self._stores[key] = store
            return store

    def get_existing(self, session_id: uuid.UUID) -> SessionVectorStore | None:
        """The session's store if one exists (cached or on disk), without needing the
        embedding model (used for deleting documents)."""
        key = str(session_id)
        with self._lock:
            store = self._stores.get(key)
            if store is not None:
                return store
            path = self._path(session_id)
            if not path.exists():
                return None
            try:
                dim = int(faiss.read_index(str(path)).d)
            except Exception:
                return None
            store = SessionVectorStore(path, dim)
            self._stores[key] = store
            return store
    def drop(self, session_id: uuid.UUID) -> None:
        """Forget a session's index (and delete its file)."""
        with self._lock:
            self._stores.pop(str(session_id), None)
        try:
            self._path(session_id).unlink(missing_ok=True)
        except OSError:
            pass


vector_stores = VectorStoreManager()