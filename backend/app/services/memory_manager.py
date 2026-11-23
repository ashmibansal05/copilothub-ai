
import logging
import re
import uuid

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.memory import MemoryItem, MemoryKind


logger = logging.getLogger("copilothub.memory")

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "will", "not",
    "you", "your", "use", "using", "have", "has", "but", "all", "can", "should",
}


def _tokens(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z0-9]{3,}", text.lower())
        if w not in _STOPWORDS
    }


class MemoryManager:
    """Structured long-term memory.

    Short-term memory (current task, recent actions, tool results)
    lives in the orchestrator state.

    This class stores what humans taught the agent and retrieves
    relevant memory items for prompts.
    """

    @staticmethod
    def remember(
        db: Session,
        session_id: uuid.UUID,
        kind: MemoryKind,
        content: str,
        *,
        key: str | None = None,
        author: str | None = None,
        user_id: uuid.UUID | None = None,
        intervention_id: uuid.UUID | None = None,
        importance: int = 3,
    ) -> MemoryItem:
        item = MemoryItem(
            session_id=session_id,
            kind=kind,
            key=key,
            content=content,
            importance=max(1, min(5, importance)),
            author=author,
            created_by=user_id,
            intervention_id=intervention_id,
        )

        db.add(item)
        db.flush()

        return item

    @staticmethod
    def deactivate_source(
        db: Session,
        session_id: uuid.UUID,
        key: str,
    ) -> int:
        rows = db.scalars(
            select(MemoryItem).where(
                MemoryItem.session_id == session_id,
                MemoryItem.is_active.is_(True),
                MemoryItem.kind.in_([
                    MemoryKind.REJECTED_SOURCE,
                    MemoryKind.APPROVED_SOURCE,
                ]),
            )
        ).all()

        count = 0

        for row in rows:
            if row.key and row.key.strip().lower() == key.strip().lower():
                row.is_active = False
                count += 1

        db.flush()

        return count

    @staticmethod
    def list_active(
        db: Session,
        session_id: uuid.UUID,
    ) -> list[MemoryItem]:
        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.session_id == session_id,
                MemoryItem.is_active.is_(True),
            )
            .order_by(MemoryItem.created_at.desc())
        )

        return list(db.scalars(stmt).all())

    @staticmethod
    def retrieve(
        db: Session,
        session_id: uuid.UUID,
        query: str,
        k: int = 5,
        char_budget: int = 1200,
        embedder=None,
    ) -> list[str]:
        """Retrieve relevant memory items for an agent prompt.

        Score combines:
        - Semantic similarity (if an embedder is available)
        - Importance
        - Recency

        If embedding generation fails or no embedder is given,
        keyword overlap is used as the fallback.
        """

        items = list(
            db.scalars(
                select(MemoryItem)
                .where(
                    MemoryItem.session_id == session_id,
                    MemoryItem.is_active.is_(True),
                    MemoryItem.kind.in_([
                        MemoryKind.FACT,
                        MemoryKind.CORRECTION,
                        MemoryKind.DECISION,
                    ]),
                )
                .order_by(MemoryItem.created_at)
            ).all()
        )

        if not items:
            return []

        # Phase 10: Semantic retrieval using embeddings
        semantic: list[float] | None = None

        if embedder is not None:
            try:
                vectors = embedder.embed(
                    [query] + [item.content for item in items]
                )

                # Cosine similarity for normalized vectors
                semantic = (
                    vectors[1:] @ vectors[0]
                ).tolist()

            except Exception:
                logger.warning(
                    "Embedding-based memory retrieval failed; "
                    "using keyword overlap",
                    exc_info=True,
                )

        # Keyword retrieval fallback
        q = _tokens(query)

        scored = []

        for index, item in enumerate(items):
            if semantic is not None:
                relevance = max(0.0, semantic[index])
            else:
                tokens = _tokens(item.content)
                relevance = (
                    len(q & tokens) / len(tokens)
                    if tokens else 0.0
                )

            recency = 0.1 * (index + 1) / len(items)

            score = (
                relevance
                + item.importance * 0.1
                + recency
            )

            scored.append((score, item))

        # Higher-scoring memories are selected first
        scored.sort(
            key=lambda pair: pair[0],
            reverse=True,
        )

        lines: list[str] = []
        used = 0

        for _, item in scored[:k]:
            who = f" by {item.author}" if item.author else ""

            line = (
                f"[{item.kind.value.lower()}{who}] "
                f"{item.content}"
            )

            if used + len(line) > char_budget:
                break

            lines.append(line)
            used += len(line)

        return lines
