import pandas as pd
import pytest
from sqlalchemy import select

from app.ml.collector import InsufficientDataError, check_enough_real_data, extract_rows, write_csv
from app.ml.features import FEATURE_NAMES, build_step_features, task_stats
from app.models.session import AgentSession, AgentStatus
from helpers import make_running_session
from seed import TASK, at, seed_history


def check(actual, expected):
    assert set(actual) == set(FEATURE_NAMES)
    for key, value in expected.items():
        assert actual[key] == pytest.approx(value), key


def test_task_stats():
    assert task_stats(TASK) == (10, 5)  # compare, pricing, one comma, one "and", the number 3
    assert task_stats("Summarise the document") == (3, 0)


def test_features_describe_the_past_only(client):
    sid = make_running_session(client)
    seed_history(client, sid)
    with client.session_factory() as db:
        f1 = build_step_features(db, sid, 1, at(2))
        f2 = build_step_features(db, sid, 2, at(4))
        f3 = build_step_features(db, sid, 3, at(6))

    check(f1, dict(task_length_words=10, task_complexity_cues=5, plan_steps=3, step_number=1, progress_fraction=1 / 3,
                   agent_confidence=0.9, min_confidence_so_far=0.9, tool_failures_so_far=0, tool_failures_this_step=0,
                   retries_so_far=0, sources_used_so_far=0, source_rejection_rate=0, retrieval_uncertainty=0.5,
                   has_retrieval=0, open_conflicts=0, human_corrections_so_far=0, human_interventions_so_far=0,
                   active_constraints=2))
    check(f2, dict(step_number=2, progress_fraction=2 / 3, agent_confidence=0.5, min_confidence_so_far=0.5,
                   tool_failures_so_far=2,  # one ERROR tool call + one failed ACT attempt
                   tool_failures_this_step=2, retries_so_far=1, sources_used_so_far=2,
                   source_rejection_rate=1 / 3, retrieval_uncertainty=0.3, has_retrieval=1, open_conflicts=0,
                   human_corrections_so_far=0,  # the CORRECT at 4.5 has not happened yet
                   human_interventions_so_far=0,  # comments never count
                   active_constraints=2))
    check(f3, dict(step_number=3, progress_fraction=1.0, agent_confidence=0.8, min_confidence_so_far=0.5,
                   tool_failures_so_far=2, tool_failures_this_step=0, retries_so_far=1, sources_used_so_far=2,
                   has_retrieval=0, retrieval_uncertainty=0.5,
                   open_conflicts=1,  # first conflict resolved at 5.5, second still open
                   human_corrections_so_far=1, human_interventions_so_far=1,
                   active_constraints=1))  # c1 removed at 5, c3 only exists from 6.5


def test_labels_mark_steps_followed_by_a_corrective_intervention(client):
    sid = make_running_session(client)
    seed_history(client, sid)
    with client.session_factory() as db:
        rows = extract_rows(db, [sid])
    assert [(r["step_index"], r["label"]) for r in rows] == [(1, 0), (2, 1), (3, 0)]
    assert all(r["session_id"] == str(sid) and set(FEATURE_NAMES) <= set(r) for r in rows)


def test_unfinished_sessions_are_not_training_data(client):
    sid = make_running_session(client)
    seed_history(client, sid)
    with client.session_factory() as db:
        db.get(AgentSession, sid).status = AgentStatus.RUNNING
        db.commit()
        assert extract_rows(db) == []
        assert len(extract_rows(db, finished_only=False)) == 3


def test_csv_export_round_trips(client, tmp_path):
    sid = make_running_session(client)
    seed_history(client, sid)
    with client.session_factory() as db:
        rows = extract_rows(db, [sid])
    write_csv(rows, tmp_path / "real.csv")
    frame = pd.read_csv(tmp_path / "real.csv")
    assert list(frame["label"]) == [0, 1, 0] and set(FEATURE_NAMES) <= set(frame.columns)


def test_too_little_real_data_is_refused():
    with pytest.raises(InsufficientDataError, match="Not enough real data"):
        check_enough_real_data([{"label": 1}, {"label": 0}] * 5)
    check_enough_real_data([{"label": i % 2} for i in range(400)])  # enough: no error