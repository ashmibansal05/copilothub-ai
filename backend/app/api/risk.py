import asyncio
import json
import logging

from fastapi import APIRouter, Depends

from app.api.deps import SessionContext, get_current_user, get_session_context
from app.core.config import get_settings
from app.db import session as db_session
from app.ml import service as risk_service
from app.ml import train as trainer
from app.models.user import User
from app.schemas.ml import MLStatus, RiskFactorRead, RiskRead

logger = logging.getLogger("copilothub.ml")
router = APIRouter(tags=["ml"])


def _latest(session_id):
    with db_session.SessionLocal() as db:
        return risk_service.estimate_for_latest_step(db, session_id)


@router.get("/sessions/{session_id}/risk", response_model=RiskRead)
async def get_risk(ctx: SessionContext = Depends(get_session_context)) -> RiskRead:
    """Estimated probability that a human will need to intervene, after the latest step."""
    if not get_settings().risk_prediction_enabled:
        return RiskRead(available=False, reason="Risk prediction is switched off")
    try:
        estimate = await asyncio.to_thread(_latest, ctx.session.id)
    except Exception:
        logger.warning("Risk estimate failed", exc_info=True)
        return RiskRead(available=False, reason="The risk model is unavailable (run: python -m app.ml.train)")
    if estimate is None:
        return RiskRead(available=False, reason="No step has been completed yet")
    return RiskRead(
        available=True, probability=round(estimate.probability, 4), level=estimate.level,
        model=estimate.model_name, data_source=estimate.data_source, step_index=estimate.step_index,
        factors=[RiskFactorRead(**f.__dict__) for f in estimate.factors], warning=estimate.warning,
    )


@router.get("/ml/status", response_model=MLStatus)
def ml_status(_: User = Depends(get_current_user)) -> MLStatus:
    """The real comparison numbers from the last training run (nothing is made up)."""
    path = trainer.metrics_path()
    if not path.exists():
        return MLStatus(available=False)
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return MLStatus(available=False)
    return MLStatus(
        available=True, data_source=m.get("data_source"), trained_at=m.get("trained_at"),
        selected_model=m.get("selected_model"), selection_rule=m.get("selection_rule"),
        n_rows=m.get("n_rows"), n_test=m.get("n_test"), positive_rate=m.get("positive_rate"),
        models=m.get("models", {}), baseline=m.get("baseline"), warning=m.get("warning"),
    )