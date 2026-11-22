import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import Approval, ApprovalStatus


def get_pending(db: Session, session_id: uuid.UUID) -> Approval | None:
    return db.scalar(
        select(Approval)
        .where(Approval.session_id == session_id, Approval.status == ApprovalStatus.PENDING)
        .order_by(Approval.created_at.desc())
        .limit(1)
    )


def expire_pending(db: Session, session_id: uuid.UUID) -> int:
    """Close approvals that can no longer be answered (session ended, restart...)."""
    rows = db.scalars(
        select(Approval).where(
            Approval.session_id == session_id, Approval.status == ApprovalStatus.PENDING
        )
    ).all()
    for row in rows:
        row.status = ApprovalStatus.EXPIRED
    if rows:
        db.commit()
    return len(rows)