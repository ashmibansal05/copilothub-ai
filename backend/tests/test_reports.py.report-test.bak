import io

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.report import Report
from app.services.report_service import SECTION_TITLES
from helpers import ScriptedBrain, create_session, join, make_user, read_until

TITLES = [t for _, t in SECTION_TITLES]


@pytest.fixture()
def reports_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_generate_final_report", True)


def run_session(client, set_brain, brain, prepare=None):
    set_brain(brain)
    headers, token = make_user(client, "owner")
    s = create_session(client, headers)
    sid = s["id"]
    if prepare:
        prepare(client, headers, sid)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.send_json({"type": "AUTH", "token": token})
        ws.receive_json()
        client.post(f"/sessions/{sid}/start", headers=headers)
        seen = read_until(ws, {"COMPLETED", "FAILED"})
    assert seen[-1] == "COMPLETED"
    return sid, headers, seen


def human_input(client, headers, sid):
    client.post(f"/sessions/{sid}/interventions", json={"type": "REJECT_SOURCE", "target": "Wikipedia"}, headers=headers)
    client.post(f"/sessions/{sid}/interventions", json={"type": "CORRECT", "content": "Use euros for all prices"}, headers=headers)


def sections_of(report):
    return {s["key"]: s["body"] for s in report["sections"]}


def test_the_final_report_has_the_ten_sections_and_reflects_the_human_input(client, reports_on, set_brain):
    brain = ScriptedBrain(steps=2, with_sources=True)
    sid, headers, seen = run_session(client, set_brain, brain, human_input)
    assert "REPORT_SAVED" in seen

    report = client.get(f"/sessions/{sid}/report", headers=headers).json()
    assert report["kind"] == "FINAL" and report["origin"] == "SYSTEM" and report["engine"] == "scripted"
    assert [s["title"] for s in report["sections"]] == TITLES
    body = sections_of(report)

    assert "Prepare a report comparing AWS" in body["objective"]
    assert "scripted" in body["methodology"] and "step 1" in body["methodology"]
    assert "Pricing docs" in body["evidence"] and "Wikipedia" not in body["evidence"].split("Sources")[0]
    # human decisions come from the database, in the humans' own words
    assert "Use euros for all prices" in body["human_decisions"] and "Wikipedia" in body["human_decisions"]
    assert "rejected a source" in body["human_decisions"]
    # sources: used vs rejected are kept apart
    used, _, rejected = body["sources"].partition("Sources rejected (not used):")
    assert "Pricing docs" in used and "Wikipedia" not in used
    assert "Wikipedia" in rejected and "rejected by constraint" in rejected
    assert "simulated" in body["limitations"].lower()
    assert body["executive_summary"] == "summary"  # the brain's default narrative
    assert report["content"].startswith("# Research report") and "## 10. Sources" in report["content"]
    assert client.get(f"/sessions/{sid}/reports", headers=headers).json()[0]["kind"] == "FINAL"


def test_text_that_mentions_an_excluded_source_is_flagged(client, reports_on, set_brain):
    brain = ScriptedBrain(steps=1, with_sources=True)
    brain.report_text = "According to Wikipedia, cloud prices are falling."
    sid, headers, _ = run_session(client, set_brain, brain, human_input)
    limitations = sections_of(client.get(f"/sessions/{sid}/report", headers=headers).json())["limitations"]
    assert 'mentions "Wikipedia"' in limitations and "excluded" in limitations


def test_no_report_without_the_switch_and_404_before_one_exists(client, set_brain):
    sid, headers, seen = run_session(client, set_brain, ScriptedBrain(steps=1))  # AGENT_GENERATE_FINAL_REPORT=false
    assert "REPORT_SAVED" not in seen
    assert client.get(f"/sessions/{sid}/report", headers=headers).status_code == 404


def wait_for_reports(client, headers, sid, count, timeout=15.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        found = client.get(f"/sessions/{sid}/reports", headers=headers).json()
        if len([r for r in found if r["kind"] == "FINAL"]) >= count:
            return found
        time.sleep(0.1)
    raise AssertionError("report was not generated in time")


def test_generating_on_demand_with_permissions_and_limits(client, set_brain, monkeypatch):
    sid, headers, _ = run_session(client, set_brain, ScriptedBrain(steps=1))
    editor, _ = make_user(client, "editor1")
    viewer, _ = make_user(client, "viewer1")
    code = client.get(f"/sessions/{sid}", headers=headers).json()
    join(client, editor, code["editor_code"])
    join(client, viewer, code["viewer_code"])

    assert client.post(f"/sessions/{sid}/report/generate", headers=viewer).status_code == 403
    assert client.post(f"/sessions/{sid}/report/generate", headers=editor).status_code == 202
    wait_for_reports(client, headers, sid, 1)

    monkeypatch.setattr(get_settings(), "max_final_reports_per_session", 1)
    assert client.post(f"/sessions/{sid}/report/generate", headers=headers).status_code == 409


def test_cannot_report_on_a_session_that_has_done_nothing(client):
    headers, _ = make_user(client, "owner")
    s = create_session(client, headers)
    assert client.post(f"/sessions/{s['id']}/report/generate", headers=headers).status_code == 409


def make_report(client, sid, content, sections=None):
    with client.session_factory() as db:
        report = Report(session_id=sid, title='Evil <b>title</b>', content=content, kind="FINAL", status="FINAL",
                        origin="SYSTEM", sections=sections)
        db.add(report)
        db.commit()
        return str(report.id)


def test_downloads_in_three_formats_and_html_is_escaped(client):
    import uuid

    import docx

    headers, _ = make_user(client, "owner")
    s = create_session(client, headers)
    sid = s["id"]
    evil = '<script>alert(1)</script> & "quotes"'
    rid = make_report(client, uuid.UUID(sid), f"# T\n\n{evil}", [
        {"key": "executive_summary", "title": "Executive Summary", "body": f"{evil}\n- bullet <img src=x onerror=alert(1)>"},
    ])

    md = client.get(f"/sessions/{sid}/reports/{rid}/download?format=md", headers=headers)
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert 'attachment; filename="evil-b-title-b.md"' == md.headers["content-disposition"]

    page = client.get(f"/sessions/{sid}/reports/{rid}/download?format=html", headers=headers)
    assert page.headers["x-content-type-options"] == "nosniff" and "attachment" in page.headers["content-disposition"]
    assert "<script>" not in page.text and "<img" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text and "<li>bullet &lt;img" in page.text

    word = client.get(f"/sessions/{sid}/reports/{rid}/download?format=docx", headers=headers)
    assert word.content[:2] == b"PK"
    text = "\n".join(p.text for p in docx.Document(io.BytesIO(word.content)).paragraphs)
    assert "Executive Summary" in text and "alert(1)" in text  # present as plain text, not markup

    assert client.get(f"/sessions/{sid}/reports/{rid}/download?format=pdf", headers=headers).status_code == 422
    stranger, _ = make_user(client, "stranger")
    assert client.get(f"/sessions/{sid}/reports/{rid}/download?format=md", headers=stranger).status_code == 404


def test_drafts_saved_by_the_tool_are_not_the_final_report(client):
    import uuid

    headers, _ = make_user(client, "owner")
    s = create_session(client, headers)
    with client.session_factory() as db:
        db.add(Report(session_id=uuid.UUID(s["id"]), title="Draft", content="just a draft of the report"))
        db.commit()
    assert client.get(f"/sessions/{s['id']}/report", headers=headers).status_code == 404
    assert client.get(f"/sessions/{s['id']}/reports", headers=headers).json()[0]["kind"] == "DRAFT"