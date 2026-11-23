import numpy as np
import pytest

from app.core.config import get_settings
from app.nlp import classifier as clf_module
from app.nlp.classifier import IntentClassifier, train
from app.nlp.dataset import INTENTS, TEST_EXAMPLES, TRAIN_EXAMPLES
from app.nlp.policy import decide
from app.rag.embeddings import HashingEmbedder


@pytest.fixture(scope="module")
def trained():
    return train(TRAIN_EXAMPLES, HashingEmbedder(), TEST_EXAMPLES)


def test_training_produces_real_metrics(trained):
    classifier, metrics = trained
    assert set(metrics["classes"]) == set(INTENTS) and metrics["n_train"] == len(TRAIN_EXAMPLES)
    assert metrics["n_test"] == len(TEST_EXAMPLES) and metrics["embedder"] == "hashing-lexical"
    assert 0.0 <= metrics["held_out"]["accuracy"] <= 1.0 and 0.0 <= metrics["cross_validation"]["accuracy"] <= 1.0
    assert metrics["train_accuracy"] >= 0.85  # it must at least fit its own training data
    assert "synthetic" in metrics["dataset"]
    assert {"text", "expected", "predicted"} <= set(metrics["held_out"]["mistakes"][0]) or metrics["held_out"]["accuracy"] == 1.0


def test_predictions_are_probability_distributions(trained):
    classifier, _ = trained
    predictions = classifier.predict(["Pause the research for now.", "Thanks!"], HashingEmbedder())
    for p in predictions:
        assert p.intent in INTENTS and 0.0 <= p.confidence <= 1.0
        assert sum(p.probabilities.values()) == pytest.approx(1.0, abs=1e-6)
        assert p.confidence == max(p.probabilities.values())


def test_save_and_load_round_trip(trained, tmp_path, monkeypatch):
    classifier, metrics = trained
    monkeypatch.setattr(clf_module, "model_dir", lambda: tmp_path)
    clf_module.save_artifact(classifier, metrics)
    assert (tmp_path / "intent_classifier.joblib").exists() and (tmp_path / "intent_metrics.json").exists()
    loaded = clf_module.load_artifact()
    embedder = HashingEmbedder()
    texts = ["Stop using Wikipedia.", "Looks good, approved."]
    assert [p.intent for p in loaded.predict(texts, embedder)] == [p.intent for p in classifier.predict(texts, embedder)]


def test_get_classifier_trains_once_then_reuses_and_retrains_for_a_new_embedder(tmp_path, monkeypatch):
    monkeypatch.setattr(clf_module, "model_dir", lambda: tmp_path)
    monkeypatch.setattr(clf_module, "_cached", None)
    first = clf_module.get_classifier()
    assert (tmp_path / "intent_classifier.joblib").exists() and first.embedder_name == "hashing-lexical"
    assert clf_module.get_classifier() is first  # cached

    monkeypatch.setattr(clf_module, "_cached", None)
    assert clf_module.get_classifier().embedder_name == "hashing-lexical"  # loaded from disk

    class OtherEmbedder(HashingEmbedder):
        name = "other-embedder"

    monkeypatch.setattr(clf_module, "get_embedder", lambda: OtherEmbedder())
    retrained = clf_module.get_classifier()
    assert retrained is not first and retrained.embedder_name == "other-embedder"


def test_without_a_model_and_auto_train_off_it_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(clf_module, "model_dir", lambda: tmp_path)
    monkeypatch.setattr(clf_module, "_cached", None)
    monkeypatch.setattr(get_settings(), "nlp_auto_train", False)
    with pytest.raises(RuntimeError, match="python -m app.nlp.train"):
        clf_module.get_classifier()


def test_policy():
    # high-impact actions are never automatic, however confident the model is
    for intent in ["APPROVE", "REJECT", "MODIFY_TASK", "REMOVE_CONSTRAINT"]:
        assert not decide(intent, 0.999, True).auto and "confirm" in decide(intent, 0.999, True).reason
    assert decide("REJECT_SOURCE", 0.9, True).auto
    low = decide("REJECT_SOURCE", 0.6, True)
    assert not low.auto and "60%" in low.reason
    assert not decide("REJECT_SOURCE", 0.99, False).auto  # missing detail
    assert not decide("PAUSE", 0.99, True, auto_enabled=False).auto
    assert decide("COMMENT", 0.45, True).auto and not decide("COMMENT", 0.3, True).auto
    assert decide("QUESTION", 0.45, True).auto