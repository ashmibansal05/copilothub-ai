"""Train (or retrain) the intent classifier and print an honest evaluation.

    python -m app.nlp.train                    # built-in synthetic dataset
    python -m app.nlp.train --include-feedback # + confirmed real samples from the database
    python -m app.nlp.train --no-save          # evaluate only
"""
import argparse
import json

from sqlalchemy import select

from app.db import session as db_session
from app.models.intent_sample import IntentSample
from app.nlp import classifier
from app.nlp.dataset import INTENTS, TEST_EXAMPLES, TRAIN_EXAMPLES
from app.rag.embeddings import get_embedder


def feedback_examples() -> list[tuple[str, str]]:
    """Real sentences whose final outcome is known (a human applied or confirmed them)."""
    out = []
    with db_session.SessionLocal() as db:
        rows = db.scalars(select(IntentSample).where(IntentSample.final_type.is_not(None))).all()
    for row in rows:
        label = "QUESTION" if row.predicted_intent == "QUESTION" and row.final_type == "COMMENT" else row.final_type
        if label in INTENTS:
            out.append((row.text, label))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--include-feedback", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    embedder = get_embedder()
    examples = list(TRAIN_EXAMPLES)
    if args.include_feedback:
        extra = feedback_examples()
        print(f"Adding {len(extra)} real, confirmed samples from the database")
        examples += extra

    print(f"Embedding backend: {embedder.name}")
    clf, metrics = classifier.train(examples, embedder, TEST_EXAMPLES)

    print(f"\nTraining examples: {metrics['n_train']}   held-out examples: {metrics['n_test']}")
    print(f"Training accuracy: {metrics['train_accuracy']:.3f}")
    cv = metrics.get("cross_validation")
    if cv:
        print(f"{cv['folds']}-fold cross-validation: accuracy {cv['accuracy']:.3f}, macro-F1 {cv['macro_f1']:.3f}")
    held = metrics.get("held_out")
    if held:
        print(f"Held-out set: accuracy {held['accuracy']:.3f}, macro-F1 {held['macro_f1']:.3f}")
        for m in held["mistakes"]:
            print(f"  wrong: {m['text']!r}  expected {m['expected']}, got {m['predicted']}")
    print("\nNote: the dataset is small and written by one person, so these scores are optimistic.")

    if args.no_save:
        print(json.dumps({k: v for k, v in metrics.items() if k != "cross_validation"}, indent=2)[:0])
    else:
        classifier.save_artifact(clf, metrics)
        print(f"\nSaved model:   {classifier.artifact_path()}\nSaved metrics: {classifier.metrics_path()}")


if __name__ == "__main__":
    main()