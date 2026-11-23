import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, get_session_context
from app.db.session import get_db
from app.models.conflict import Conflict, ConflictStatus
from app.models.intervention import InterventionType
from app.schemas.conflict import ConflictRead, ResolveRequest
from app.schemas.intervention import InterventionCreate
from app.services.conflict_manager import ConflictManager
from app.services.intervention_service import process_intervention

router = APIRouter(prefix="/sessions", tags=["conflicts"])


@router.get("/{session_id}/conflicts", response_model=list[ConflictRead])
async def list_conflicts(
    status: str = Query("all", pattern="^(all|OPEN|RESOLVED)$"),
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> list[ConflictRead]:
    wanted = None if status == "all" else ConflictStatus(status)
    return [ConflictManager.to_read(db, c) for c in ConflictManager.list(db, ctx.session.id, wanted)]


@router.post("/{session_id}/conflicts/{conflict_id}/resolve", response_model=ConflictRead)
async def resolve_conflict(
    conflict_id: uuid.UUID,
    data: ResolveRequest,
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> ConflictRead:
    # Owner-only, audited, and broadcast: all handled by the intervention processor.
    await process_intervention(
        db, ctx,
        InterventionCreate(
            type=InterventionType.RESOLVE_CONFLICT,
            conflict_id=conflict_id,
            winner_constraint_id=data.winner_constraint_id,
            content=data.note,
        ),
    )
    return ConflictManager.to_read(db, db.get(Conflict, conflict_id))