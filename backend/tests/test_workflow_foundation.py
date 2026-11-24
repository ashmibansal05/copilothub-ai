"""Unified workflow regression tests (no model or network needed)."""
import uuid
from sqlalchemy import select
from helpers import create_session, make_user
from app.models.workflow_request import WorkflowRequest
from app.services.project_profile import profile_for, research_brief
from app.services.workflow_service import (
    consume_code_request, finish_claimed_requests, queue_code_request,
    queued_code_requests, recover_interrupted_requests,
)


def test_domain_profile_is_human_readable():
    profile = profile_for("Analyze marketing sales data and prepare a dashboard")
    assert profile["domain"] == "Data & Analytics"
    assert profile["expected_outputs"]
    assert profile_for("Build a website with React")["workflow"] == "CODING"
    brief = research_brief("Compare Python and C++ and build two calculators")
    assert "Do not write or compile source code" in brief


def test_queued_requests_persist_and_survive_restart(client):
    owner, _ = make_user(client, "persistentqueueowner")
    session = create_session(client, owner, task="Compare two web frameworks and build a FastAPI prototype")
    sid = uuid.UUID(session["id"])
    assert queue_code_request(sid, "also add Java support") == 1
    assert queue_code_request(sid, "add test cases") == 2
    with client.session_factory() as db:
        rows = db.scalars(select(WorkflowRequest).where(WorkflowRequest.session_id == sid)).all()
        assert len(rows) == 2
    instruction = consume_code_request(sid)
    assert "also add Java support" in instruction
    assert "add test cases" in instruction
    assert queued_code_requests(sid) == []
    assert recover_interrupted_requests() == 2
    assert len(queued_code_requests(sid)) == 2
    # The next execution claims the same instructions after the restart.
    assert "Java support" in consume_code_request(sid)
    finish_claimed_requests(sid, success=True)
    assert queued_code_requests(sid) == []
    with client.session_factory() as db:
        statuses = [r.status for r in db.scalars(select(WorkflowRequest).where(WorkflowRequest.session_id == sid)).all()]
    assert statuses == ["DONE", "DONE"]


def test_request_queue_returns_202_instead_of_conflict_while_code_generating(client, monkeypatch):
    from app.api import code as code_api
    owner, _ = make_user(client, "queuewhilewriting")
    session = create_session(client, owner, task="Write a Python calculator program")
    sid = session["id"]

    class FakeJob:
        def done(self):
            return False

    monkeypatch.setitem(code_api._jobs, uuid.UUID(sid), FakeJob())
    response = client.post(f"/sessions/{sid}/code/generate", headers=owner,
                           json={"instruction": "Add tests for division by zero"})
    assert response.status_code == 202, response.text
    assert response.json()["queued"] is True
    assert "division by zero" in queued_code_requests(uuid.UUID(sid))[0]
    code_api._jobs.pop(uuid.UUID(sid), None)


def test_plain_language_research_note_does_not_require_classifier(client):
    owner, _ = make_user(client, "plainresearchowner")
    session = create_session(client, owner, task="Research and summarize renewable energy sources")
    sid = session["id"]
    response = client.post(f"/sessions/{sid}/work-requests", headers=owner,
                           json={"text": "Include recent sources about solar power"})
    assert response.status_code == 202, response.text
    assert response.json()["mode"] == "NOTE"


def test_plain_language_code_change_uses_queue(client, monkeypatch):
    from app.agents.runner import agent_runner
    owner, _ = make_user(client, "plaincodeowner")
    session = create_session(client, owner, task="Compare Python and Java, then write sample code")
    sid = session["id"]
    monkeypatch.setattr(agent_runner, "is_active", lambda _sid: True)
    response = client.post(f"/sessions/{sid}/work-requests", headers=owner,
                           json={"text": "Add C++ examples too"})
    assert response.status_code == 202, response.text
    assert response.json()["queued"] is True
    assert "Add C++ examples" in queued_code_requests(uuid.UUID(sid))[0]
