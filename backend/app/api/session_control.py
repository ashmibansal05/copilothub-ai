from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, require_session_role
from app.db.session import get_db
from app.models.user import UserRole
from app.schemas.session import StateResponse
from app.services.session_control import apply_transition

router = APIRouter(prefix="/sessions", tags=["session-control"])

OwnerOnly = Depends(require_session_role(UserRole.OWNER))
OwnerOrEditor = Depends(require_session_role(UserRole.OWNER, UserRole.EDITOR))


@router.post("/{session_id}/start", response_model=StateResponse)
async def start_session(ctx: SessionContext = OwnerOnly, db: Session = Depends(get_db)):
    return await apply_transition("start", ctx, db)


@router.post("/{session_id}/pause", response_model=StateResponse)
async def pause_session(ctx: SessionContext = OwnerOrEditor, db: Session = Depends(get_db)):
    return await apply_transition("pause", ctx, db)


@router.post("/{session_id}/resume", response_model=StateResponse)
async def resume_session(ctx: SessionContext = OwnerOrEditor, db: Session = Depends(get_db)):
    return await apply_transition("resume", ctx, db)


@router.post("/{session_id}/stop", response_model=StateResponse)
async def stop_session(ctx: SessionContext = OwnerOnly, db: Session = Depends(get_db)):
    return await apply_transition("stop", ctx, db)