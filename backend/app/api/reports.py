import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, get_session_context
from app.db.session import get_db
from app.models.report import Report
from app.schemas.tools import ReportDetail, ReportSummary

router = APIRouter(prefix="/sessions", tags=["reports"])


def _summary(r: Report) -> ReportSummary:
    return ReportSummary(
        id=r.id, title=r.title, format=r.format, origin=r.origin, status=r.status,
        chars=len(r.content), created_at=r.created_at,
    )


@router.get("/{session_id}/reports", response_model=list[ReportSummary])
async def list_reports(
    ctx: SessionContext = Depends(get_session_context), db: Session = Depends(get_db)
) -> list[ReportSummary]:
    rows = db.scalars(
        select(Report).where(Report.session_id == ctx.session.id).order_by(Report.created_at)
    ).all()
    return [_summary(r) for r in rows]


@router.get("/{session_id}/reports/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: uuid.UUID,
    ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> ReportDetail:
    report = db.scalar(select(Report).where(Report.id == report_id, Report.session_id == ctx.session.id))
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return ReportDetail(**_summary(report).model_dump(), content=report.content)