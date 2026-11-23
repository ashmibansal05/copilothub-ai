import csv
import io
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, get_current_user, get_session_context
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsOverview, SessionAnalytics
from app.services import analytics_service

router = APIRouter(tags=["analytics"])


@router.get("/sessions/{session_id}/analytics", response_model=SessionAnalytics)
async def session_analytics(
    ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)
) -> SessionAnalytics:
    return analytics_service.compute(db, ctx.session)[0]


@router.get("/analytics/overview", response_model=AnalyticsOverview)
async def analytics_overview(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AnalyticsOverview:
    """Aggregated over every session you are a member of."""
    return analytics_service.overview(db, user)


@router.get("/analytics/export.csv")
async def export_csv(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Per-session metric snapshots (written when sessions end) for the research evaluation.
    Contains ids and numbers only: no names or text."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=analytics_service.CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(analytics_service.export_rows(db, user))
    return Response(
        content=buffer.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="copilothub-analytics.csv"'},
    )