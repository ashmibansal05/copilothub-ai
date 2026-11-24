"""Phase 16-18 regressions: ownership, revisions, exports and code in reports."""
import io
import uuid
import zipfile
from sqlalchemy import select
from app.models.report import Report
from app.services import code_service
from app.services.coding_agent import classify_task
from helpers import create_session, make_user, join


def test_classify():
    assert classify_task("Write Python code for a calculator") == "CODING"
    assert classify_task("Research sorting algorithms") == "RESEARCH"
    assert classify_task("Compare sorting algorithms and implement them in Python") == "HYBRID"


def test_invalid_paths():
    import pytest
    for path in ("../.env", "/etc/passwd", "a/../../bad", "C:/secret.key", "foo\\bar", "secret.pem", ".env"):
        with pytest.raises(code_service.CodeError): code_service.safe_path(path)


def test_shared_code_versions_permissions_and_download(client):
    owner, _ = make_user(client, "fileowner")
    sess = create_session(client, owner, task="Write Python code")
    sid = sess["id"]
    editor, _ = make_user(client, "fileeditor")
    viewer, _ = make_user(client, "fileviewer")
    stranger, _ = make_user(client, "filestranger")
    join(client, editor, sess["editor_code"])
    join(client, viewer, sess["viewer_code"])
    with client.session_factory() as db:
        saved = code_service.save_file(db, uuid.UUID(sid), "calculator.py", "print(1 + 1)\n")
    aid = saved["id"]
    assert client.get(f"/sessions/{sid}/code", headers=viewer).json()["files"][0]["path"] == "calculator.py"
    assert client.get(f"/sessions/{sid}/code", headers=stranger).status_code == 404
    assert client.get(f"/sessions/{sid}/code/{aid}", headers=viewer).json()["content"] == "print(1 + 1)\n"
    assert client.put(f"/sessions/{sid}/code/{aid}", json={"content":"x=2\n", "expected_version":1}, headers=viewer).status_code == 403
    success = client.put(f"/sessions/{sid}/code/{aid}", json={"content":"x=2\n", "expected_version":1}, headers=editor)
    assert success.status_code == 200, success.text
    assert success.json()["version"] == 2
    assert client.put(f"/sessions/{sid}/code/{aid}", json={"content":"x=3", "expected_version":1}, headers=owner).status_code == 409
    assert client.get(f"/sessions/{sid}/code/{aid}?version=1", headers=owner).json()["content"] == "print(1 + 1)\n"
    assert len(client.get(f"/sessions/{sid}/code/{aid}/versions", headers=owner).json()) == 2
    source = client.get(f"/sessions/{sid}/code-export", headers=viewer)
    assert source.status_code == 200
    with zipfile.ZipFile(io.BytesIO(source.content)) as z:
        assert z.read("calculator.py") == b"x=2\n"
        assert "project-manifest.json" in z.namelist()
    assert client.get(f"/sessions/{sid}/code-export", headers=stranger).status_code == 404


def test_report_export_includes_current_source(client):
    owner, _ = make_user(client, "codereport")
    s = create_session(client, owner, task="Implement Python calculator")
    sid = uuid.UUID(s["id"])
    with client.session_factory() as db:
        code_service.save_file(db, sid, "main.py", "def add(a,b):\n    return a+b\n")
        r = Report(session_id=sid, title="Code project", content="# Code project", kind="FINAL", status="FINAL",
                   sections=[{"key":"summary", "title":"Summary", "body":"A calculator."}])
        db.add(r); db.commit()
        rid = str(r.id)
    detail = client.get(f"/sessions/{sid}/reports/{rid}", headers=owner).json()
    assert "Source Code and Implementation" in [x["title"] for x in detail["sections"]]
    md = client.get(f"/sessions/{sid}/reports/{rid}/download?format=md", headers=owner)
    assert "def add(a,b)" in md.text
    html = client.get(f"/sessions/{sid}/reports/{rid}/download?format=html", headers=owner)
    assert b"def add(a,b)" in html.content
    word = client.get(f"/sessions/{sid}/reports/{rid}/download?format=docx", headers=owner)
    assert word.status_code == 200 and word.content[:2] == b"PK"
    complete = client.get(f"/sessions/{sid}/code-export?complete=true", headers=owner)
    assert complete.status_code == 200
    with zipfile.ZipFile(io.BytesIO(complete.content)) as z:
        assert "source-code/main.py" in z.namelist()
        assert "reports/Project_Report.docx" in z.namelist()
        assert b"def add(a,b)" in z.read("reports/Project_Report.md")
