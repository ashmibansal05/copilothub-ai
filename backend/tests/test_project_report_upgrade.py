"""Regression checks for quality, immutability and factual coding analytics."""
import uuid
from helpers import create_session, make_user
from app.services import code_service


def test_report_has_actual_file_inventory_and_accurate_validation(client):
    owner, _ = make_user(client, "reportqualityowner")
    session = create_session(client, owner, task="Write Python code for a calculator")
    sid = session["id"]
    with client.session_factory() as db:
        code_service.save_file(db, uuid.UUID(sid), "calculator.py", "print(42)\n")
        code_service.save_file(db, uuid.UUID(sid), "README.md", "# Run\n\npython calculator.py\n")
    review = client.post(f"/sessions/{sid}/code-review/request", headers=owner)
    assert review.status_code == 200, review.text
    approved = client.post(f"/sessions/{sid}/code-review/decision", headers=owner,
                           json={"approve": True, "feedback": ""})
    assert approved.status_code == 200, approved.text
    report = client.get(f"/sessions/{sid}/report", headers=owner).json()
    titles = [s["title"] for s in report["sections"]]
    assert "Deliverables and File Inventory" in titles
    assert "Validation and Verification" in titles
    assert "Setup and Usage" in titles
    assert "Collaboration and Human Review" in titles
    assert "Source Code and Implementation" in titles
    assert "Syntax-validated files: 1" in report["content"]
    assert "not performed" in report["content"]
    assert "print(42)" in report["content"]

    analytics = client.get(f"/sessions/{sid}/analytics", headers=owner)
    assert analytics.status_code == 200, analytics.text
    m = analytics.json()["project_metrics"]
    assert m["files"] == 2
    assert m["syntax_validated"] == 1
    assert m["not_validated"] == 1
    assert m["versions_saved"] == 2
    assert m["approval_status"] == "APPROVED"
    assert m["runtime_tested"] is False

    previous_id = report["id"]
    refresh = client.post(f"/sessions/{sid}/code-review/refresh-report", headers=owner)
    assert refresh.status_code == 200, refresh.text
    updated = client.get(f"/sessions/{sid}/report", headers=owner).json()
    assert updated["id"] != previous_id
    original = client.get(f"/sessions/{sid}/reports/{previous_id}", headers=owner).json()
    assert original["content"] == report["content"]


def test_cannot_refresh_report_after_edits_to_approved_code(client):
    owner, _ = make_user(client, "refreshstaleowner")
    session = create_session(client, owner, task="Implement a Python calculator")
    sid = session["id"]
    with client.session_factory() as db:
        code_service.save_file(db, uuid.UUID(sid), "main.py", "print(1)\n")
    client.post(f"/sessions/{sid}/code-review/request", headers=owner)
    client.post(f"/sessions/{sid}/code-review/decision", headers=owner,
                json={"approve": True, "feedback": ""})
    art = client.get(f"/sessions/{sid}/code", headers=owner).json()["files"][0]
    client.put(f"/sessions/{sid}/code/{art['id']}", headers=owner,
               json={"content": "print(2)\n", "expected_version": 1})
    assert client.post(f"/sessions/{sid}/code-review/refresh-report", headers=owner).status_code == 409
