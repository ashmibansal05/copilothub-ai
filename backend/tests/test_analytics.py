import csv
import io

import pytest
from sqlalchemy import select

from app.models.analytics_record import AnalyticsRecord
from app.models.session import AgentSession, AgentStatus
from app.services import analytics_service
from helpers import ScriptedBrain, create_session, make_running_session, make_user, read_until
from seed import seed_history


def seeded(client):
    sid = make_running_session(client)
    seed_history(client, sid, with_predictions=True)
    headers, _ = make_user(client, "owner")
    return sid, headers


def test_session_analytics_match_the_hand_computed_numbers(client):
    sid, headers = seeded(client)
    a = client.get(f"/sessions/{sid}/analytics", headers=headers).json()

    assert a["status"] == "COMPLETED" and a["duration_seconds"] == pytest.approx(420)
    assert (a["steps_planned"], a["steps_completed"]) == (3, 3)
    assert [p["confidence"] for p in a["confidence_series"]] == [0.9, 0.5, 0.8]
    assert a["avg_confidence"] == pytest.approx(0.7333, abs=1e-3) and a["final_confidence"] == 0.8 and a["min_confidence"] == 0.5

    assert (a["interventions_total"], a["comments"], a["corrective"]) == (2, 1, 1)  # CORRECT + APPROVE; one comment
    assert a["interventions_by_type"] == {"COMMENT": 1, "CORRECT": 1, "APPROVE": 1} and a["interventions_by_user"] == {"owner": 2}

    assert (a["tool_calls"], a["tool_failures"]) == (3, 1) and a["tool_failure_rate"] == pytest.approx(1 / 3)
    assert {t["tool"]: (t["calls"], t["failures"]) for t in a["tools"]} == {"calculate": (1, 0), "search_web": (1, 0), "retrieve_documents": (1, 1)}
    assert a["failed_attempts"] == 1 and a["recovered"] is True

    assert (a["approvals_requested"], a["approvals_approved"], a["approvals_rejected"]) == (2, 1, 1) and a["approval_rate"] == 0.5
    assert (a["conflicts_total"], a["conflicts_open"], a["conflicts_resolved"]) == (2, 1, 1)
    assert (a["sources_used"], a["sources_rejected"]) == (2, 1) and a["source_rejection_rate"] == pytest.approx(1 / 3)
    assert a["sources_by_origin"] == {"DOCUMENT": 2}

    risk = a["risk"]  # predictions .2/.8/.3 against outcomes 0/1/0
    assert (risk["n"], risk["observed_n"]) == (3, 3) and risk["mean"] == pytest.approx(0.4333, abs=1e-3)
    assert (risk["max"], risk["last"]) == (0.8, 0.3)
    assert risk["mean_when_intervened"] == pytest.approx(0.8) and risk["mean_when_not"] == pytest.approx(0.25)


def test_analytics_are_only_visible_to_members(client):
    sid, _ = seeded(client)
    stranger, _ = make_user(client, "stranger")
    assert client.get(f"/sessions/{sid}/analytics", headers=stranger).status_code == 404
    assert client.get(f"/sessions/{sid}/analytics").status_code == 401


def test_overview_aggregates_only_my_sessions(client):
    sid, headers = seeded(client)
    other_headers, _ = make_user(client, "someone")
    create_session(client, other_headers)  # not mine: must not be counted
    mine = create_session(client, headers, name="Still running")  # CREATED, no data
    o = client.get("/analytics/overview", headers=headers).json()

    assert o["sessions_total"] == 2 and o["sessions_completed"] == 1 and o["sessions_active"] == 1
    assert o["success_rate"] == 1.0 and o["avg_duration_seconds"] == pytest.approx(420)
    assert (o["interventions_total"], o["interventions_corrective"]) == (2, 1)
    assert o["interventions_by_type"]["CORRECT"] == 1 and o["tool_failures"] == 1 and o["tool_failure_rate"] == pytest.approx(1 / 3)
    assert o["approval_rate"] == 0.5 and o["conflicts_total"] == 2 and o["source_rejection_rate"] == pytest.approx(1 / 3)
    assert sum(b["count"] for b in o["confidence_histogram"]) == 3
    assert o["prediction"]["mean_when_intervened"] == pytest.approx(0.8)
    assert {r["id"] for r in o["recent_sessions"]} == {str(sid), mine["id"]}

    research = o["research"]
    assert research["task_completion_rate"] == 1.0 and research["agent_recovery_rate"] == 1.0
    assert research["human_correction_rate"] == pytest.approx(1 / 3)
    assert research["groups"][0]["sessions"] == 1 and research["groups"][1]["sessions"] == 0
    assert "NOT a controlled experiment" in research["notes"]


def test_overview_of_nothing_is_empty_not_an_error(client):
    headers, _ = make_user(client, "newcomer")
    o = client.get("/analytics/overview", headers=headers).json()
    assert o["sessions_total"] == 0 and o["success_rate"] is None and o["avg_duration_seconds"] is None
    assert o["recent_sessions"] == [] and o["research"]["task_completion_rate"] is None


def test_session_snapshots_are_idempotent_and_exportable(client):
    sid, headers = seeded(client)
    analytics_service.record_session_end(sid)
    analytics_service.record_session_end(sid)
    with client.session_factory() as db:
        records = db.scalars(select(AnalyticsRecord).where(AnalyticsRecord.session_id == sid)).all()
        assert len(records) == 1
        r = records[0]
        assert (r.status, r.steps_completed, r.interventions, r.corrective, r.tool_calls, r.tool_failures) == ("COMPLETED", 3, 2, 1, 3, 1)
        assert r.metrics["tool_calls"] == 3

    other, _ = make_user(client, "someone")
    assert client.get("/analytics/export.csv").status_code == 401
    mine = client.get("/analytics/export.csv", headers=headers)
    assert mine.headers["content-type"].startswith("text/csv") and "attachment" in mine.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(mine.text)))
    assert len(rows) == 1 and rows[0]["session_id"] == str(sid) and rows[0]["corrective"] == "1"
    assert list(csv.DictReader(io.StringIO(client.get("/analytics/export.csv", headers=other).text))) == []


def test_a_finished_run_writes_its_own_snapshot(client, set_brain):
    set_brain(ScriptedBrain(steps=2))
    headers, token = make_user(client, "owner")
    s = create_session(client, headers)
    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": token})
        ws.receive_json()
        client.post(f"/sessions/{s['id']}/start", headers=headers)
        assert read_until(ws, {"COMPLETED", "FAILED"})[-1] == "COMPLETED"
    import time
    import uuid

    deadline = time.time() + 5
    while time.time() < deadline:
        with client.session_factory() as db:
            record = db.scalar(select(AnalyticsRecord).where(AnalyticsRecord.session_id == uuid.UUID(s["id"])))
        if record:
            break
        time.sleep(0.1)
    assert record is not None and record.status == "COMPLETED" and record.steps_completed == 2


def test_stopping_a_session_writes_a_snapshot_too(client, disable_agent):
    headers, _ = make_user(client, "owner")
    s = create_session(client, headers)
    client.post(f"/sessions/{s['id']}/start", headers=headers)
    client.post(f"/sessions/{s['id']}/stop", headers=headers)
    rows = list(csv.DictReader(io.StringIO(client.get("/analytics/export.csv", headers=headers).text)))
    assert [r["status"] for r in rows] == ["CANCELLED"]