import pytest

from helpers import create_session, join, make_user

pytestmark = pytest.mark.usefixtures("disable_agent")


def setup(client):
    owner_h, _ = make_user(client, "owner")
    ed_h, _ = make_user(client, "editor1")
    vw_h, _ = make_user(client, "viewer1")
    s = create_session(client, owner_h)
    join(client, ed_h, s["editor_code"])
    join(client, vw_h, s["viewer_code"])
    return s["id"], owner_h, ed_h, vw_h


def iv(client, headers, sid, **body):
    return client.post(f"/sessions/{sid}/interventions", json=body, headers=headers)


def test_viewer_cannot_intervene(client):
    sid, _, _, vw = setup(client)
    for body in [
        {"type": "COMMENT", "content": "hello there"},
        {"type": "CORRECT", "content": "fix this please"},
        {"type": "REJECT_SOURCE", "target": "Wikipedia"},
        {"type": "PAUSE"},
    ]:
        assert iv(client, vw, sid, **body).status_code == 403, body
    assert client.post(f"/sessions/{sid}/constraints", json={"action": "EXCLUDE_SOURCE", "target": "Wikipedia"}, headers=vw).status_code == 403


def test_only_owner_can_modify_task(client):
    sid, owner, editor, _ = setup(client)
    new_task = "Compare only pricing for a two person startup"
    assert iv(client, editor, sid, type="MODIFY_TASK", content=new_task).status_code == 403
    r = iv(client, owner, sid, type="MODIFY_TASK", content=new_task)
    assert r.status_code == 201 and r.json()["details"]["new_task"] == new_task
    assert client.get(f"/sessions/{sid}", headers=owner).json()["task"] == new_task


def test_validation(client):
    sid, owner, _, _ = setup(client)
    assert iv(client, owner, sid, type="COMMENT").status_code == 422
    assert iv(client, owner, sid, type="COMMENT", content="x").status_code == 422
    assert iv(client, owner, sid, type="MODIFY_TASK", content="short").status_code == 422
    assert iv(client, owner, sid, type="REJECT_SOURCE").status_code == 422
    assert iv(client, owner, sid, type="CHANGE_SOURCE", target="A").status_code == 422
    assert iv(client, owner, sid, type="ADD_CONSTRAINT", target="Wikipedia").status_code == 422
    assert iv(client, owner, sid, type="REMOVE_CONSTRAINT").status_code == 422
    assert iv(client, owner, sid, type="NOT_A_TYPE").status_code == 422


def test_comment_is_stored_and_visible_to_everyone(client):
    sid, _, editor, viewer = setup(client)
    r = iv(client, editor, sid, type="COMMENT", content="Looks promising so far")
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "editor1" and body["status"] == "APPLIED" and body["priority"] == "MEDIUM"
    listed = client.get(f"/sessions/{sid}/interventions", headers=viewer).json()
    assert [i["type"] for i in listed] == ["COMMENT"]


def test_correct_and_information_become_memory(client):
    sid, owner, editor, _ = setup(client)
    iv(client, editor, sid, type="CORRECT", content="Use euros for all prices")
    iv(client, owner, sid, type="ADD_INFORMATION", content="The team has two developers")
    items = client.get(f"/sessions/{sid}/memory", headers=owner).json()["items"]
    assert {(i["kind"], i["author"]) for i in items} == {("CORRECTION", "editor1"), ("FACT", "owner")}


def test_reject_source_creates_structured_constraint_and_memory(client):
    sid, _, editor, _ = setup(client)
    r = iv(client, editor, sid, type="REJECT_SOURCE", target="Wikipedia")
    assert r.status_code == 201 and r.json()["priority"] == "HIGH"
    constraints = client.get(f"/sessions/{sid}/constraints", headers=editor).json()
    assert len(constraints) == 1
    c = constraints[0]
    assert (c["type"], c["action"], c["target"], c["priority"], c["status"]) == (
        "CONSTRAINT", "EXCLUDE_SOURCE", "Wikipedia", "HIGH", "ACTIVE")
    assert c["created_by_username"] == "editor1"
    mem = client.get(f"/sessions/{sid}/memory", headers=editor).json()
    assert [i["kind"] for i in mem["items"]] == ["REJECTED_SOURCE"]
    state = client.get(f"/sessions/{sid}/state", headers=editor).json()
    assert [x["target"] for x in state["active_constraints"]] == ["Wikipedia"]
    assert state["human_interventions"][0]["type"] == "REJECT_SOURCE"


def test_duplicate_constraints_are_idempotent(client):
    sid, owner, editor, _ = setup(client)
    body = {"action": "EXCLUDE_SOURCE", "target": "Wikipedia"}
    a = client.post(f"/sessions/{sid}/constraints", json=body, headers=owner).json()
    b = client.post(f"/sessions/{sid}/constraints", json={**body, "target": "  wikipedia "}, headers=editor).json()
    assert a["id"] == b["id"]
    assert len(client.get(f"/sessions/{sid}/constraints", headers=owner).json()) == 1


def test_remove_constraint_deactivates_it_and_its_memory(client):
    sid, owner, _, _ = setup(client)
    c = client.post(f"/sessions/{sid}/constraints", json={"action": "EXCLUDE_SOURCE", "target": "Wikipedia"}, headers=owner).json()
    assert client.delete(f"/sessions/{sid}/constraints/{c['id']}", headers=owner).status_code == 200
    assert client.get(f"/sessions/{sid}/constraints", headers=owner).json() == []
    assert client.get(f"/sessions/{sid}/memory", headers=owner).json()["items"] == []
    assert client.delete(f"/sessions/{sid}/constraints/{c['id']}", headers=owner).status_code == 404


def test_change_source_excludes_old_and_prefers_new(client):
    sid, owner, _, _ = setup(client)
    r = iv(client, owner, sid, type="CHANGE_SOURCE", target="Startup blog", content="official documentation")
    assert r.status_code == 201
    actions = {c["action"]: c["target"] for c in client.get(f"/sessions/{sid}/constraints", headers=owner).json()}
    assert actions == {"EXCLUDE_SOURCE": "Startup blog", "PREFER_SOURCE": "official documentation"}


def test_include_constraint_is_remembered_as_approved_source(client):
    sid, owner, _, _ = setup(client)
    iv(client, owner, sid, type="ADD_CONSTRAINT", action="INCLUDE_SOURCE", target="Wikipedia")
    kinds = [i["kind"] for i in client.get(f"/sessions/{sid}/memory", headers=owner).json()["items"]]
    assert kinds == ["APPROVED_SOURCE"]


def test_approvals_and_reviews_need_a_running_agent(client):
    sid, owner, _, _ = setup(client)
    assert iv(client, owner, sid, type="APPROVE").status_code == 409
    assert iv(client, owner, sid, type="REJECT", content="no").status_code == 409
    assert iv(client, owner, sid, type="REQUEST_REVIEW").status_code == 409


def test_pause_and_resume_interventions_use_the_state_machine(client):
    sid, owner, editor, _ = setup(client)
    assert iv(client, owner, sid, type="PAUSE").status_code == 409  # not running yet
    client.post(f"/sessions/{sid}/start", headers=owner)
    assert iv(client, editor, sid, type="PAUSE").status_code == 201
    assert client.get(f"/sessions/{sid}", headers=owner).json()["status"] == "PAUSED"
    assert iv(client, editor, sid, type="RESUME").status_code == 201
    assert client.get(f"/sessions/{sid}", headers=owner).json()["status"] == "RUNNING"


def test_finished_sessions_only_accept_comments(client):
    sid, owner, _, _ = setup(client)
    client.post(f"/sessions/{sid}/start", headers=owner)
    client.post(f"/sessions/{sid}/stop", headers=owner)
    assert iv(client, owner, sid, type="CORRECT", content="too late now").status_code == 409
    assert iv(client, owner, sid, type="COMMENT", content="thanks everyone").status_code == 201