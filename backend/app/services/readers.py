"""Turn ORM rows into API schemas (shared by services, routes and WebSocket events)."""

from app.models.approval import Approval
from app.models.constraint import Constraint
from app.models.intervention import Intervention
from app.schemas.intervention import ApprovalRead, ConstraintRead, InterventionRead


def describe_constraint(action: str, target: str) -> str:
    if action == "EXCLUDE_SOURCE":
        return f'Do not use sources from or about "{target}".'
    if action == "INCLUDE_SOURCE":
        return f'Sources from "{target}" are explicitly allowed.'
    if action == "PREFER_SOURCE":
        return f'Prefer sources from "{target}".'
    return target  # INSTRUCTION: the text itself


def intervention_read(row: Intervention) -> InterventionRead:
    return InterventionRead(
        id=row.id,
        session_id=row.session_id,
        user_id=row.user_id,
        username=row.user.username if row.user else None,
        type=row.type,
        content=row.content,
        target=row.target,
        priority=row.priority,
        status=row.status,
        details=row.details or {},
        result=row.result,
        created_at=row.created_at,
    )


def constraint_read(c: Constraint) -> ConstraintRead:
    return ConstraintRead(
        id=c.id,
        session_id=c.session_id,
        action=c.action,
        target=c.target,
        description=describe_constraint(c.action.value, c.target),
        priority=c.priority,
        status=c.status,
        created_by=c.created_by,
        created_by_username=c.creator.username if c.creator else None,
        created_at=c.created_at,
    )


def approval_read(a: Approval) -> ApprovalRead:
    return ApprovalRead(
        id=a.id, kind=a.kind, status=a.status, payload=a.payload or {}, created_at=a.created_at
    )