import asyncio
import uuid

from sqlalchemy import select

from app.agents.orchestrator import AgentOrchestrator
from app.agents.state import ApprovalDecision
from app.core.config import get_settings
from app.models.approval import ApprovalKind
from app.models.constraint import ConstraintAction
from app.models.event import AgentEvent
from app.models.intervention import Priority
from app.models.session import AgentSession, AgentStatus
from app.models.user import User
from app.services import approval_service
from app.services.constraint_manager import ConstraintManager
from helpers import ScriptedBrain, create_session, make_running_session, make_user, read_until


def iv(client, headers, sid, **body):
    return client.post(f"/sessions/{sid}/interventions", json=body, headers=headers)



def tool_events(client, sid):
    session_uuid = uuid.UUID(str(sid))

    with client.session_factory() as db:
        events = db.scalars(
            select(AgentEvent).where(
                AgentEvent.session_id == session_uuid,
                AgentEvent.type == "TOOL_COMPLETED",
            )
        ).all()

        return sorted(
            (e.payload for e in events),
            key=lambda p: p["step_index"],
        )



# ---------------------------------------------------------------- approval flow
def test_final_draft_waits_for_approval_then_completes(client, monkeypatch, set_brain):
    monkeypatch.setattr(get_settings(), "agent_require_final_approval", True)
    set_brain(ScriptedBrain(steps=2))
    owner_h, owner_t = make_user(client, "owner")
    s = create_session(client, owner_h)

    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": owner_t})
        ws.receive_json()
        client.post(f"/sessions/{s['id']}/start", headers=owner_h)
        assert read_until(ws, {"APPROVAL_REQUESTED", "FAILED"})[-1] == "APPROVAL_REQUESTED"

        state = client.get(f"/sessions/{s['id']}/state", headers=owner_h).json()
        assert state["status"] == "WAITING_FOR_APPROVAL"
        assert state["pending_approval"]["kind"] == "FINAL_REPORT"
        assert state["pending_approval"]["payload"]["draft"] == "summary"

        assert iv(client, owner_h, s["id"], type="APPROVE").status_code == 201
        seen = read_until(ws, {"COMPLETED", "FAILED"})
        assert seen[-1] == "COMPLETED" and "APPROVAL_COMPLETED" in seen

    state = client.get(f"/sessions/{s['id']}/state", headers=owner_h).json()
    assert state["status"] == "COMPLETED" and state["pending_approval"] is None


def test_rejection_feedback_reaches_the_next_draft(client, monkeypatch, set_brain):
    monkeypatch.setattr(get_settings(), "agent_require_final_approval", True)
    brain = ScriptedBrain(steps=1)
    set_brain(brain)
    owner_h, owner_t = make_user(client, "owner")
    s = create_session(client, owner_h)

    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": owner_t})
        ws.receive_json()
        client.post(f"/sessions/{s['id']}/start", headers=owner_h)
        read_until(ws, {"APPROVAL_REQUESTED"})
        assert iv(client, owner_h, s["id"], type="REJECT", content="Add pricing details").status_code == 201
        read_until(ws, {"APPROVAL_REQUESTED", "FAILED"})  # second round
        assert any("Add pricing details" in n for n in brain.summarize_notes[-1])
        iv(client, owner_h, s["id"], type="APPROVE")
        assert read_until(ws, {"COMPLETED", "FAILED"})[-1] == "COMPLETED"
    assert len(brain.summarize_notes) == 2


def test_too_many_rejections_escalate_and_fail(client, monkeypatch, set_brain):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_require_final_approval", True)
    monkeypatch.setattr(settings, "agent_max_approval_rounds", 2)
    set_brain(ScriptedBrain(steps=1))
    owner_h, owner_t = make_user(client, "owner")
    s = create_session(client, owner_h)

    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": owner_t})
        ws.receive_json()
        client.post(f"/sessions/{s['id']}/start", headers=owner_h)
        read_until(ws, {"APPROVAL_REQUESTED"})
        iv(client, owner_h, s["id"], type="REJECT", content="nope")
        read_until(ws, {"APPROVAL_REQUESTED"})
        iv(client, owner_h, s["id"], type="REJECT", content="still nope")
        assert read_until(ws, {"FAILED", "COMPLETED"})[-1] == "FAILED"
    assert client.get(f"/sessions/{s['id']}/state", headers=owner_h).json()["status"] == "FAILED"


def test_viewer_cannot_approve(client, monkeypatch, set_brain):
    monkeypatch.setattr(get_settings(), "agent_require_final_approval", True)
    set_brain(ScriptedBrain(steps=1))
    owner_h, owner_t = make_user(client, "owner")
    viewer_h, _ = make_user(client, "viewer1")
    s = create_session(client, owner_h)
    client.post("/sessions/join", json={"code": s["viewer_code"]}, headers=viewer_h)
    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": owner_t})
        ws.receive_json()
        client.post(f"/sessions/{s['id']}/start", headers=owner_h)
        read_until(ws, {"APPROVAL_REQUESTED"})
        assert iv(client, viewer_h, s["id"], type="APPROVE").status_code == 403
        client.post(f"/sessions/{s['id']}/stop", headers=owner_h)  # cleanup: closes the approval
        assert client.get(f"/sessions/{s['id']}/state", headers=owner_h).json()["pending_approval"] is None


def test_review_request_makes_agent_wait_for_approval(client):
    sid = make_running_session(client)
    brain = ScriptedBrain(steps=2, delay=0.01)

    async def scenario():
        orch = AgentOrchestrator(sid, brain_factory=brain.factory())
        orch.request_review(None, "alice", "please check")
        task = asyncio.create_task(orch.run())
        pending_id = kind = None
        for _ in range(300):
            await asyncio.sleep(0.02)
            with client.session_factory() as db:
                pending = approval_service.get_pending(db, sid)
                if pending:
                    pending_id, kind = pending.id, pending.kind
                    break
        assert pending_id is not None and kind == ApprovalKind.REVIEW
        with client.session_factory() as db:
            assert db.get(AgentSession, sid).status == AgentStatus.WAITING_FOR_APPROVAL
        assert orch.resolve_approval(pending_id, ApprovalDecision(True, None, "alice"))
        await asyncio.wait_for(task, 10)

    asyncio.run(scenario())
    with client.session_factory() as db:
        assert db.get(AgentSession, sid).status == AgentStatus.COMPLETED


# ---------------------------------------------------------------- constraints in the agent loop
def test_demo_agent_respects_constraints_set_before_start(client):
    h, token = make_user(client, "owner")
    s = create_session(client, h)
    sid = s["id"]
    iv(client, h, sid, type="REJECT_SOURCE", target="Wikipedia")
    iv(client, h, sid, type="ADD_CONSTRAINT", action="PREFER_SOURCE", target="official documentation")

    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.send_json({"type": "AUTH", "token": token})
        ws.receive_json()
        client.post(f"/sessions/{sid}/start", headers=h)
        assert read_until(ws, {"COMPLETED", "FAILED"})[-1] == "COMPLETED"

    events = tool_events(client, sid)
    used = [src for e in events for src in e["sources"]]
    rejected = [src for e in events for src in e["rejected_sources"]]
    assert used and all(src["publisher"] != "Wikipedia" for src in used)
    assert rejected and all(src["publisher"] == "Wikipedia" and src["rejected_by"] == "Wikipedia" for src in rejected)

    aws_step = next(e for e in events if e["step_index"] == 3)  # "Gather information on AWS"
    assert aws_step["sources"][0]["source_type"] == "official documentation"
    assert aws_step["sources"][0]["preferred"] is True

    messages = client.get(f"/sessions/{sid}/events", headers=h).json()
    draft = next(m["payload"]["text"] for m in messages if m["payload"].get("text", "").startswith("Draft summary"))
    assert "Wikipedia" not in draft.split("Human constraints")[0]  # not listed among the sources used
    assert "Do not use sources from or about" in draft  # the constraint is reported back


def test_constraint_added_mid_run_filters_later_steps_and_final_history(client):
    sid = make_running_session(client)

    def on_call(n):
        if n == 2:  # a human adds the rule while step 2 is executing
            with client.session_factory() as db:
                owner = db.scalar(select(User).where(User.username == "owner"))
                ConstraintManager.add(db, sid, owner, ConstraintAction.EXCLUDE_SOURCE, "Wikipedia", Priority.HIGH)
                db.commit()

    brain = ScriptedBrain(steps=4, with_sources=True, on_call=on_call)
    asyncio.run(AgentOrchestrator(sid, brain_factory=brain.factory()).run())

    events = tool_events(client, sid)
    assert any(s["publisher"] == "Wikipedia" for s in events[0]["sources"])  # step 1: before the rule
    for e in events[1:]:  # step 2 onwards: filtered
        assert all(s["publisher"] != "Wikipedia" for s in e["sources"])
        assert e["rejected_sources"]
    # the final summary was built from re-filtered history, so step 1's Wikipedia source is gone too
    assert all(s["publisher"] != "Wikipedia" for o in brain.summarize_history for s in o["sources"])


# ---------------------------------------------------------------- re-planning
def test_modified_task_triggers_replan(client):
    sid = make_running_session(client)
    holder = {}

    def on_call(n):
        if n == 2:
            with client.session_factory() as db:
                row = db.get(AgentSession, sid)
                row.task = "A different task entirely now"
                db.commit()
            holder["orch"].request_replan()

    brain = ScriptedBrain(steps=3, on_call=on_call)
    orch = AgentOrchestrator(sid, brain_factory=brain.factory())
    holder["orch"] = orch
    asyncio.run(orch.run())

    assert len(brain.plan_tasks) == 2 and brain.plan_tasks[-1] == "A different task entirely now"
    assert brain.calls == 5  # 2 steps of the first plan + 3 of the new plan
    with client.session_factory() as db:
        assert db.get(AgentSession, sid).status == AgentStatus.COMPLETED