from typing import Any

from pydantic import BaseModel


class RiskFactorRead(BaseModel):
    feature: str
    label: str
    effect: float
    value: float


class RiskRead(BaseModel):
    available: bool
    reason: str | None = None
    probability: float | None = None
    level: str | None = None
    model: str | None = None
    data_source: str | None = None
    step_index: int | None = None
    factors: list[RiskFactorRead] = []
    warning: str | None = None


class MLStatus(BaseModel):
    available: bool
    data_source: str | None = None
    trained_at: str | None = None
    selected_model: str | None = None
    selection_rule: str | None = None
    n_rows: int | None = None
    n_test: int | None = None
    positive_rate: float | None = None
    models: dict[str, Any] = {}
    baseline: dict[str, Any] | None = None
    warning: str | None = None