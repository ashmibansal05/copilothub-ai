"""Code approval gates final reporting and binds approval to exact file versions."""
import uuid
from sqlalchemy import select
from helpers import create_session, make_user, join
from app.models.report import Report
from app.models.session import AgentSession, AgentStatus
from app.services import code_service


def test_code_review_owner_approval_creates_final_immutable_report(client):
    owner, _ = make_user(client, "codegateowner")
    editor, _ = make_user(client, "codegateeditor")
    viewer, _ = make_user(client, "codegateviewer")
    sess = create_session(client, owner, task="Write Python code for a calculator")
    join(client, editor, sess["editor_code"])
    join(client, viewer, sess["viewer_code"])
    sid = sess["id"]
    with client.session_factory() as db:
        code_service.save_file(db, uuid.UUID(sid), "main.py", "print(123)\n")
    assert client.post(f"/sessions/{sid}/code-review/request", headers=viewer).status_code == 403
    r = client.post(f"/sessions/{sid}/code-review/request", headers=editor)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PENDING"
    with client.session_factory() as db:
        assert db.get(AgentSession, uuid.UUID(sid)).status == AgentStatus.WAITING_FOR_APPROVAL
        assert db.scalars(select(Report).where(Report.session_id == uuid.UUID(sid), Report.kind == "FINAL")).all() == []
    assert client.post(f"/sessions/{sid}/code-review/decision", headers=editor,
                       json={"approve": True, "feedback": ""}).status_code == 403
    r = client.post(f"/sessions/{sid}/code-review/decision", headers=owner,
                    json={"approve": True, "feedback": ""})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"
    final = client.get(f"/sessions/{sid}/report", headers=owner)
    assert final.status_code == 200
    assert "print(123)" in final.json()["content"]
    assert client.get(f"/sessions/{sid}/code-export?complete=true", headers=owner).status_code == 200

    # Editing after approval does not rewrite the previously approved report.
    code = client.get(f"/sessions/{sid}/code", headers=owner).json()["files"][0]
    r = client.put(f"/sessions/{sid}/code/{code['id']}", headers=editor,
                   json={"content": "print(456)\n", "expected_version": 1})
    assert r.status_code == 200, r.text
    assert "print(123)" in client.get(f"/sessions/{sid}/report", headers=owner).json()["content"]
    assert "print(456)" not in client.get(f"/sessions/{sid}/report", headers=owner).json()["content"]
    assert client.get(f"/sessions/{sid}/code-export?complete=true", headers=owner).status_code == 409


def test_rejection_keeps_files_and_starts_revision(client, monkeypatch):
    owner, _ = make_user(client, "coderejectowner")
    sess = create_session(client, owner, task="Implement Python calculator")
    sid = sess["id"]
    with client.session_factory() as db:
        code_service.save_file(db, uuid.UUID(sid), "main.py", "print(1)\n")
    r = client.post(f"/sessions/{sid}/code-review/request", headers=owner)
    assert r.status_code == 200, r.text
    assert client.post(f"/sessions/{sid}/code-review/decision", headers=owner,
                       json={"approve": False, "feedback": ""}).status_code == 422
    from app.api import code as code_api
    async def fake_revision(sid, task, feedback, **kwargs):
        return None
    monkeypatch.setattr(code_api, "_background", fake_revision)
    r = client.post(f"/sessions/{sid}/code-review/decision", headers=owner,
                    json={"approve": False, "feedback": "Please fix the output"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "REJECTED"
    assert client.get(f"/sessions/{sid}/code", headers=owner).json()["files"]
    assert client.get(f"/sessions/{sid}/report", headers=owner).status_code == 404
    with client.session_factory() as db:
        assert db.get(AgentSession, uuid.UUID(sid)).status == AgentStatus.RUNNING


def test_edit_invalidates_pending_approval(client):
    owner, _ = make_user(client, "codestaleowner")
    sess = create_session(client, owner, task="Implement Python calculator")
    sid = sess["id"]
    with client.session_factory() as db:
        code_service.save_file(db, uuid.UUID(sid), "main.py", "print(1)\n")
    client.post(f"/sessions/{sid}/code-review/request", headers=owner)
    item = client.get(f"/sessions/{sid}/code", headers=owner).json()["files"][0]
    assert client.put(f"/sessions/{sid}/code/{item['id']}", headers=owner,
                      json={"content": "print(2)\n", "expected_version": 1}).status_code == 200
    assert client.post(f"/sessions/{sid}/code-review/decision", headers=owner,
                       json={"approve": True, "feedback": ""}).status_code == 409
    assert client.post(f"/sessions/{sid}/code-review/request", headers=owner).status_code == 200


def test_hybrid_owner_approval_preserves_research_and_adds_code(client):
    owner, _ = make_user(client, "hybridreportowner")
    sess = create_session(client, owner, task="Compare calculators and implement one in Python")
    sid = uuid.UUID(sess["id"])
    with client.session_factory() as db:
        research = Report(
            session_id=sid,
            title="Final research report",
            content="# Final research report",
            kind="FINAL",
            status="FINAL",
            sections=[
                {"key": "summary", "title": "Executive Summary", "body": "Research summary."},
                {"key": "findings", "title": "Findings", "body": "Python is easier to read."},
            ],
        )
        db.add(research)
        code_service.save_file(db, sid, "calculator.py", "print(10)\n")
        db.commit()
    assert client.post(f"/sessions/{sid}/code-review/request", headers=owner).status_code == 200
    approved = client.post(f"/sessions/{sid}/code-review/decision", headers=owner,
                           json={"approve": True, "feedback": ""})
    assert approved.status_code == 200, approved.text
    final = client.get(f"/sessions/{sid}/report", headers=owner)
    assert final.status_code == 200
    titles = [s["title"] for s in final.json()["sections"]]
    assert "Findings" in titles
    assert "Source Code and Implementation" in titles
    assert "print(10)" in final.json()["content"]


def test_hybrid_generate_queues_while_research_is_running(client, monkeypatch):
    owner, _ = make_user(client, "queuehybridowner")
    sess = create_session(client, owner, task="Compare note apps and build one with FastAPI")
    sid = sess["id"]
    from app.agents.runner import agent_runner

    monkeypatch.setattr(agent_runner, "is_active", lambda _sid: True)
    result = client.post(f"/sessions/{sid}/code/generate", headers=owner, json={"instruction": "also add login support"})
    assert result.status_code == 202, result.text
    body = result.json()
    assert body["queued"] is True
    details = client.get(f"/sessions/{sid}/code", headers=owner).json()
    assert details["workflow"]["queued_requests"] == 1
