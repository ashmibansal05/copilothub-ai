import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.constraint import Constraint, ConstraintAction, ConstraintStatus
from app.models.intervention import Priority
from app.models.user import User
from app.services.readers import describe_constraint

PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


@dataclass(frozen=True)
class ConstraintView:
    """Plain, session-independent copy of a constraint (safe to pass around)."""

    id: str
    action: str
    target: str
    priority: str
    description: str


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _target_keys(target: str) -> set[str]:
    """'Wikipedia', 'wikipedia.org' and 'https://en.wikipedia.org/x' all key on 'wikipedia'."""
    t = target.strip().lower()
    host = (urlparse(t).hostname or t) if "://" in t else t
    keys = {_norm(host)}
    if "." in host and " " not in host:
        parts = [p for p in host.split(".") if p]
        if len(parts) >= 2:
            keys.add(_norm(parts[-2]))
    return {k for k in keys if len(k) >= 2}

target_keys = _target_keys
class ConstraintManager:
    # ---------------------------------------------------------------- database
    @staticmethod
    def active(db: Session, session_id: uuid.UUID) -> list[Constraint]:
        stmt = (
            select(Constraint)
            .options(joinedload(Constraint.creator))
            .where(Constraint.session_id == session_id, Constraint.status == ConstraintStatus.ACTIVE)
            .order_by(Constraint.created_at)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get(db: Session, constraint_id: uuid.UUID) -> Constraint | None:
        return db.get(Constraint, constraint_id)

    @staticmethod
    def add(
        db: Session,
        session_id: uuid.UUID,
        user: User,
        action: ConstraintAction,
        target: str,
        priority: Priority,
        intervention_id: uuid.UUID | None = None,
    ) -> tuple[Constraint, bool]:
        """Returns (constraint, created). Adding an identical active constraint is a
        no-op that returns the existing one. The caller commits."""
        target = target.strip()
        key = _norm(target)
        for existing in ConstraintManager.active(db, session_id):
            if existing.action == action and _norm(existing.target) == key:
                return existing, False
        row = Constraint(
            session_id=session_id,
            intervention_id=intervention_id,
            action=action,
            target=target,
            priority=priority,
            status=ConstraintStatus.ACTIVE,
            created_by=user.id,
        )
        db.add(row)
        db.flush()
        db.refresh(row)
        return row, True

    @staticmethod
    def remove(db: Session, session_id: uuid.UUID, constraint_id: uuid.UUID, user: User) -> Constraint:
        row = db.get(Constraint, constraint_id)
        if row is None or row.session_id != session_id or row.status != ConstraintStatus.ACTIVE:
            raise LookupError("constraint not found")
        row.status = ConstraintStatus.REMOVED
        row.removed_by = user.id
        row.removed_at = datetime.now(timezone.utc)
        db.flush()
        return row

    # ---------------------------------------------------------------- pure helpers
    @staticmethod
    def to_views(rows: list[Constraint]) -> list[ConstraintView]:
        return [
            ConstraintView(
                id=str(c.id),
                action=c.action.value,
                target=c.target,
                priority=c.priority.value,
                description=describe_constraint(c.action.value, c.target),
            )
            for c in rows
        ]

    @staticmethod
    def matches(target: str, source: dict) -> bool:
        haystack = _norm(
            " ".join(str(source.get(k, "")) for k in ("title", "publisher", "source_type", "domain", "url"))
        )
        return any(re.search(rf"\b{re.escape(key)}\b", haystack) for key in _target_keys(target))

    @staticmethod
    def filter_sources(
        views: list[ConstraintView], sources: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Apply the rules to a tool's sources. Returns (allowed_and_ranked, rejected).

        EXCLUDE_SOURCE wins over INCLUDE_SOURCE until Phase 9 conflict resolution
        decides explicitly. PREFER_SOURCE only changes the ranking."""
        excludes = [v for v in views if v.action == ConstraintAction.EXCLUDE_SOURCE.value]
        prefers = [v for v in views if v.action == ConstraintAction.PREFER_SOURCE.value]
        allowed: list[dict] = []
        rejected: list[dict] = []
        for source in sources:
            hit = next((v for v in excludes if ConstraintManager.matches(v.target, source)), None)
            if hit is not None:
                rejected.append({**source, "rejected_by": hit.target})
                continue
            preferred = any(ConstraintManager.matches(v.target, source) for v in prefers)
            allowed.append({**source, "preferred": True} if preferred else dict(source))
        allowed.sort(key=lambda s: not s.get("preferred", False))  # stable: preferred first
        return allowed, rejected

    @staticmethod
    def prompt_lines(views: list[ConstraintView], limit: int = 20) -> list[str]:
        """All active constraints are always shown to the model (there are few and they
        are mandatory), highest priority first."""
        ordered = sorted(views, key=lambda v: PRIORITY_ORDER.get(v.priority, 1))
        return [f"[{v.priority}] {v.description}" for v in ordered[:limit]]