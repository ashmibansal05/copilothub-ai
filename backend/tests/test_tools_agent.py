import uuid
import pytest
from sqlalchemy import select

from app.agents.brain import ToolCall
from app.core.config import get_settings
from app.models.event import AgentEvent
from app.models.report import Report
from app.models.tool_execution import ToolExecution
from helpers import ScriptedToolBrain, create_session, make_user, read_until

pytestmark = pytest.mark.usefixtures("tools_on")


def run_session(client, set_brain, brain, before_start=None):
    set_brain(brain)
    headers, token = make_user(client, "owner")
    s = create_session(client, headers)
    sid = s["id"]
    if before_start:
        before_start(client, headers, sid)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.send_json({"type": "AUTH", "token": token})
        ws.receive_json()
        client.post(f"/sessions/{sid}/start", headers=headers)
        assert read_until(ws, {"COMPLETED", "FAILED"})[-1] == "COMPLETED"
    return sid, headers


def executions(client, sid):
    session_uuid = sid if isinstance(sid, uuid.UUID) else uuid.UUID(str(sid))

    with client.session_factory() as db:
        rows = db.scalars(
            select(ToolExecution)
            .where(ToolExecution.session_id == session_uuid)
            .order_by(ToolExecution.created_at)
        ).all()

        return [(r.tool_name, r.status, r.error) for r in rows]


def test_the_model_can_only_use_approved_tools_and_every_call_is_audited(client, set_brain):
    brain = ScriptedToolBrain([
        ToolCall("calculate", {"expression": "2+2"}),
        ToolCall("evil_shell", {"cmd": "rm -rf /"}),
        ToolCall("calculate", {"expression": "__import__('os').system('ls')"}),
    ], final="All done")
    sid, headers = run_session(client, set_brain, brain)

    rows = executions(client, sid)
    assert [(t, s) for t, s, _ in rows] == [("calculate", "SUCCESS"), ("evil_shell", "REJECTED"), ("calculate", "ERROR")]
    assert "Unknown or disabled tool" in rows[1][2]

    # the model is shown what happened, so it can recover
    final_view = brain.seen_observations[-1]
    assert [(t, ok) for t, ok, _ in final_view] == [("calculate", True), ("evil_shell", False), ("calculate", False)]
    assert "= 4" in final_view[0][2]

    events = client.get(f"/sessions/{sid}/events", headers=headers).json()
    completed = [e["payload"] for e in events if e["type"] == "TOOL_COMPLETED"]
    print("\n=== TOOL COMPLETED EVENTS ===")
    for event in completed:
        print(event)
    assert [(p["tool"], p["status"]) for p in completed] == [("calculate", "SUCCESS"), ("evil_shell", "REJECTED"), ("calculate", "ERROR")]
    assert completed[0]["arguments"] == {"expression": "2+2"}
    assert client.get(f"/sessions/{sid}/tools?status=REJECTED", headers=headers).json()[0]["tool_name"] == "evil_shell"
    texts = [e["payload"]["text"] for e in events if e["type"] == "AGENT_MESSAGE"]
    assert any("Step 1/1" in t and "All done" in t for t in texts)  # the final findings reach the humans


def test_tool_calls_per_step_are_capped_and_the_model_is_told_to_answer(client, set_brain, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_max_tool_calls_per_step", 2)
    brain = ScriptedToolBrain([ToolCall("calculate", {"expression": "1+1"})] * 10)
    sid, _ = run_session(client, set_brain, brain)
    assert len(executions(client, sid)) == 2  # never more than the limit
    assert brain.force_flags == [False, False, True]  # the third request forces a final answer


def test_a_run_wide_tool_budget_is_enforced(client, set_brain, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_max_tool_calls_per_step", 3)
    monkeypatch.setattr(settings, "agent_max_tool_calls_per_run", 4)
    brain = ScriptedToolBrain([ToolCall("calculate", {"expression": "1+1"})] * 10, steps=3)
    sid, _ = run_session(client, set_brain, brain)
    assert len(executions(client, sid)) == 4


def test_save_report_creates_a_draft_and_announces_it(client, set_brain):
    brain = ScriptedToolBrain([ToolCall("save_report", {"title": "Interim notes", "content": "These are the interim findings so far."})])
    sid, headers = run_session(client, set_brain, brain)
    reports = client.get(f"/sessions/{sid}/reports", headers=headers).json()
    assert [r["title"] for r in reports] == ["Interim notes"] and reports[0]["origin"] == "AGENT"
    events = client.get(f"/sessions/{sid}/events", headers=headers).json()
    assert "REPORT_SAVED" in {e["type"] for e in events}


def test_the_demo_agent_uses_real_tools_and_obeys_constraints(client):
    """The real MockBrain in tool mode: search_web (simulated provider) + retrieve_documents."""
    def reject_wikipedia(client, headers, sid):
        r = client.post(f"/sessions/{sid}/interventions", json={"type": "REJECT_SOURCE", "target": "Wikipedia"}, headers=headers)
        assert r.status_code == 201

    headers, token = make_user(client, "owner")
    s = create_session(client, headers)
    sid = s["id"]
    reject_wikipedia(client, headers, sid)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.send_json({"type": "AUTH", "token": token})
        ws.receive_json()
        client.post(f"/sessions/{sid}/start", headers=headers)
        assert read_until(ws, {"COMPLETED", "FAILED"})[-1] == "COMPLETED"

    rows = executions(client, sid)
    names = [t for t, _, _ in rows]
    assert names.count("search_web") == 5 and names.count("retrieve_documents") == 5 and names.count("compare_sources") == 1
    assert all(status == "SUCCESS" for _, status, _ in rows)

    events = client.get(f"/sessions/{sid}/events?limit=500", headers=headers).json()
    searches = [e["payload"] for e in events if e["type"] == "TOOL_COMPLETED" and e["payload"]["tool"] == "search_web"]
    assert all(p["simulated"] for p in searches)  # labelled as simulated
    assert all(s["publisher"] != "Wikipedia" for p in searches for s in p["sources"])
    assert any(s["publisher"] == "Wikipedia" for p in searches for s in p["rejected_sources"])
    with client.session_factory() as db:
        rejected = db.scalars(
            select(ToolExecution).where(
                ToolExecution.session_id == uuid.UUID(sid),
                ToolExecution.tool_name == "search_web"
            )
        ).all()
        assert all(r.simulated and r.rejected_count >= 1 for r in rejected)