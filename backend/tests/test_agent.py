import asyncio
import uuid

from sqlalchemy import select

from app.agents.orchestrator import AgentOrchestrator
from app.models.agent import AgentAction
from app.models.event import AgentEvent
from app.models.session import AgentSession, AgentStatus
from helpers import ScriptedBrain, create_session, make_running_session, make_user


def read_until(ws, stop_types, limit=300):
    seen = []
    for _ in range(limit):
        event = ws.receive_json()
        seen.append(event["type"])
        if event["type"] in stop_types:
            return seen
    raise AssertionError(f"Did not see {stop_types}; saw {seen[-10:]}")


def session_status(client, sid):
    with client.session_factory() as db:
        return db.get(AgentSession, sid).status


# ---------------------------------------------------------------- full demo run
def test_demo_agent_runs_to_completion(client):
    headers, token = make_user(client, "owner")
    s = create_session(client, headers)

    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": token})
        assert ws.receive_json()["type"] == "CONNECTED"
        assert client.post(f"/sessions/{s['id']}/start", headers=headers).status_code == 200
        seen = read_until(ws, {"COMPLETED", "FAILED"})

    assert seen[-1] == "COMPLETED"
    for expected in ("STEP_STARTED", "TOOL_STARTED", "TOOL_COMPLETED", "STEP_COMPLETED"):
        assert expected in seen

    state = client.get(f"/sessions/{s['id']}/state", headers=headers).json()
    assert state["status"] == "COMPLETED"
    assert state["progress"] == 100
    assert state["engine"] == "demo"
    assert len(state["plan"]) == 7  # cloud-research plan
    assert state["step_index"] == 7
    assert state["confidence"] is not None

    actions = client.get(f"/sessions/{s['id']}/actions", headers=headers).json()
    assert {a["action_type"] for a in actions} >= {"PLAN", "TOOL_CALL", "EVALUATE", "FINALIZE"}
    assert all(a["success"] for a in actions)


def test_state_requires_membership(client):
    owner_h, _ = make_user(client, "owner")
    other_h, _ = make_user(client, "stranger")
    s = create_session(client, owner_h)
    assert client.get(f"/sessions/{s['id']}/state", headers=other_h).status_code == 404
    assert client.get(f"/sessions/{s['id']}/actions", headers=other_h).status_code == 404


def test_state_before_start_is_empty(client):
    h, _ = make_user(client, "owner")
    s = create_session(client, h)
    state = client.get(f"/sessions/{s['id']}/state", headers=h).json()
    assert state["status"] == "CREATED" and state["plan"] == [] and state["progress"] == 0


def test_llm_status_endpoint_never_crashes(client):
    h, _ = make_user(client, "owner")
    r = client.get("/llm/status", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "ollama" and "ready" in body
    assert client.get("/llm/status").status_code == 401


# ---------------------------------------------------------------- orchestrator
def test_pause_blocks_progress_and_resume_continues(client):
    sid = make_running_session(client)
    brain = ScriptedBrain(steps=6, delay=0.05)

    async def scenario():
        orch = AgentOrchestrator(sid, brain_factory=brain.factory())
        task = asyncio.create_task(orch.run())
        await asyncio.sleep(0.12)
        orch.pause()
        await asyncio.sleep(0.25)  # let the in-flight step finish
        calls_at_pause = brain.calls
        await asyncio.sleep(0.3)
        assert brain.calls == calls_at_pause, "agent kept working while paused"
        assert not task.done()
        orch.resume()
        await asyncio.wait_for(task, timeout=10)
        return calls_at_pause

    calls_at_pause = asyncio.run(scenario())
    assert 0 < calls_at_pause < 6
    assert brain.calls == 6
    assert session_status(client, sid) == AgentStatus.COMPLETED


def test_transient_failures_are_retried_and_recorded(client):
    sid = make_running_session(client)
    brain = ScriptedBrain(steps=2, fail_first=2)  # default max_retries=2 -> 3 attempts allowed
    asyncio.run(AgentOrchestrator(sid, brain_factory=brain.factory()).run())

    assert session_status(client, sid) == AgentStatus.COMPLETED
    with client.session_factory() as db:
        failed = db.scalars(
            select(AgentAction).where(AgentAction.session_id == sid, AgentAction.success.is_(False))
        ).all()
    assert len(failed) == 2
    assert all(a.error == "boom" for a in failed)


def test_persistent_failure_escalates_and_fails(client):
    sid = make_running_session(client)
    brain = ScriptedBrain(steps=3, fail_always=True)
    asyncio.run(AgentOrchestrator(sid, brain_factory=brain.factory()).run())

    assert session_status(client, sid) == AgentStatus.FAILED
    assert brain.calls == 3  # 1 try + 2 retries, then give up
    with client.session_factory() as db:
        events = db.scalars(select(AgentEvent).where(AgentEvent.session_id == sid)).all()
    types = [e.type for e in events]
    assert "FAILED" in types
    kinds = [e.payload.get("kind") for e in events if e.type == "AGENT_MESSAGE"]
    assert "escalation" in kinds


def test_step_limit_is_enforced(client):
    sid = make_running_session(client)
    brain = ScriptedBrain(steps=12)  # plan longer than AGENT_MAX_STEPS (8)
    asyncio.run(AgentOrchestrator(sid, brain_factory=brain.factory()).run())
    assert brain.calls == 8
    assert session_status(client, sid) == AgentStatus.COMPLETED


def test_fallback_to_demo_when_llm_unreachable(client, monkeypatch):
    """DEMO_MODE=false with no Ollama running must fall back, with a visible warning."""
    from app.agents.factory import create_brain
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", False)
    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://127.0.0.1:9")  # nothing listens here
    from app.llm.factory import get_llm_provider

    get_llm_provider.cache_clear()
    try:
        brain, notice = asyncio.run(create_brain())
    finally:
        get_llm_provider.cache_clear()
    assert brain.engine == "demo"
    assert notice and "demo mode" in notice.lower()


def test_orphaned_sessions_are_recovered(client):
    from app.services.agent_service import recover_orphaned_sessions

    sid = make_running_session(client)
    assert asyncio.run(recover_orphaned_sessions()) == 1
    assert session_status(client, sid) == AgentStatus.FAILED
    assert asyncio.run(recover_orphaned_sessions()) == 0  # idempotent


def test_start_then_stop_cancels_agent(client):
    headers, token = make_user(client, "owner")
    s = create_session(client, headers)
    sid = uuid.UUID(s["id"])
    from app.agents.runner import agent_runner

    slow = ScriptedBrain(steps=50, delay=0.2)
    agent_runner.brain_factory = slow.factory()  # reset by the next test via fresh import state below
    try:
        client.post(f"/sessions/{s['id']}/start", headers=headers)
        assert client.post(f"/sessions/{s['id']}/stop", headers=headers).json()["status"] == "CANCELLED"
    finally:
        from app.agents.factory import create_brain

        agent_runner.brain_factory = create_brain
    calls_after_stop = slow.calls
    import time

    time.sleep(0.5)
    assert slow.calls == calls_after_stop, "agent kept running after stop"
    assert session_status(client, sid) == AgentStatus.CANCELLED