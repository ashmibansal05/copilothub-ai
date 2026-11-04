from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, get_current_user, get_session_context
from app.core.config import get_settings
from app.db.session import get_db
from app.llm.factory import get_llm_provider
from app.models.agent import AgentAction
from app.models.user import User
from app.schemas.agent import AgentActionRead, AgentStateRead, LLMStatus
from app.services import agent_service

router = APIRouter(tags=["agent"])


@router.get("/sessions/{session_id}/state", response_model=AgentStateRead)
async def get_agent_state(
    ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)
) -> AgentStateRead:
    return agent_service.build_state_read(db, ctx.session)


@router.get("/sessions/{session_id}/actions", response_model=list[AgentActionRead])
async def list_actions(
    limit: int = Query(200, ge=1, le=500),
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> list[AgentAction]:
    stmt = (
        select(AgentAction)
        .where(AgentAction.session_id == ctx.session.id)
        .order_by(AgentAction.created_at.desc())
        .limit(limit)
    )
    return list(reversed(db.scalars(stmt).all()))


@router.get("/llm/status", response_model=LLMStatus)
async def llm_status(_: User = Depends(get_current_user)) -> LLMStatus:
    settings = get_settings()
    try:
        provider = get_llm_provider()
    except ValueError as exc:
        return LLMStatus(
            provider=settings.llm_provider, model="", demo_mode=settings.demo_mode,
            reachable=False, model_available=False, ready=False, detail=str(exc),
        )
    health = await provider.health()
    return LLMStatus(
        provider=provider.name, model=provider.model, demo_mode=settings.demo_mode,
        reachable=health.reachable, model_available=health.model_available,
        ready=health.ready, detail=health.detail,
    )