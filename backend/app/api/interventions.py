import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import SessionContext, get_session_context
from app.db.session import get_db
from app.models.intervention import Intervention, InterventionType
from app.schemas.auth import MessageResponse
from app.schemas.intervention import (
    ConstraintCreate,
    ConstraintRead,
    InterventionCreate,
    InterventionRead,
    MemoryRead,
)
from app.services.constraint_manager import ConstraintManager
from app.services.intervention_service import process_intervention
from app.services.memory_manager import MemoryManager
from app.services.readers import constraint_read, intervention_read

router = APIRouter(prefix="/sessions", tags=["interventions"])


@router.post("/{session_id}/interventions", response_model=InterventionRead, status_code=status.HTTP_201_CREATED)
async def create_intervention(
    data: InterventionCreate,
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> InterventionRead:
    return await process_intervention(db, ctx, data)


@router.get("/{session_id}/interventions", response_model=list[InterventionRead])
async def list_interventions(
    limit: int = Query(100, ge=1, le=300),
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> list[InterventionRead]:
    rows = db.scalars(
        select(Intervention)
        .options(joinedload(Intervention.user))
        .where(Intervention.session_id == ctx.session.id)
        .order_by(Intervention.created_at.desc())
        .limit(limit)
    ).all()
    return [intervention_read(r) for r in rows]


@router.get("/{session_id}/constraints", response_model=list[ConstraintRead])
async def list_constraints(
    ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)
) -> list[ConstraintRead]:
    return [constraint_read(c) for c in ConstraintManager.active(db, ctx.session.id)]


@router.post("/{session_id}/constraints", response_model=ConstraintRead, status_code=status.HTTP_201_CREATED)
async def add_constraint(
    data: ConstraintCreate,
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> ConstraintRead:
    # Goes through the intervention processor so it is permission-checked and audited.
    iv = await process_intervention(
        db, ctx,
        InterventionCreate(
            type=InterventionType.ADD_CONSTRAINT, action=data.action,
            target=data.target, priority=data.priority,
        ),
    )
    constraint = ConstraintManager.get(db, uuid.UUID(iv.details["constraint_id"]))
    if constraint is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Constraint was not stored")
    return constraint_read(constraint)


@router.delete("/{session_id}/constraints/{constraint_id}", response_model=MessageResponse)
async def remove_constraint(
    constraint_id: uuid.UUID,
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> MessageResponse:
    await process_intervention(
        db, ctx, InterventionCreate(type=InterventionType.REMOVE_CONSTRAINT, constraint_id=constraint_id)
    )
    return MessageResponse(message="Constraint removed")


@router.get("/{session_id}/memory", response_model=MemoryRead)
async def get_memory(
    ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)
) -> MemoryRead:
    return MemoryRead(
        constraints=[constraint_read(c) for c in ConstraintManager.active(db, ctx.session.id)],
        items=MemoryManager.list_active(db, ctx.session.id),
    )