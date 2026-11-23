
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.intent_sample import IntentSample


def record_outcome(
    db: Session,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    text: str,
    final_type: str,
) -> None:
    """Remember what a human finally did with a classified sentence
    (confirmed, edited or auto-applied).

    Called inside the intervention transaction; the caller commits.
    """
    sample = db.scalar(
        select(IntentSample)
        .where(
            IntentSample.session_id == session_id,
            IntentSample.user_id == user_id,
            IntentSample.text == text,
            IntentSample.final_type.is_(None),
        )
        .order_by(IntentSample.created_at.desc())
        .limit(1)
    )

    if sample is not None:
        sample.final_type = final_type
