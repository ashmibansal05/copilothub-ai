"""SYNTHETIC training data for the intervention predictor.

READ THIS: there are no real sessions yet, so this module INVENTS a dataset. The labels are
drawn from the formula below, whose coefficients are ASSUMPTIONS written by the project
author (for example "low confidence makes a human intervention more likely"). A model
trained on this data learns those assumptions back. High scores on it say NOTHING about how
well the model predicts what real people will do. Real data is collected by
app/ml/collector.py and used with `python -m app.ml.train --source real`."""

import numpy as np
import pandas as pd

from app.ml.features import FEATURE_NAMES

ASSUMED_LOGIT = {
    "intercept": -3.0,
    "low_confidence": 3.0,  # per unit of (1 - agent_confidence)
    "low_min_confidence": 0.8,  # per unit of (1 - min_confidence_so_far)
    "tool_failures_this_step": 0.45,
    "tool_failures_so_far": 0.2,
    "retries_so_far": 0.25,
    "open_conflict": 1.4,  # if any conflict is open
    "source_rejection_rate": 1.6,
    "retrieval_uncertainty": 1.2,  # per unit above 0.5, only when documents were retrieved
    "human_corrections_so_far": 0.35,
    "task_complexity_cues": 0.05,
    "task_length_words": 0.004,
}


def generate(n: int = 3000, seed: int = 42, label_noise: float = 0.06) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    words = np.clip(rng.lognormal(2.9, 0.5, n), 5, 150).round()
    cues = rng.poisson(2.5, n)
    plan_steps = rng.integers(3, 9, n)
    step_number = (rng.random(n) * plan_steps).astype(int) + 1
    confidence = np.clip(rng.beta(5, 2, n) - 0.02 * cues + rng.normal(0, 0.05, n), 0.02, 0.99)
    min_confidence = np.clip(confidence - np.abs(rng.normal(0, 0.12, n)), 0.0, 1.0)
    failures_so_far = rng.poisson(0.2 + 0.1 * step_number)
    failures_this = np.minimum(failures_so_far, rng.poisson(0.15, n))
    retries = rng.poisson(0.3, n)
    sources_used = rng.poisson(2.0 * step_number)
    rejection = np.where(sources_used == 0, 0.0, rng.beta(1, 6, n))
    has_retrieval = (rng.random(n) < 0.6).astype(float)
    uncertainty = np.where(has_retrieval == 1, np.clip(rng.normal(0.5, 0.2, n), 0, 1), 0.5)
    open_conflicts = rng.poisson(0.1, n)
    corrections = rng.poisson(0.4, n)
    interventions = corrections + rng.poisson(0.3, n)
    constraints = rng.poisson(0.8, n)

    c = ASSUMED_LOGIT
    logit = (
        c["intercept"]
        + c["low_confidence"] * (1 - confidence)
        + c["low_min_confidence"] * (1 - min_confidence)
        + c["tool_failures_this_step"] * failures_this
        + c["tool_failures_so_far"] * failures_so_far
        + c["retries_so_far"] * retries
        + c["open_conflict"] * (open_conflicts > 0)
        + c["source_rejection_rate"] * rejection
        + c["retrieval_uncertainty"] * (uncertainty - 0.5) * has_retrieval
        + c["human_corrections_so_far"] * corrections
        + c["task_complexity_cues"] * cues
        + c["task_length_words"] * words
    )
    probability = 1.0 / (1.0 + np.exp(-logit))
    label = rng.random(n) < probability
    flip = rng.random(n) < label_noise  # some noise so it is not trivially separable
    label = np.logical_xor(label, flip).astype(int)

    frame = pd.DataFrame({
        "task_length_words": words, "task_complexity_cues": cues.astype(float),
        "plan_steps": plan_steps.astype(float), "step_number": step_number.astype(float),
        "progress_fraction": step_number / plan_steps, "agent_confidence": confidence,
        "min_confidence_so_far": min_confidence, "tool_failures_so_far": failures_so_far.astype(float),
        "tool_failures_this_step": failures_this.astype(float), "retries_so_far": retries.astype(float),
        "sources_used_so_far": sources_used.astype(float), "source_rejection_rate": rejection,
        "retrieval_uncertainty": uncertainty, "has_retrieval": has_retrieval,
        "open_conflicts": open_conflicts.astype(float), "human_corrections_so_far": corrections.astype(float),
        "human_interventions_so_far": interventions.astype(float), "active_constraints": constraints.astype(float),
    })[FEATURE_NAMES]
    frame["label"] = label
    return frame