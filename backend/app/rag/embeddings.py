import threading
from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np

from app.core.config import get_settings


class Embedder(ABC):
    """Turns texts into L2-normalised float32 vectors (so inner product == cosine)."""

    name: str

    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Shape (len(texts), dim)."""


class SentenceTransformerEmbedder(Embedder):
    """Semantic embeddings from a Sentence-Transformers model (the default).
    The model is loaded lazily, in whichever thread first needs it."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.name = f"sentence-transformers:{model_name}"
        self._model = None
        self._dim = 0
        self._lock = threading.Lock()

    def _load(self) -> None:
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer  # heavy import, kept lazy

                self._model = SentenceTransformer(self.model_name)
                self._dim = int(self._model.get_sentence_embedding_dimension())

    @property
    def dim(self) -> int:
        self._load()
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        self._load()
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        vectors = self._model.encode(
            texts, batch_size=32, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


class HashingEmbedder(Embedder):
    """Lexical fallback: hashed bag-of-words vectors (scikit-learn). Needs no download
    and works offline, but only matches shared words, not meaning. Selected
    explicitly with EMBEDDING_BACKEND=hashing; never used silently."""

    name = "hashing-lexical"

    def __init__(self, dim: int = 512) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer

        self._dim = dim
        self._vectorizer = HashingVectorizer(
            n_features=dim, alternate_sign=False, norm="l2", stop_words="english"
        )

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        return self._vectorizer.transform(texts).toarray().astype(np.float32)


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedding_backend == "hashing":
        return HashingEmbedder()
    return SentenceTransformerEmbedder(settings.embedding_model)