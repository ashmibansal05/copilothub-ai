import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from app.core.config import get_settings
from app.nlp.dataset import TEST_EXAMPLES, TRAIN_EXAMPLES
from app.rag.embeddings import Embedder, get_embedder

logger = logging.getLogger("copilothub.nlp")


@dataclass
class Prediction:
    intent: str
    confidence: float  # the model's predicted probability for `intent` (not guaranteed to be calibrated)
    probabilities: dict[str, float] = field(default_factory=dict)


class IntentClassifier:
    """Sentence embedding -> Logistic Regression -> intent."""

    def __init__(self, model: LogisticRegression, embedder_name: str, meta: dict | None = None) -> None:
        self.model = model
        self.classes: list[str] = [str(c) for c in model.classes_]
        self.embedder_name = embedder_name
        self.meta = meta or {}

    def predict(self, texts: list[str], embedder: Embedder) -> list[Prediction]:
        probabilities = self.model.predict_proba(embedder.embed(texts))
        out = []
        for row in probabilities:
            by_class = {c: float(p) for c, p in zip(self.classes, row)}
            intent = max(by_class, key=by_class.get)
            out.append(Prediction(intent=intent, confidence=by_class[intent], probabilities=by_class))
        return out


def _new_model() -> LogisticRegression:
    return LogisticRegression(C=20.0, max_iter=3000, class_weight="balanced")


def train(
    examples: list[tuple[str, str]],
    embedder: Embedder,
    test_examples: list[tuple[str, str]] | None = None,
    folds: int = 5,
) -> tuple[IntentClassifier, dict]:
    """Fit the classifier and EVALUATE it honestly. Every number in the returned metrics
    is computed here from the data it was given; nothing is hard-coded."""
    texts = [t for t, _ in examples]
    labels = [label for _, label in examples]
    vectors = embedder.embed(texts)

    metrics: dict = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "embedder": embedder.name,
        "n_train": len(examples),
        "n_test": len(test_examples or []),
        "classes": sorted(set(labels)),
        "dataset": "synthetic, hand-written (see app/nlp/dataset.py); optimistic compared with real users",
    }

    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    splits = min(folds, min(counts.values()))
    if splits >= 2:
        predicted = cross_val_predict(
            _new_model(), vectors, labels, cv=StratifiedKFold(splits, shuffle=True, random_state=42)
        )
        metrics["cross_validation"] = {
            "folds": splits,
            "accuracy": float(accuracy_score(labels, predicted)),
            "macro_f1": float(f1_score(labels, predicted, average="macro")),
            "per_class": classification_report(labels, predicted, output_dict=True, zero_division=0),
        }

    model = _new_model().fit(vectors, labels)
    metrics["train_accuracy"] = float(accuracy_score(labels, model.predict(vectors)))

    if test_examples:
        test_vectors = embedder.embed([t for t, _ in test_examples])
        truth = [label for _, label in test_examples]
        predicted = model.predict(test_vectors)
        metrics["held_out"] = {
            "accuracy": float(accuracy_score(truth, predicted)),
            "macro_f1": float(f1_score(truth, predicted, average="macro")),
            "mistakes": [
                {"text": t, "expected": e, "predicted": str(p)}
                for (t, e), p in zip(test_examples, predicted) if e != p
            ],
        }
    return IntentClassifier(model, embedder.name, meta=metrics), metrics


# ------------------------------------------------------------------ persistence
def model_dir() -> Path:
    return get_settings().data_path / "ml"


def artifact_path() -> Path:
    return model_dir() / "intent_classifier.joblib"


def metrics_path() -> Path:
    return model_dir() / "intent_metrics.json"


def save_artifact(classifier: IntentClassifier, metrics: dict) -> None:
    model_dir().mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": classifier.model, "embedder": classifier.embedder_name, "meta": metrics}, artifact_path())
    metrics_path().write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def load_artifact() -> IntentClassifier | None:
    """Only ever loads the file this application wrote itself into its own data folder
    (joblib/pickle files must never come from an untrusted source)."""
    path = artifact_path()
    if not path.exists():
        return None
    try:
        blob = joblib.load(path)
        return IntentClassifier(blob["model"], blob["embedder"], blob.get("meta"))
    except Exception:
        logger.exception("Could not load the intent classifier at %s", path)
        return None


_lock = threading.Lock()
_cached: IntentClassifier | None = None


def get_classifier() -> IntentClassifier:
    """The classifier for the current embedding backend. Loads the saved model, or trains
    one from the built-in dataset on first use (a few seconds)."""
    global _cached
    embedder = get_embedder()
    with _lock:
        if _cached is not None and _cached.embedder_name == embedder.name:
            return _cached
        loaded = load_artifact()
        if loaded is not None and loaded.embedder_name == embedder.name:
            _cached = loaded
            return loaded
        if not get_settings().nlp_auto_train:
            raise RuntimeError("No trained intent classifier. Run: python -m app.nlp.train")
        logger.info("Training the intent classifier with %s ...", embedder.name)
        classifier, metrics = train(TRAIN_EXAMPLES, embedder, TEST_EXAMPLES)
        save_artifact(classifier, metrics)
        _cached = classifier
        return classifier