import logging
import threading
import uuid
from dataclasses import dataclass, field

import joblib
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import session as db_session
from app.ml import synthetic
from app.ml import train as trainer
from app.ml.features import FEATURE_LABELS, aware, build_step_features
from app.models.agent import AgentAction
from app.models.risk_prediction import RiskPrediction

logger = logging.getLogger("copilothub.ml")

LOW, HIGH = 0.33, 0.66  # level boundaries (documented; the probabilities are not calibrated)


def level_for(probability: float) -> str:
    return "LOW" if probability < LOW else "MEDIUM" if probability < HIGH else "HIGH"


@dataclass
class RiskFactor:
    feature: str
    label: str
    effect: float  # how much this feature currently raises (+) or lowers (-) the probability
    value: float


@dataclass
class RiskEstimate:
    probability: float
    level: str
    model_name: str
    data_source: str
    step_index: int
    factors: list[RiskFactor]
    features: dict[str, float]
    warning: str | None = None

    def event_payload(self) -> dict:
        return {
            "available": True, "step_index": self.step_index, "probability": round(self.probability, 4),
            "level": self.level, "model": self.model_name, "data_source": self.data_source,
            "factors": [f.__dict__ for f in self.factors], "warning": self.warning,
        }


@dataclass
class LoadedModel:
    model: object
    name: str
    feature_names: list[str]
    feature_means: dict[str, float]
    meta: dict = field(default_factory=dict)


_lock = threading.Lock()
_cached: LoadedModel | None = None


def get_model() -> LoadedModel:
    """The saved model, or (first use only) one trained on SYNTHETIC data and clearly labelled so."""
    global _cached
    with _lock:
        if _cached is not None:
            return _cached
        path = trainer.artifact_path()
        if path.exists():
            blob = joblib.load(path)  # only ever our own file in our own data folder
        else:
            settings = get_settings()
            if not settings.risk_auto_train:
                raise RuntimeError("No trained risk model. Run: python -m app.ml.train")
            logger.warning("Training the risk model on SYNTHETIC data (no real sessions yet)")
            blob, metrics = trainer.train_models(synthetic.generate(settings.risk_synthetic_rows), "synthetic")
            trainer.save_artifact(blob, metrics)
        _cached = LoadedModel(blob["model"], blob["model_name"], blob["feature_names"], blob["feature_means"], blob["meta"])
        return _cached


def reset_cache() -> None:
    global _cached
    _cached = None


def predict_features(features: dict[str, float], loaded: LoadedModel | None = None, step_index: int = 0) -> RiskEstimate:
    loaded = loaded or get_model()
    names = loaded.feature_names
    row = {n: float(features.get(n, loaded.feature_means.get(n, 0.0))) for n in names}
    X = pd.DataFrame([row], columns=names)
    probability = float(loaded.model.predict_proba(X)[0, 1])

    # Model-agnostic explanation: replace one feature at a time by its training average and
    # see how much the prediction moves.
    variants = pd.concat([X] * len(names), ignore_index=True)
    for i, name in enumerate(names):
        variants.loc[i, name] = loaded.feature_means[name]
    averaged = loaded.model.predict_proba(variants)[:, 1]
    effects = sorted(((n, probability - float(p)) for n, p in zip(names, averaged)), key=lambda t: abs(t[1]), reverse=True)
    factors = [
        RiskFactor(n, FEATURE_LABELS.get(n, n), round(e, 3), round(row[n], 3)) for n, e in effects[:3] if abs(e) >= 0.01
    ]
    source = loaded.meta.get("data_source", "synthetic")
    warning = loaded.meta.get("warning") if source != "real" else None
    return RiskEstimate(probability, level_for(probability), loaded.name, source, step_index, factors, row, warning)


def _latest_evaluation(db: Session, session_id: uuid.UUID) -> AgentAction | None:
    """Find the highest-index successful evaluation for this session."""
    return db.scalar(
        select(AgentAction)
        .where(
            AgentAction.session_id == session_id,
            AgentAction.action_type == "EVALUATE",
            AgentAction.success.is_(True),
        )
        .order_by(
            AgentAction.step_index.desc(),
            AgentAction.created_at.desc(),
            AgentAction.id.desc(),
        )
        .limit(1)
    )


def estimate_for_latest_step(db: Session, session_id: uuid.UUID) -> RiskEstimate | None:
    """Risk right after the most recent evaluated step (None if no step finished yet)."""
    row = _latest_evaluation(db, session_id)
    if row is None:
        return None
    features = build_step_features(db, session_id, row.step_index, row.created_at)
    return predict_features(features, step_index=row.step_index)


def estimate_and_store(session_id: uuid.UUID) -> RiskEstimate | None:
    """Used by the agent after every step: compute, remember (for later evaluation) and return."""
    with db_session.SessionLocal() as db:
        row = _latest_evaluation(db, session_id)
        if row is None:
            return None
        features = build_step_features(db, session_id, row.step_index, row.created_at)
        estimate = predict_features(features, step_index=row.step_index)
        db.add(RiskPrediction(
            session_id=session_id, step_index=row.step_index, snapshot_at=aware(row.created_at),
            probability=estimate.probability, level=estimate.level, model_name=estimate.model_name,
            data_source=estimate.data_source, features=estimate.features,
        ))
        db.commit()
        return estimate