from __future__ import annotations
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conflict import (
    Conflict,
    ConflictKind,
    ConflictResolution,
    ConflictStatus,
)
from app.models.constraint import Constraint, ConstraintAction, ConstraintStatus
from app.models.intervention import Priority
from app.models.session import SessionMember
from app.models.user import User, UserRole
from app.schemas.conflict import ConflictRead, ConflictSide
from app.services.constraint_manager import ConstraintManager, target_keys
from app.services.readers import describe_constraint

ROLE_RANK = {UserRole.OWNER: 2, UserRole.EDITOR: 1, UserRole.VIEWER: 0}
PRIORITY_RANK = {Priority.HIGH: 2, Priority.MEDIUM: 1, Priority.LOW: 0}

_CONTRADICTORY = {
    frozenset({ConstraintAction.INCLUDE_SOURCE, ConstraintAction.EXCLUDE_SOURCE}),
    frozenset({ConstraintAction.PREFER_SOURCE, ConstraintAction.EXCLUDE_SOURCE}),
}


def conflicting(a: Constraint, b: Constraint) -> bool:
    """Same source, opposite intent. (Free-text INSTRUCTIONs cannot be compared
    deterministically, so they are never reported as conflicting.)"""
    if frozenset({a.action, b.action}) not in _CONTRADICTORY:
        return False
    return bool(target_keys(a.target) & target_keys(b.target))


def decide(
    a: Constraint, role_a: UserRole, b: Constraint, role_b: UserRole
) -> tuple[Constraint | None, str]:
    """The predefined priority rules. Returns (winner or None, explanation).

    1. Higher priority wins.  2. The owner outranks an editor.  3. Otherwise no
    winner: a human must decide explicitly."""
    if a.priority != b.priority:
        win, lose = (a, b) if PRIORITY_RANK[a.priority] > PRIORITY_RANK[b.priority] else (b, a)
        return win, f"Higher priority wins ({win.priority.value} over {lose.priority.value})."
    if role_a != role_b:
        win, lose = (a, b) if ROLE_RANK[role_a] > ROLE_RANK[role_b] else (b, a)
        win_role = role_a if win is a else role_b
        lose_role = role_b if win is a else role_a
        return win, f"The {win_role.value.lower()}'s instruction outranks the {lose_role.value.lower()}'s."
    return None, "Same priority and same role: the rules cannot decide. Explicit resolution by the owner is required."


def _role_of(db: Session, session_id: uuid.UUID, user_id: uuid.UUID | None) -> UserRole:
    if user_id is None:
        return UserRole.EDITOR
    member = db.scalar(
        select(SessionMember).where(
            SessionMember.session_id == session_id, SessionMember.user_id == user_id
        )
    )
    return member.role if member else UserRole.EDITOR


class ConflictManager:
    # ---------------------------------------------------------------- detection
    @staticmethod
    def open_conflicts(db: Session, session_id: uuid.UUID) -> list[Conflict]:
        return list(
            db.scalars(
                select(Conflict)
                .where(Conflict.session_id == session_id, Conflict.status == ConflictStatus.OPEN)
                .order_by(Conflict.created_at)
            ).all()
        )

    @staticmethod
    def list(db: Session, session_id: uuid.UUID, status: ConflictStatus | None = None) -> list[Conflict]:
        stmt = select(Conflict).where(Conflict.session_id == session_id)
        if status is not None:
            stmt = stmt.where(Conflict.status == status)
        return list(db.scalars(stmt.order_by(Conflict.created_at.desc())).all())

    @staticmethod
    def detect(db: Session, session_id: uuid.UUID, new: Constraint) -> list[Conflict]:
        """Compare a newly added constraint with the active ones. The caller commits."""
        existing_pairs = {
            frozenset({c.constraint_a_id, c.constraint_b_id})
            for c in ConflictManager.open_conflicts(db, session_id)
        }
        found: list[Conflict] = []
        for other in ConstraintManager.active(db, session_id):
            if other.id == new.id or not conflicting(other, new):
                continue
            if frozenset({other.id, new.id}) in existing_pairs:
                continue
            winner, rule = decide(
                other, _role_of(db, session_id, other.created_by),
                new, _role_of(db, session_id, new.created_by),
            )
            conflict = Conflict(
                session_id=session_id,
                kind=ConflictKind.SOURCE_POLICY,
                status=ConflictStatus.OPEN,
                constraint_a_id=other.id,
                constraint_b_id=new.id,
                suggested_winner_id=winner.id if winner else None,
                requires_resolution=winner is None,
                rule_applied=rule,
            )
            db.add(conflict)
            db.flush()
            db.refresh(conflict)
            found.append(conflict)
        return found

    @staticmethod
    def count_blocking(db: Session, session_id: uuid.UUID) -> int:
        return db.scalar(
            select(func.count())
            .select_from(Conflict)
            .where(
                Conflict.session_id == session_id,
                Conflict.status == ConflictStatus.OPEN,
                Conflict.requires_resolution.is_(True),
            )
        ) or 0

    # ---------------------------------------------------------------- enforcement
    @staticmethod
    def effective_constraints(db: Session, session_id: uuid.UUID) -> list[Constraint]:
        """The constraints the agent must actually follow right now: all active ones
        minus the 'losing' side of every open conflict (by the priority rules, or by
        the restrictive default for ties). Never decided by the LLM."""
        active = ConstraintManager.active(db, session_id)
        by_id = {c.id: c for c in active}
        losers: set[uuid.UUID] = set()
        for conflict in ConflictManager.open_conflicts(db, session_id):
            a, b = by_id.get(conflict.constraint_a_id), by_id.get(conflict.constraint_b_id)
            if a is None or b is None:
                continue
            if conflict.suggested_winner_id is not None:
                losers.add(b.id if conflict.suggested_winner_id == a.id else a.id)
            else:  # tie: stay on the safe side until a human decides
                losers.add(b.id if a.action == ConstraintAction.EXCLUDE_SOURCE else a.id)
        return [c for c in active if c.id not in losers]

    # ---------------------------------------------------------------- resolution
    @staticmethod
    def resolve(
        db: Session, conflict: Conflict, user: User, winner_id: uuid.UUID | None, note: str | None
    ) -> list[Constraint]:
        """Apply the owner's decision. Returns the constraints that were superseded.
        Raises ValueError if winner_id is not one of the two constraints. Caller commits."""
        a = db.get(Constraint, conflict.constraint_a_id)
        b = db.get(Constraint, conflict.constraint_b_id)
        if winner_id is not None and winner_id not in {a.id, b.id}:
            raise ValueError("winner must be one of the two constraints")

        superseded: list[Constraint] = []
        for c in (a, b):
            if c.id != winner_id and c.status == ConstraintStatus.ACTIVE:
                c.status = ConstraintStatus.SUPERSEDED
                superseded.append(c)

        conflict.status = ConflictStatus.RESOLVED
        conflict.resolution = (
            ConflictResolution.KEEP_A if winner_id == a.id
            else ConflictResolution.KEEP_B if winner_id == b.id
            else ConflictResolution.REMOVE_BOTH
        )
        conflict.resolved_by = user.id
        conflict.resolved_at = datetime.now(timezone.utc)
        conflict.resolution_note = note
        db.flush()
        for c in superseded:  # other open conflicts that involved a superseded constraint
            ConflictManager.close_for_constraint(db, c)
        return superseded

    @staticmethod
    def close_for_constraint(db: Session, constraint: Constraint) -> list[Conflict]:
        """Close open conflicts that involve a constraint that is no longer active."""
        closed = []
        for conflict in ConflictManager.open_conflicts(db, constraint.session_id):
            if constraint.id in (conflict.constraint_a_id, conflict.constraint_b_id):
                conflict.status = ConflictStatus.RESOLVED
                conflict.resolution = ConflictResolution.AUTO_CLOSED
                conflict.resolved_at = datetime.now(timezone.utc)
                conflict.resolution_note = "A constraint involved in this conflict is no longer active."
                closed.append(conflict)
        db.flush()
        return closed

    # ---------------------------------------------------------------- reading
    @staticmethod
    def _side(db: Session, session_id: uuid.UUID, c: Constraint) -> ConflictSide:
        creator = db.get(User, c.created_by) if c.created_by else None
        return ConflictSide(
            constraint_id=c.id,
            action=c.action,
            target=c.target,
            description=describe_constraint(c.action.value, c.target),
            priority=c.priority,
            created_by_username=creator.username if creator else None,
            created_by_role=_role_of(db, session_id, c.created_by).value if c.created_by else None,
            still_active=c.status == ConstraintStatus.ACTIVE,
        )

    @staticmethod
    def to_read(db: Session, conflict: Conflict) -> ConflictRead:
        a = db.get(Constraint, conflict.constraint_a_id)
        b = db.get(Constraint, conflict.constraint_b_id)
        provisional = None
        if conflict.status == ConflictStatus.OPEN:
            if conflict.suggested_winner_id is not None:
                win = a if conflict.suggested_winner_id == a.id else b
                provisional = (
                    f"Enforced for now: {describe_constraint(win.action.value, win.target)} "
                    "(by the priority rules). The owner can still override this."
                )
            else:
                safe = a if a.action == ConstraintAction.EXCLUDE_SOURCE else b
                provisional = (
                    f"Enforced for now: the restrictive option ({describe_constraint(safe.action.value, safe.target)}) "
                    "The agent waits for the owner to decide."
                )
        resolver = db.get(User, conflict.resolved_by) if conflict.resolved_by else None
        return ConflictRead(
            id=conflict.id,
            session_id=conflict.session_id,
            kind=conflict.kind,
            status=conflict.status,
            constraint_a=ConflictManager._side(db, conflict.session_id, a),
            constraint_b=ConflictManager._side(db, conflict.session_id, b),
            requires_resolution=conflict.requires_resolution,
            rule_applied=conflict.rule_applied,
            provisional=provisional,
            suggested_winner_id=conflict.suggested_winner_id,
            resolution=conflict.resolution,
            resolution_note=conflict.resolution_note,
            resolved_by_username=resolver.username if resolver else None,
            created_at=conflict.created_at,
            resolved_at=conflict.resolved_at,
        )