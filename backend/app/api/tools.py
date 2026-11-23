from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, get_current_user, get_session_context
from app.db.session import get_db
from app.models.tool_execution import ToolExecution
from app.models.user import User
from app.schemas.tools import ToolExecutionRead, ToolSpecRead
from app.tools import get_registry

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=list[ToolSpecRead])
def list_approved_tools(_: User = Depends(get_current_user)) -> list[ToolSpecRead]:
    """The complete list of what the agent is allowed to do."""
    return [
        ToolSpecRead(name=s.name, description=s.description, parameters=s.parameters, side_effects=s.side_effects)
        for s in get_registry().specs()
    ]


@router.get("/sessions/{session_id}/tools", response_model=list[ToolExecutionRead])
async def list_tool_executions(
    status_filter: str = Query("all", alias="status", pattern="^(all|SUCCESS|ERROR|REJECTED|TIMEOUT)$"),
    limit: int = Query(200, ge=1, le=500),
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> list[ToolExecution]:
    stmt = select(ToolExecution).where(ToolExecution.session_id == ctx.session.id)
    if status_filter != "all":
        stmt = stmt.where(ToolExecution.status == status_filter)
    return list(reversed(db.scalars(stmt.order_by(ToolExecution.created_at.desc()).limit(limit)).all()))