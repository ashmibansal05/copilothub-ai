import numpy as np
import pandas as pd
import pytest

from app.core.config import get_settings
from app.ml import service as risk_service
from app.ml import synthetic
from app.ml import train as trainer
from app.ml.features import FEATURE_NAMES

LOW_RISK = dict(agent_confidence=0.95, min_confidence_so_far=0.9, tool_failures_so_far=0, tool_failures_this_step=0,
                retries_so_far=0, open_conflicts=0, source_rejection_rate=0.0, human_corrections_so_far=0)
HIGH_RISK = dict(agent_confidence=0.15, min_confidence_so_far=0.1, tool_failures_so_far=4, tool_failures_this_step=2,
                 retries_so_far=3, open_conflicts=1, source_rejection_rate=0.6, human_corrections_so_far=2)


@pytest.fixture(scope="module")
def trained():
    return trainer.train_models(synthetic.generate(1500, seed=7), "synthetic", seed=7)


def test_synthetic_data_is_well_formed_and_reproducible():
    a, b = synthetic.generate(800, seed=1), synthetic.generate(800, seed=1)
    assert a.equals(b) and not a.equals(synthetic.generate(800, seed=2))
    assert list(a.columns) == FEATURE_NAMES + ["label"] and not a.isna().any().any()
    assert set(a["label"]) == {0, 1} and 0.05 < a["label"].mean() < 0.95
    assert a["agent_confidence"].between(0, 1).all() and (a["min_confidence_so_far"] <= a["agent_confidence"]).all()
    assert (a["step_number"] <= a["plan_steps"]).all()


def test_training_compares_the_models_with_computed_metrics(trained):
    artifact, metrics = trained
    assert metrics["data_source"] == "synthetic" and "SYNTHETIC" in metrics["warning"]
    assert {"logistic_regression", "random_forest"} <= set(metrics["models"])
    for name, result in metrics["models"].items():
        test = result["test"]
        assert all(0.0 <= test[k] <= 1.0 for k in ("accuracy", "precision", "recall", "f1", "roc_auc")), name
        assert sum(test["confusion"].values()) == metrics["n_test"]
        assert 0.0 <= result["cv_roc_auc_mean"] <= 1.0
    assert metrics["models"]["logistic_regression"]["test"]["roc_auc"] > 0.6  # it learns the (assumed) signal
    assert metrics["n_train"] + metrics["n_test"] == metrics["n_rows"] == 1500
    assert 0.0 <= metrics["baseline"]["roc_auc"] <= 1.0 and "confidence" in metrics["baseline"]["rule"]


def test_the_model_is_chosen_on_validation_not_on_the_test_set(trained):
    _, metrics = trained
    models = metrics["models"]
    best = max(models, key=lambda n: (models[n]["cv_roc_auc_mean"], -trainer.MODEL_ORDER.index(n)))
    assert metrics["selected_model"] == best
    assert "test split is never used" in metrics["selection_rule"]


def test_xgboost_is_part_of_the_comparison_when_installed(trained):
    pytest.importorskip("xgboost")
    assert "xgboost" in trained[1]["models"]


def test_group_split_keeps_sessions_together():
    y = np.array([0, 1] * 60)
    groups = np.repeat(np.arange(40), 3)
    train, test = trainer.split_indices(y, groups, seed=3)
    assert not set(groups[train]) & set(groups[test])
    with pytest.raises(ValueError):
        trainer.split_indices(np.zeros(60, dtype=int), None, seed=3)


def test_training_refuses_degenerate_data():
    frame = synthetic.generate(500, seed=1)
    with pytest.raises(ValueError, match="only one class"):
        trainer.train_models(frame.assign(label=0), "synthetic")
    with pytest.raises(ValueError, match="At least 100"):
        trainer.train_models(frame.head(50), "synthetic")


def test_save_load_and_serve(trained, ml_sandbox):
    artifact, metrics = trained
    trainer.save_artifact(artifact, metrics)
    assert trainer.artifact_path().exists() and trainer.metrics_path().exists()
    risk_service.reset_cache()
    loaded = risk_service.get_model()  # loads the file; does not retrain
    assert loaded.name == metrics["selected_model"] and loaded.meta["data_source"] == "synthetic"


def test_higher_risk_inputs_give_a_higher_probability_and_a_synthetic_warning(trained, ml_sandbox):
    artifact, metrics = trained
    trainer.save_artifact(artifact, metrics)
    risk_service.reset_cache()
    base = {n: risk_service.get_model().feature_means[n] for n in FEATURE_NAMES}
    low = risk_service.predict_features({**base, **LOW_RISK})
    high = risk_service.predict_features({**base, **HIGH_RISK})
    assert 0.0 <= low.probability < high.probability <= 1.0
    assert low.level in ("LOW", "MEDIUM") and high.level in ("MEDIUM", "HIGH")
    assert "SYNTHETIC" in high.warning
    assert 1 <= len(high.factors) <= 3 and abs(high.factors[0].effect) >= abs(high.factors[-1].effect)
    assert high.factors[0].effect > 0  # the strongest driver raises the risk


def test_levels():
    assert [risk_service.level_for(p) for p in (0.0, 0.32, 0.33, 0.65, 0.66, 1.0)] == ["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH"]


def test_first_use_trains_on_synthetic_data_unless_switched_off(ml_sandbox, monkeypatch):
    model = risk_service.get_model()
    assert model.meta["data_source"] == "synthetic" and trainer.artifact_path().exists()
    risk_service.reset_cache()
    trainer.artifact_path().unlink()
    monkeypatch.setattr(get_settings(), "risk_auto_train", False)
    with pytest.raises(RuntimeError, match="python -m app.ml.train"):
        risk_service.get_model()