"""End-to-end test of the demonstration flow from the project brief (steps 1-19)."""
import csv
import io
import time

import pytest

from app.core.config import get_settings
from app.nlp import classifier as clf_module
from app.nlp.classifier import Prediction
from helpers import create_session, join, make_user, read_until

pytestmark = pytest.mark.usefixtures("ml_sandbox", "tools_on")

SENTENCES = {
    "Do not use Wikipedia.": ("REJECT_SOURCE", 0.95),
    "Prefer official cloud provider documentation.": ("ADD_CONSTRAINT", 0.92),
}


class FakeClassifier:
    """Deterministic classifier: this test is about the whole flow, not about model quality."""

    def predict(self, texts, embedder):
        out = []
        for text in texts:
            intent, confidence = SENTENCES.get(text, ("COMMENT", 0.9))
            out.append(Prediction(intent, confidence, {intent: confidence}))
        return out


def wait_for_state(client, headers, sid, predicate, timeout=20.0):
    deadline = time.time() + timeout
    state = {}
    while time.time() < deadline:
        state = client.get(f"/sessions/{sid}/state", headers=headers).json()
        if predicate(state):
            return state
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting; last status was {state.get('status')}")


def test_the_full_demonstration_flow(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_require_final_approval", True)
    monkeypatch.setattr(settings, "agent_generate_final_report", True)
    monkeypatch.setattr(settings, "risk_prediction_enabled", True)
    monkeypatch.setattr(clf_module, "get_classifier", lambda: FakeClassifier())

    # Steps 1-4: users log in, alice creates the session, bob/dave join as editors, carol as viewer
    alice, alice_token = make_user(client, "alice")
    bob, _ = make_user(client, "bob")
    carol, carol_token = make_user(client, "carol")
    dave, _ = make_user(client, "dave")
    session = create_session(
        client, alice, name="Cloud platform research",
        task="Prepare a report comparing AWS, Microsoft Azure and Google Cloud for a small startup",
    )
    sid = session["id"]
    assert session["my_role"] == "OWNER" and len(session["editor_code"]) == 8 and len(session["viewer_code"]) == 8
    assert join(client, bob, session["editor_code"]).json()["my_role"] == "EDITOR"
    assert join(client, dave, session["editor_code"]).json()["my_role"] == "EDITOR"
    assert join(client, carol, session["viewer_code"]).json()["my_role"] == "VIEWER"

    # Steps 8-13: free text becomes structured constraints (a viewer cannot instruct the agent)
    said = client.post(f"/sessions/{sid}/instructions", json={"text": "Do not use Wikipedia."}, headers=bob).json()
    assert said["applied"] and said["intent"] == "REJECT_SOURCE" and said["proposal"]["target"] == "Wikipedia"
    assert client.post(f"/sessions/{sid}/instructions", json={"text": "Do not use Wikipedia."}, headers=carol).status_code == 403
    said = client.post(f"/sessions/{sid}/instructions", json={"text": "Prefer official cloud provider documentation."}, headers=dave).json()
    assert said["applied"] and said["proposal"]["action"] == "PREFER_SOURCE"
    constraints = client.get(f"/sessions/{sid}/constraints", headers=alice).json()
    assert {(c["action"], c["target"]) for c in constraints} == {
        ("EXCLUDE_SOURCE", "Wikipedia"), ("PREFER_SOURCE", "official documentation")}

    # Step 14: two editors give contradicting instructions; the system must not pick silently
    allow = client.post(f"/sessions/{sid}/constraints", json={"action": "INCLUDE_SOURCE", "target": "Wikipedia", "priority": "HIGH"}, headers=dave)
    assert allow.status_code == 201
    (conflict,) = client.get(f"/sessions/{sid}/conflicts?status=OPEN", headers=alice).json()
    assert conflict["requires_resolution"] is True and conflict["constraint_a"]["action"] == "EXCLUDE_SOURCE"

    ws_url = f"/ws/sessions/{sid}"
    with client.websocket_connect(ws_url) as ws_alice, client.websocket_connect(ws_url) as ws_carol:
        for ws, token in ((ws_alice, alice_token), (ws_carol, carol_token)):
            ws.send_json({"type": "AUTH", "token": token})
            assert ws.receive_json()["type"] == "CONNECTED"

        # Steps 5-6: the agent starts; both users see it live
        assert client.post(f"/sessions/{sid}/start", headers=alice).status_code == 200
        waiting = wait_for_state(
            client, alice, sid, lambda s: s["status"] == "WAITING_FOR_APPROVAL" and s["pending_approval"] is None)
        assert len(waiting["open_conflicts"]) == 1  # the agent is waiting for a human, not guessing

        # Step 15: only the owner can resolve it
        resolve = f"/sessions/{sid}/conflicts/{conflict['id']}/resolve"
        keep = {"winner_constraint_id": conflict["constraint_a"]["constraint_id"]}
        assert client.post(resolve, json=keep, headers=bob).status_code == 403
        assert client.post(resolve, json=keep, headers=alice).status_code == 200

        # Steps 7, 11, 13, 16: the agent researches while respecting the rules, then asks for approval
        seen = read_until(ws_alice, {"APPROVAL_REQUESTED", "FAILED"})
        assert seen[-1] == "APPROVAL_REQUESTED"
        assert {"STEP_STARTED", "TOOL_COMPLETED", "CONFLICT_RESOLVED", "RISK_UPDATED"} <= set(seen)
        assert read_until(ws_carol, {"APPROVAL_REQUESTED", "FAILED"})[-1] == "APPROVAL_REQUESTED"  # the viewer saw it too

        # Step 17: the viewer cannot approve; the owner can
        assert client.post(f"/sessions/{sid}/interventions", json={"type": "APPROVE"}, headers=carol).status_code == 403
        assert client.post(f"/sessions/{sid}/interventions", json={"type": "APPROVE"}, headers=alice).status_code == 201

        # Step 18: the agent finishes and generates the final report
        seen = read_until(ws_alice, {"COMPLETED", "FAILED"})
        assert seen[-1] == "COMPLETED" and "REPORT_SAVED" in seen

    # The constraints were honoured all the way through
    state = client.get(f"/sessions/{sid}/state", headers=alice).json()
    assert state["status"] == "COMPLETED" and state["progress"] == 100 and state["open_conflicts"] == []
    events = client.get(f"/sessions/{sid}/events?limit=500", headers=alice).json()
    calls = [e["payload"] for e in events if e["type"] == "TOOL_COMPLETED"]
    used = [s for p in calls for s in p["sources"]]
    rejected = [s for p in calls for s in p["rejected_sources"]]
    assert used and all(s["publisher"] != "Wikipedia" for s in used)
    assert any(s["publisher"] == "Wikipedia" and s["rejected_by"] == "Wikipedia" for s in rejected)
    assert any(s.get("preferred") for s in used)  # official documentation ranked first

    # The report reflects the human input (viewers may read it)
    report = client.get(f"/sessions/{sid}/report", headers=carol).json()
    assert [s["title"] for s in report["sections"]][:2] == ["Executive Summary", "Research Objective"] and len(report["sections"]) == 10
    body = {s["key"]: s["body"] for s in report["sections"]}
    used_part, _, rejected_part = body["sources"].partition("Sources rejected (not used):")
    assert "Wikipedia" in rejected_part and "Wikipedia" not in used_part
    assert "@bob rejected a source" in body["human_decisions"] and "@alice approved" in body["human_decisions"]
    assert "keep a" in body["human_decisions"]

    # Step 19: the analytics dashboard shows it all
    analytics = client.get(f"/sessions/{sid}/analytics", headers=alice).json()
    assert analytics["status"] == "COMPLETED" and analytics["steps_completed"] == 7
    assert analytics["interventions_total"] >= 5 and analytics["conflicts_total"] == 1 and analytics["conflicts_resolved"] == 1
    assert analytics["approvals_approved"] == 1 and analytics["sources_rejected"] > 0 and analytics["risk"]["n"] >= 1
    overview = client.get("/analytics/overview", headers=alice).json()
    assert overview["sessions_completed"] == 1 and overview["success_rate"] == 1.0

    deadline, rows = time.time() + 5, []
    while time.time() < deadline and not rows:  # the end-of-session snapshot is written just after COMPLETED
        rows = list(csv.DictReader(io.StringIO(client.get("/analytics/export.csv", headers=alice).text)))
        time.sleep(0.1)
    assert rows and rows[0]["status"] == "COMPLETED" and rows[0]["session_id"] == sid