
"""Train the intervention-risk predictor and print an honest comparison.

Usage:
    python -m app.ml.train
        # SYNTHETIC data (the only option at first)

    python -m app.ml.train --source real
        # Real sessions from the database

    python -m app.ml.train --source mixed
        # Real + synthetic (synthetic capped at 2x real)

    python -m app.ml.train --export-real data/ml/real_steps.csv
        # Export the real rows

    python -m app.ml.train --no-save
        # Evaluate only

Every number is computed from the data; nothing is hard-coded.
"""

import argparse
import logging
from datetime import datetime, timezone
from typing import Any

import joblib
import numpy as np
import pandas as pd

from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    GroupShuffleSplit,
    StratifiedGroupKFold,
    StratifiedKFold,
    cross_val_score,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.core.config import get_settings
from app.ml.features import FEATURE_NAMES


logger = logging.getLogger("copilothub.ml")

MODEL_ORDER = [
    "logistic_regression",
    "random_forest",
    "xgboost",
]

WARNINGS = {
    "synthetic": (
        "SYNTHETIC DATA: the labels were generated from assumed "
        "relationships written by the project author. These scores "
        "show how well each model recovers those assumptions, NOT "
        "how well it predicts real human interventions."
    ),
    "mixed": (
        "MIXED DATA: real sessions plus synthetic rows. Scores "
        "partly reflect the synthetic assumptions."
    ),
    "real": (
        "Real sessions. Small samples give unstable estimates; "
        "treat the numbers as indicative."
    ),
}


# ============================================================
# Model Paths
# ============================================================

def model_dir():
    return get_settings().data_path / "ml"


def artifact_path():
    return model_dir() / "risk_model.joblib"


def metrics_path():
    return model_dir() / "risk_metrics.json"


# ============================================================
# Model Definitions
# ============================================================

def make_models(seed: int, pos_weight: float) -> dict[str, Any]:
    models: dict[str, Any] = {
        "logistic_regression": Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                    ),
                ),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=3,
            class_weight="balanced_subsample",
            random_state=seed,
            n_jobs=1,
        ),
    }

    try:
        from xgboost import XGBClassifier

        models["xgboost"] = XGBClassifier(
            n_estimators=300,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            scale_pos_weight=pos_weight,
            random_state=seed,
            n_jobs=1,
        )

    except ImportError:
        logger.warning(
            "xgboost is not installed; it is skipped in the comparison"
        )

    return models


# ============================================================
# Train/Test Split
# ============================================================

def split_indices(
    y: np.ndarray,
    groups: np.ndarray | None,
    seed: int,
    test_size: float = 0.25,
):
    """
    Split data into training and testing sets.

    For real data, whole sessions remain on one side of
    the split so steps from the same session do not appear
    in both training and testing sets.
    """

    index = np.arange(len(y))

    if groups is not None:
        train, test = next(
            GroupShuffleSplit(
                n_splits=1,
                test_size=test_size,
                random_state=seed,
            ).split(index, y, groups)
        )

    else:
        train, test = train_test_split(
            index,
            test_size=test_size,
            random_state=seed,
            stratify=y,
        )

    if len(set(y[train])) < 2 or len(set(y[test])) < 2:
        raise ValueError(
            "A split is missing one of the classes: "
            "more data is needed"
        )

    return train, test


# ============================================================
# Evaluation Metrics
# ============================================================

def _scores(
    y_true: np.ndarray,
    proba: np.ndarray,
) -> dict:
    """
    Calculate classification metrics from real predictions.
    """

    pred = (proba >= 0.5).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_true,
        pred,
        labels=[0, 1],
    ).ravel()

    return {
        "accuracy": float(
            accuracy_score(y_true, pred)
        ),
        "precision": float(
            precision_score(
                y_true,
                pred,
                zero_division=0,
            )
        ),
        "recall": float(
            recall_score(
                y_true,
                pred,
                zero_division=0,
            )
        ),
        "f1": float(
            f1_score(
                y_true,
                pred,
                zero_division=0,
            )
        ),
        "roc_auc": float(
            roc_auc_score(y_true, proba)
        ),
        "confusion": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
    }


# ============================================================
# Training and Model Comparison
# ============================================================

def train_models(
    frame: pd.DataFrame,
    data_source: str,
    seed: int = 42,
    groups: np.ndarray | None = None,
) -> tuple[dict, dict]:
    """
    Compare multiple ML models and select the best using
    cross-validated ROC-AUC.

    The test set is not used for selecting the model.

    The selected model is then refitted on all available data.

    Returns:
        artifact: Trained model and metadata.
        metrics: Evaluation results.
    """

    if len(frame) < 100:
        raise ValueError(
            "At least 100 rows are needed"
        )

    X = frame[FEATURE_NAMES].reset_index(drop=True)
    y = frame["label"].to_numpy().astype(int)

    if len(set(y)) < 2:
        raise ValueError(
            "The data contains only one class"
        )

    train_idx, test_idx = split_indices(
        y,
        groups,
        seed,
    )

    X_train = X.iloc[train_idx]
    X_test = X.iloc[test_idx]

    y_train = y[train_idx]
    y_test = y[test_idx]

    g_train = (
        groups[train_idx]
        if groups is not None
        else None
    )

    n_splits = min(
        5,
        int(np.bincount(y_train).min()),
    )

    if n_splits < 2:
        raise ValueError(
            "Too few examples of one class for cross-validation"
        )

    if groups is not None:
        cv = StratifiedGroupKFold(
            n_splits=n_splits,
            shuffle=True,
            random_state=seed,
        )
    else:
        cv = StratifiedKFold(
            n_splits=n_splits,
            shuffle=True,
            random_state=seed,
        )

    pos_weight = float(
        (y_train == 0).sum()
        / max(1, (y_train == 1).sum())
    )

    results: dict[str, dict] = {}

    models = make_models(
        seed,
        pos_weight,
    )

    # --------------------------------------------------------
    # Compare models
    # --------------------------------------------------------

    for name, model in models.items():
        cv_scores = cross_val_score(
            model,
            X_train,
            y_train,
            cv=cv,
            scoring="roc_auc",
            groups=g_train,
        )

        fitted = clone(model).fit(
            X_train,
            y_train,
        )

        probabilities = fitted.predict_proba(
            X_test
        )[:, 1]

        results[name] = {
            "cv_roc_auc_mean": float(
                cv_scores.mean()
            ),
            "cv_roc_auc_std": float(
                cv_scores.std()
            ),
            "test": _scores(
                y_test,
                probabilities,
            ),
        }

    # --------------------------------------------------------
    # Baseline comparison
    # --------------------------------------------------------

    # Simple rule:
    # Predict intervention when agent confidence < 0.5.

    rule_prediction = (
        X_test["agent_confidence"].to_numpy() < 0.5
    ).astype(int)

    baseline = _scores(
        y_test,
        rule_prediction.astype(float),
    )

    # Use continuous confidence-based risk scores for ROC-AUC.
    baseline["roc_auc"] = float(
        roc_auc_score(
            y_test,
            1.0 - X_test["agent_confidence"].to_numpy(),
        )
    )

    baseline["rule"] = (
        "predict an intervention when agent_confidence < 0.5"
    )

    # --------------------------------------------------------
    # Select best model
    # --------------------------------------------------------

    ranked = sorted(
        results,
        key=lambda n: (
            -results[n]["cv_roc_auc_mean"],
            MODEL_ORDER.index(n),
        ),
    )

    selected = ranked[0]

    # Refit selected model on all data for deployment.
    final = clone(
        models[selected]
    ).fit(X, y)

    # --------------------------------------------------------
    # Metrics and metadata
    # --------------------------------------------------------

    metrics = {
        "trained_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "data_source": data_source,
        "n_rows": int(len(frame)),
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "positive_rate": float(y.mean()),
        "n_groups": (
            int(len(set(groups)))
            if groups is not None
            else None
        ),
        "feature_names": FEATURE_NAMES,
        "models": results,
        "baseline": baseline,
        "selected_model": selected,
        "selection_rule": (
            "highest mean cross-validated ROC-AUC on "
            "the training split (the test split is "
            "never used to choose)"
        ),
        "warning": WARNINGS[data_source],
    }

    artifact = {
        "model": final,
        "model_name": selected,
        "feature_names": FEATURE_NAMES,
        "feature_means": {
            k: float(v)
            for k, v in X.mean().items()
        },
        "meta": metrics,
    }

    return artifact, metrics


# ============================================================
# Save Model and Metrics
# ============================================================

def save_artifact(
    artifact: dict,
    metrics: dict,
) -> None:
    import json

    model_dir().mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        artifact,
        artifact_path(),
    )

    metrics_path().write_text(
        json.dumps(
            metrics,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# Print Training Report
# ============================================================

def _print_report(metrics: dict) -> None:
    print(
        f"\nData source: {metrics['data_source'].upper()}   "
        f"rows: {metrics['n_rows']} "
        f"(train {metrics['n_train']}, "
        f"held-out test {metrics['n_test']})   "
        f"share with an intervention: "
        f"{metrics['positive_rate']:.1%}"
    )

    print(
        f"\n{metrics['warning']}\n"
    )

    header = (
        f"{'model':<20}"
        f"{'CV AUC':>9}"
        f"{'accuracy':>10}"
        f"{'precision':>10}"
        f"{'recall':>8}"
        f"{'F1':>7}"
        f"{'AUC':>7}"
    )

    print(
        header + "\n" + "-" * len(header)
    )

    for name, result in metrics["models"].items():
        test = result["test"]

        star = (
            " *"
            if name == metrics["selected_model"]
            else ""
        )

        print(
            f"{name:<20}"
            f"{result['cv_roc_auc_mean']:>9.3f}"
            f"{test['accuracy']:>10.3f}"
            f"{test['precision']:>10.3f}"
            f"{test['recall']:>8.3f}"
            f"{test['f1']:>7.3f}"
            f"{test['roc_auc']:>7.3f}"
            f"{star}"
        )

    baseline = metrics["baseline"]

    print(
        f"{'baseline rule':<20}"
        f"{'':>9}"
        f"{baseline['accuracy']:>10.3f}"
        f"{baseline['precision']:>10.3f}"
        f"{baseline['recall']:>8.3f}"
        f"{baseline['f1']:>7.3f}"
        f"{baseline['roc_auc']:>7.3f}   "
        f"({baseline['rule']})"
    )

    print(
        f"\n* selected: {metrics['selected_model']}  "
        f"({metrics['selection_rule']})"
    )


# ============================================================
# Command-Line Interface
# ============================================================

def main() -> None:
    from app.db import session as db_session
    from app.ml import collector, synthetic

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--source",
        choices=[
            "synthetic",
            "real",
            "mixed",
        ],
        default="synthetic",
    )

    parser.add_argument(
        "--rows",
        type=int,
        default=get_settings().risk_synthetic_rows,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    parser.add_argument(
        "--no-save",
        action="store_true",
    )

    parser.add_argument(
        "--export-real",
        metavar="CSV",
        help="export the real training rows and exit",
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # Export real session data
    # --------------------------------------------------------

    if args.export_real:
        with db_session.SessionLocal() as db:
            rows = collector.extract_rows(db)

        collector.write_csv(
            rows,
            args.export_real,
        )

        print(
            f"Exported {len(rows)} real rows "
            f"({sum(r['label'] for r in rows)} "
            f"with an intervention) to {args.export_real}"
        )

        return

    # --------------------------------------------------------
    # Prepare training data
    # --------------------------------------------------------

    groups = None

    if args.source == "synthetic":
        frame = synthetic.generate(
            args.rows,
            args.seed,
        )

    else:
        with db_session.SessionLocal() as db:
            real_rows = collector.extract_rows(db)

        collector.check_enough_real_data(
            real_rows
        )

        real = pd.DataFrame(
            real_rows
        )

        frame = real[
            FEATURE_NAMES + ["label"]
        ]

        groups = real[
            "session_id"
        ].to_numpy()

        if args.source == "mixed":
            fake = synthetic.generate(
                min(
                    args.rows,
                    2 * len(real),
                ),
                args.seed,
            )

            frame = pd.concat(
                [
                    frame,
                    fake,
                ],
                ignore_index=True,
            )

            groups = np.concatenate(
                [
                    groups,
                    np.array(
                        [
                            f"synthetic-{i}"
                            for i in range(len(fake))
                        ]
                    ),
                ]
            )

    # --------------------------------------------------------
    # Train and evaluate
    # --------------------------------------------------------

    artifact, metrics = train_models(
        frame,
        args.source,
        args.seed,
        groups,
    )

    _print_report(
        metrics
    )

    if not args.no_save:
        save_artifact(
            artifact,
            metrics,
        )

        print(
            f"\nSaved model: {artifact_path()}"
            f"\nSaved metrics: {metrics_path()}"
        )


if __name__ == "__main__":
    main()