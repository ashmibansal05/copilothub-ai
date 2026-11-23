import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.agents.orchestrator import AgentOrchestrator
from app.models.conflict import Conflict
from app.models.constraint import Constraint, ConstraintAction as A
from app.models.event import AgentEvent
from app.models.intervention import Priority as P
from app.models.session import AgentSession, AgentStatus
from app.models.user import User, UserRole
from app.services.conflict_manager import ConflictManager, conflicting, decide
from app.services.constraint_manager import ConstraintManager
from helpers import ScriptedBrain, create_session, join, make_running_session, make_user


def constraint(action, target="Wikipedia", priority=P.MEDIUM):
    return Constraint(id=uuid.uuid4(), action=action, target=target, priority=priority)


# ---------------------------------------------------------------- pure rules
def test_conflicting_pairs():
    assert conflicting(constraint(A.INCLUDE_SOURCE), constraint(A.EXCLUDE_SOURCE))
    assert conflicting(constraint(A.PREFER_SOURCE), constraint(A.EXCLUDE_SOURCE, "wikipedia.org"))
    assert not conflicting(constraint(A.PREFER_SOURCE), constraint(A.INCLUDE_SOURCE))
    assert not conflicting(constraint(A.EXCLUDE_SOURCE), constraint(A.EXCLUDE_SOURCE))
    assert not conflicting(constraint(A.EXCLUDE_SOURCE, "Wikipedia"), constraint(A.PREFER_SOURCE, "official documentation"))
    assert not conflicting(constraint(A.INSTRUCTION, "be brief"), constraint(A.INSTRUCTION, "be detailed"))


def test_priority_rules():
    inc, exc = constraint(A.INCLUDE_SOURCE, priority=P.LOW), constraint(A.EXCLUDE_SOURCE, priority=P.HIGH)
    winner, rule = decide(inc, UserRole.OWNER, exc, UserRole.EDITOR)
    assert winner is exc and "priority" in rule.lower()  # priority beats role

    inc, exc = constraint(A.INCLUDE_SOURCE), constraint(A.EXCLUDE_SOURCE)
    winner, rule = decide(inc, UserRole.EDITOR, exc, UserRole.OWNER)
    assert winner is exc and "owner" in rule.lower()

    winner, rule = decide(inc, UserRole.EDITOR, exc, UserRole.EDITOR)
    assert winner is None and "explicit resolution" in rule.lower()


# ---------------------------------------------------------------- API
pytestmark_api = pytest.mark.usefixtures("disable_agent")


def setup(client):
    owner, _ = make_user(client, "owner")
    e1, _ = make_user(client, "editor1")
    e2, _ = make_user(client, "editor2")
    s = create_session(client, owner)
    join(client, e1, s["editor_code"])
    join(client, e2, s["editor_code"])
    return s["id"], owner, e1, e2


def add(client, headers, sid, action, target="Wikipedia", priority=None):
    body = {"action": action, "target": target}
    if priority:
        body["priority"] = priority
    r = client.post(f"/sessions/{sid}/constraints", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def conflicts(client, headers, sid, status="all"):
    return client.get(f"/sessions/{sid}/conflicts?status={status}", headers=headers).json()


def effective_targets(client, sid):
    with client.session_factory() as db:
        return sorted((c.action.value, c.target) for c in ConflictManager.effective_constraints(db, uuid.UUID(sid)))


@pytestmark_api
def test_same_role_same_priority_is_a_blocking_conflict(client):
    sid, owner, e1, e2 = setup(client)
    add(client, e1, sid, "INCLUDE_SOURCE")
    assert conflicts(client, owner, sid) == []
    add(client, e2, sid, "EXCLUDE_SOURCE")

    (c,) = conflicts(client, owner, sid)
    assert c["status"] == "OPEN" and c["requires_resolution"] is True and c["suggested_winner_id"] is None
    assert c["constraint_a"]["action"] == "INCLUDE_SOURCE" and c["constraint_a"]["created_by_username"] == "editor1"
    assert c["constraint_b"]["action"] == "EXCLUDE_SOURCE" and c["constraint_b"]["created_by_username"] == "editor2"
    assert "restrictive" in c["provisional"]
    # until the owner decides, only the restrictive rule is enforced
    assert effective_targets(client, sid) == [("EXCLUDE_SOURCE", "Wikipedia")]
    assert client.get(f"/sessions/{sid}/state", headers=owner).json()["open_conflicts"][0]["id"] == c["id"]
    events = client.get(f"/sessions/{sid}/events", headers=owner).json()
    assert "CONFLICT_DETECTED" in {e["type"] for e in events}


@pytestmark_api
def test_priority_rule_picks_a_provisional_winner_without_blocking(client):
    sid, owner, e1, e2 = setup(client)
    add(client, e1, sid, "INCLUDE_SOURCE", priority="MEDIUM")
    add(client, e2, sid, "EXCLUDE_SOURCE", priority="HIGH")
    (c,) = conflicts(client, owner, sid)
    assert c["requires_resolution"] is False and c["suggested_winner_id"] == c["constraint_b"]["constraint_id"]
    assert effective_targets(client, sid) == [("EXCLUDE_SOURCE", "Wikipedia")]


@pytestmark_api
def test_owner_outranks_editor(client):
    sid, owner, e1, _ = setup(client)
    add(client, e1, sid, "EXCLUDE_SOURCE")
    add(client, owner, sid, "INCLUDE_SOURCE")
    (c,) = conflicts(client, owner, sid)
    assert c["suggested_winner_id"] == c["constraint_b"]["constraint_id"]  # the owner's newer INCLUDE
    assert effective_targets(client, sid) == [("INCLUDE_SOURCE", "Wikipedia")]


@pytestmark_api
def test_unrelated_constraints_do_not_conflict(client):
    sid, owner, e1, _ = setup(client)
    add(client, e1, sid, "EXCLUDE_SOURCE", "Wikipedia")
    add(client, e1, sid, "PREFER_SOURCE", "official documentation")
    assert conflicts(client, owner, sid) == []


@pytestmark_api
def test_only_the_owner_can_resolve_and_the_loser_is_superseded(client):
    sid, owner, e1, e2 = setup(client)
    add(client, e1, sid, "INCLUDE_SOURCE")
    add(client, e2, sid, "EXCLUDE_SOURCE")
    (c,) = conflicts(client, owner, sid)
    url = f"/sessions/{sid}/conflicts/{c['id']}/resolve"
    keep = c["constraint_b"]["constraint_id"]

    assert client.post(url, json={"winner_constraint_id": keep}, headers=e1).status_code == 403
    assert client.post(url, json={"winner_constraint_id": str(uuid.uuid4())}, headers=owner).status_code == 422

    r = client.post(url, json={"winner_constraint_id": keep, "note": "no encyclopaedias"}, headers=owner)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "RESOLVED" and body["resolution"] == "KEEP_B" and body["resolved_by_username"] == "owner"
    assert body["constraint_a"]["still_active"] is False
    active = client.get(f"/sessions/{sid}/constraints", headers=owner).json()
    assert [(x["action"], x["target"]) for x in active] == [("EXCLUDE_SOURCE", "Wikipedia")]
    assert client.post(url, json={"winner_constraint_id": keep}, headers=owner).status_code == 409
    assert conflicts(client, owner, sid, "OPEN") == []
    assert client.get(f"/sessions/{sid}/state", headers=owner).json()["open_conflicts"] == []
    audit = [i["type"] for i in client.get(f"/sessions/{sid}/interventions", headers=owner).json()]
    assert "RESOLVE_CONFLICT" in audit


@pytestmark_api
def test_owner_can_remove_both_instructions(client):
    sid, owner, e1, e2 = setup(client)
    add(client, e1, sid, "INCLUDE_SOURCE")
    add(client, e2, sid, "EXCLUDE_SOURCE")
    (c,) = conflicts(client, owner, sid)
    r = client.post(f"/sessions/{sid}/conflicts/{c['id']}/resolve", json={"winner_constraint_id": None}, headers=owner)
    assert r.json()["resolution"] == "REMOVE_BOTH"
    assert client.get(f"/sessions/{sid}/constraints", headers=owner).json() == []


@pytestmark_api
def test_removing_a_constraint_auto_closes_its_conflict(client):
    sid, owner, e1, e2 = setup(client)
    add(client, e1, sid, "INCLUDE_SOURCE")
    exclude = add(client, e2, sid, "EXCLUDE_SOURCE")
    assert client.delete(f"/sessions/{sid}/constraints/{exclude['id']}", headers=e2).status_code == 200
    (c,) = conflicts(client, owner, sid)
    assert c["status"] == "RESOLVED" and c["resolution"] == "AUTO_CLOSED"


@pytestmark_api
def test_no_duplicate_conflicts(client):
    sid, owner, e1, e2 = setup(client)
    add(client, e1, sid, "INCLUDE_SOURCE")
    add(client, e2, sid, "EXCLUDE_SOURCE")
    add(client, e2, sid, "EXCLUDE_SOURCE")  # identical constraint: idempotent
    assert len(conflicts(client, owner, sid)) == 1


# ---------------------------------------------------------------- the agent never picks a side
def test_agent_waits_for_a_tie_conflict_then_follows_the_owners_decision(client):
    sid = make_running_session(client)
    with client.session_factory() as db:
        owner = db.scalar(select(User).where(User.username == "owner"))
        ConstraintManager.add(db, sid, owner, A.INCLUDE_SOURCE, "Wikipedia", P.MEDIUM)
        exclude, _ = ConstraintManager.add(db, sid, owner, A.EXCLUDE_SOURCE, "Wikipedia", P.MEDIUM)
        found = ConflictManager.detect(db, sid, exclude)
        db.commit()
        assert len(found) == 1 and found[0].requires_resolution
        exclude_id = exclude.id

    brain = ScriptedBrain(steps=2, with_sources=True)

    async def scenario():
        orch = AgentOrchestrator(sid, brain_factory=brain.factory())
        task = asyncio.create_task(orch.run())
        for _ in range(300):
            await asyncio.sleep(0.02)
            with client.session_factory() as db:
                if db.get(AgentSession, sid).status == AgentStatus.WAITING_FOR_APPROVAL:
                    break
        assert brain.calls == 0, "the agent acted although a conflict needs a human decision"
        with client.session_factory() as db:
            assert db.get(AgentSession, sid).status == AgentStatus.WAITING_FOR_APPROVAL
            owner = db.scalar(select(User).where(User.username == "owner"))
            conflict = db.scalar(select(Conflict).where(Conflict.session_id == sid))
            ConflictManager.resolve(db, conflict, owner, exclude_id, "keep the exclusion")
            db.commit()
        orch.notify_conflicts_changed()
        await asyncio.wait_for(task, 10)

    asyncio.run(scenario())

    with client.session_factory() as db:
        assert db.get(AgentSession, sid).status == AgentStatus.COMPLETED
        events = db.scalars(
            select(AgentEvent).where(AgentEvent.session_id == sid, AgentEvent.type == "TOOL_COMPLETED")
        ).all()
    assert brain.calls == 2
    for e in events:
        assert all(s["publisher"] != "Wikipedia" for s in e.payload["sources"])