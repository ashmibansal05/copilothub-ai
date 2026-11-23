import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.agents.runner import agent_runner
from app.agents.state import ApprovalDecision
from app.api.deps import SessionContext
from app.models.approval import ApprovalKind, ApprovalStatus
from app.models.conflict import Conflict, ConflictStatus
from app.models.constraint import Constraint, ConstraintAction
from app.models.intervention import (
    Intervention,
    InterventionStatus,
    InterventionType as T,
    Priority,
)
from app.models.memory import MemoryKind
from app.models.session import AgentStatus
from app.models.user import UserRole
from app.nlp.feedback import record_outcome
from app.schemas.intervention import InterventionCreate, InterventionRead
from app.services import approval_service, event_service
from app.services.conflict_manager import ConflictManager
from app.services.constraint_manager import ConstraintManager
from app.services.memory_manager import MemoryManager
from app.services.readers import constraint_read, intervention_read
from app.services.session_control import apply_transition
from app.websocket.events import EventType

logger = logging.getLogger("copilothub.interventions")

TERMINAL = {AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED}

# The single place that decides who may do what (checked on the backend only).
EDITOR_TYPES = {
    T.COMMENT, T.CORRECT, T.ADD_INFORMATION, T.APPROVE, T.REJECT, T.PAUSE, T.RESUME,
    T.REQUEST_REVIEW, T.ADD_CONSTRAINT, T.REMOVE_CONSTRAINT, T.REJECT_SOURCE, T.CHANGE_SOURCE,
}
ROLE_PERMISSIONS: dict[UserRole, set[T]] = {
    UserRole.OWNER: set(T),  # editors' set + MODIFY_TASK + RESOLVE_CONFLICT
    UserRole.EDITOR: EDITOR_TYPES,
    UserRole.VIEWER: set(),
}
DEFAULT_PRIORITY = {T.REJECT_SOURCE: Priority.HIGH, T.CHANGE_SOURCE: Priority.HIGH}


def _need(condition: object, message: str) -> None:
    if not condition:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, message)


def _validate(data: InterventionCreate) -> tuple[str | None, str | None]:
    content = (data.content or "").strip() or None
    target = (data.target or "").strip() or None
    t = data.type
    if t in (T.COMMENT, T.CORRECT, T.ADD_INFORMATION):
        _need(content and len(content) >= 3, "Content is required (at least 3 characters)")
    elif t == T.MODIFY_TASK:
        _need(content and len(content) >= 10, "The new task must be at least 10 characters")
    elif t == T.REJECT_SOURCE:
        _need(target, "A source name (target) is required")
    elif t == T.CHANGE_SOURCE:
        _need(target and content, "Both the source to replace (target) and the new source (content) are required")
    elif t == T.ADD_CONSTRAINT:
        _need(data.action is not None, "A constraint action is required")
        _need(target and len(target) >= 2, "A target is required")
    elif t == T.REMOVE_CONSTRAINT:
        _need(data.constraint_id is not None, "constraint_id is required")
    elif t == T.RESOLVE_CONFLICT:
        _need(data.conflict_id is not None, "conflict_id is required")
    return content, target


def _add_constraint(
    db: Session, ctx: SessionContext, row: Intervention, action: ConstraintAction,
    target: str, priority: Priority, added: list[Constraint], new_conflicts: list[Conflict],
) -> Constraint:
    constraint, created = ConstraintManager.add(
        db, ctx.session.id, ctx.user, action, target, priority, row.id
    )
    if created:
        added.append(constraint)
        new_conflicts.extend(ConflictManager.detect(db, ctx.session.id, constraint))
        common = dict(
            session_id=ctx.session.id, key=target, author=ctx.user.username,
            user_id=ctx.user.id, intervention_id=row.id, importance=4,
        )
        if action == ConstraintAction.EXCLUDE_SOURCE:
            MemoryManager.remember(db, kind=MemoryKind.REJECTED_SOURCE, content=f"Source rejected: {target}", **common)
        elif action == ConstraintAction.INCLUDE_SOURCE:
            MemoryManager.remember(db, kind=MemoryKind.APPROVED_SOURCE, content=f"Source approved: {target}", **common)
    return constraint


async def process_intervention(db: Session, ctx: SessionContext, data: InterventionCreate) -> InterventionRead:
    t = data.type
    session, user = ctx.session, ctx.user
    sid = session.id

    if t not in ROLE_PERMISSIONS[ctx.role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role ({ctx.role.value}) may not perform {t.value}")
    content, target = _validate(data)
    if session.status in TERMINAL and t != T.COMMENT:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The session is {session.status.value.lower()}; only comments are accepted")
    priority = data.priority or DEFAULT_PRIORITY.get(t, Priority.MEDIUM)

    # ---- checks and side effects on the running agent (before anything is stored) ----
    pending = None
    if t in (T.APPROVE, T.REJECT):
        pending = approval_service.get_pending(db, sid)
        if pending is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for approval")
        decision = ApprovalDecision(approved=(t == T.APPROVE), note=content, by=user.username)
        if not agent_runner.resolve_approval(sid, pending.id, decision):
            approval_service.expire_pending(db, sid)
            raise HTTPException(status.HTTP_409_CONFLICT, "The agent is no longer waiting for this approval")
    elif t == T.REQUEST_REVIEW:
        if approval_service.get_pending(db, sid) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "An approval is already pending")
        if not agent_runner.request_review(sid, user.id, user.username, content):
            raise HTTPException(status.HTTP_409_CONFLICT, "The agent is not running")
    elif t in (T.PAUSE, T.RESUME):
        await apply_transition("pause" if t == T.PAUSE else "resume", ctx, db)  # 409 if invalid

    # ---- store the intervention, then apply its effects ----
    row = Intervention(
        session_id=sid, user_id=user.id, type=t, content=content, target=target,
        priority=priority, status=InterventionStatus.APPLIED, details={},
    )
    db.add(row)
    db.flush()

    added: list[Constraint] = []
    removed: list[tuple[Constraint, str]] = []  # (constraint, reason)
    new_conflicts: list[Conflict] = []
    resolved_conflicts: list[Conflict] = []
    approval_event: dict | None = None
    details: dict = {}
    result = ""
    memory = dict(session_id=sid, author=user.username, user_id=user.id, intervention_id=row.id)

    if t == T.COMMENT:
        result = "Comment recorded"
    elif t == T.CORRECT:
        MemoryManager.remember(db, kind=MemoryKind.CORRECTION, content=content, importance=4, **memory)
        result = "Correction saved; the agent will take it into account"
    elif t == T.ADD_INFORMATION:
        MemoryManager.remember(db, kind=MemoryKind.FACT, content=content, importance=3, **memory)
        result = "Information saved; the agent will take it into account"
    elif t == T.MODIFY_TASK:
        details = {"old_task": session.task, "new_task": content}
        session.task = content
        MemoryManager.remember(db, kind=MemoryKind.DECISION, content=f"Task changed to: {content}", importance=1, **memory)
        replanning = agent_runner.request_replan(sid)
        result = "Task updated" + ("; the agent will re-plan at its next checkpoint" if replanning else "")
    elif t == T.REJECT_SOURCE:
        c = _add_constraint(db, ctx, row, ConstraintAction.EXCLUDE_SOURCE, target, priority, added, new_conflicts)
        details = {"constraint_id": str(c.id)}
        result = f"Source '{target}' is now excluded"
    elif t == T.CHANGE_SOURCE:
        old = _add_constraint(db, ctx, row, ConstraintAction.EXCLUDE_SOURCE, target, priority, added, new_conflicts)
        new = _add_constraint(db, ctx, row, ConstraintAction.PREFER_SOURCE, content, priority, added, new_conflicts)
        details = {"excluded_constraint_id": str(old.id), "preferred_constraint_id": str(new.id)}
        result = f"Excluding '{target}', preferring '{content}'"
    elif t == T.ADD_CONSTRAINT:
        c = _add_constraint(db, ctx, row, data.action, target, priority, added, new_conflicts)
        details = {"constraint_id": str(c.id), "action": data.action.value, "created": c in added}
        result = "Constraint added" if c in added else "An identical constraint is already active"
    elif t == T.REMOVE_CONSTRAINT:
        try:
            c = ConstraintManager.remove(db, sid, data.constraint_id, user)
        except LookupError:
            db.rollback()
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Constraint not found or already removed")
        if c.action in (ConstraintAction.EXCLUDE_SOURCE, ConstraintAction.INCLUDE_SOURCE):
            MemoryManager.deactivate_source(db, sid, c.target)
        resolved_conflicts.extend(ConflictManager.close_for_constraint(db, c))
        removed.append((c, "removed"))
        row.target = c.target
        details = {"constraint_id": str(c.id)}
        result = "Constraint removed"
    elif t == T.RESOLVE_CONFLICT:
        conflict = db.get(Conflict, data.conflict_id)
        if conflict is None or conflict.session_id != sid:
            db.rollback()
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conflict not found")
        if conflict.status != ConflictStatus.OPEN:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "This conflict is already resolved")
        try:
            superseded = ConflictManager.resolve(db, conflict, user, data.winner_constraint_id, content)
        except ValueError:
            db.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The winner must be one of the two constraints in the conflict")
        for c in superseded:
            removed.append((c, "superseded"))
            if c.action in (ConstraintAction.EXCLUDE_SOURCE, ConstraintAction.INCLUDE_SOURCE):
                MemoryManager.deactivate_source(db, sid, c.target)
        resolved_conflicts.append(conflict)
        MemoryManager.remember(
            db, kind=MemoryKind.DECISION, importance=4,
            content=f"Conflict resolved by {user.username}: " + (
                "both instructions removed" if data.winner_constraint_id is None
                else f"kept the instruction on '{target or ''}'".replace(" on ''", "")
            ) + (f" ({content})" if content else ""),
            **memory,
        )
        details = {
            "conflict_id": str(conflict.id),
            "winner_constraint_id": str(data.winner_constraint_id) if data.winner_constraint_id else None,
        }
        result = "Conflict resolved"
    elif t in (T.APPROVE, T.REJECT):
        approved = t == T.APPROVE
        label = "final draft" if pending.kind == ApprovalKind.FINAL_REPORT else "review request"
        pending.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        pending.decided_by = user.id
        pending.note = content
        pending.decided_at = datetime.now(timezone.utc)
        if approved:
            MemoryManager.remember(db, kind=MemoryKind.DECISION, content=f"{user.username} approved the {label}", importance=2, **memory)
        else:
            MemoryManager.remember(
                db, kind=MemoryKind.CORRECTION,
                content=f"A reviewer rejected the {label}: {content or 'no reason given'}",
                importance=5, **memory,
            )
        details = {"approval_id": str(pending.id), "kind": pending.kind.value}
        approval_event = {"approval_id": str(pending.id), "kind": pending.kind.value, "approved": approved, "note": content}
        result = "Approved" if approved else "Rejected; the agent will revise"
    elif t == T.REQUEST_REVIEW:
        result = "Review requested; the agent will wait for approval at its next checkpoint"
    elif t == T.PAUSE:
        result = "Paused"
    elif t == T.RESUME:
        result = "Resumed"

    if new_conflicts:
        result += f"; {len(new_conflicts)} conflict(s) detected"
    if data.origin_text:  # original sentence: audit trail and classifier feedback
        details = {**details, "origin_text": data.origin_text[:500]}
        record_outcome(db, sid, user.id, data.origin_text, t.value)
    row.details = details
    row.result = result
    db.commit()
    logger.info("intervention %s by %s in session %s: %s", t.value, user.username, sid, result)

    # ---- broadcast (after the commit, so listeners can immediately read the data) ----
    for c in added:
        await event_service.publish(db, sid, EventType.CONSTRAINT_ADDED, {"constraint": constraint_read(c).model_dump(mode="json")}, user)
    for c, reason in removed:
        await event_service.publish(
            db, sid, EventType.CONSTRAINT_REMOVED,
            {"constraint_id": str(c.id), "target": c.target, "action": c.action.value, "reason": reason}, user,
        )
    for conflict in new_conflicts:
        read = ConflictManager.to_read(db, conflict)
        await event_service.publish(db, sid, EventType.CONFLICT_DETECTED, {"conflict": read.model_dump(mode="json")}, user)
        await event_service.publish(
            db, sid, EventType.AGENT_MESSAGE,
            {"kind": "warning", "text": (
                f"Conflict detected: \"{read.constraint_a.description}\" vs \"{read.constraint_b.description}\". "
                + ("The agent will wait for the owner to resolve it. " if read.requires_resolution else "")
                + (read.provisional or "")
            )},
            user,
        )
    for conflict in resolved_conflicts:
        read = ConflictManager.to_read(db, conflict)
        await event_service.publish(db, sid, EventType.CONFLICT_RESOLVED, {"conflict": read.model_dump(mode="json")}, user)
    if resolved_conflicts:
        agent_runner.conflicts_changed(sid)
    if approval_event is not None:
        await event_service.publish(db, sid, EventType.APPROVAL_COMPLETED, approval_event, user)

    read = intervention_read(row)
    await event_service.publish(db, sid, EventType.HUMAN_INTERVENTION, {"intervention": read.model_dump(mode="json")}, user)
    return read