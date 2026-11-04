from helpers import create_session, join, make_user


def test_create_session_owner_sees_codes(client):
    h, _ = make_user(client, "owner")
    s = create_session(client, h)
    assert s["my_role"] == "OWNER"
    assert s["status"] == "CREATED"
    assert len(s["editor_code"]) == 8 and len(s["viewer_code"]) == 8
    assert s["editor_code"] != s["viewer_code"]
    assert [m["username"] for m in s["members"]] == ["owner"]


def test_create_session_validation(client):
    h, _ = make_user(client, "owner")
    r = client.post("/sessions", json={"name": "x", "task": "short"}, headers=h)
    assert r.status_code == 422


def test_requires_auth(client):
    assert client.get("/sessions").status_code == 401
    assert client.post("/sessions", json={"name": "abc", "task": "a long enough task"}).status_code == 401


def test_join_roles_come_from_code(client):
    owner_h, _ = make_user(client, "owner")
    ed_h, _ = make_user(client, "editor1")
    vw_h, _ = make_user(client, "viewer1")
    s = create_session(client, owner_h)

    r = join(client, ed_h, s["editor_code"])
    assert r.status_code == 200 and r.json()["my_role"] == "EDITOR"
    r = join(client, vw_h, s["viewer_code"])
    assert r.status_code == 200 and r.json()["my_role"] == "VIEWER"

    detail = client.get(f"/sessions/{s['id']}", headers=owner_h).json()
    assert {m["username"]: m["role"] for m in detail["members"]} == {
        "owner": "OWNER", "editor1": "EDITOR", "viewer1": "VIEWER",
    }


def test_codes_hidden_from_non_owners(client):
    owner_h, _ = make_user(client, "owner")
    ed_h, _ = make_user(client, "editor1")
    s = create_session(client, owner_h)
    join(client, ed_h, s["editor_code"])
    detail = client.get(f"/sessions/{s['id']}", headers=ed_h).json()
    assert detail["editor_code"] is None and detail["viewer_code"] is None


def test_join_invalid_code(client):
    h, _ = make_user(client, "someone")
    assert join(client, h, "ZZZZZZZZ").status_code == 404
    assert client.post("/sessions/join", json={"code": "!!"}, headers=h).status_code == 422


def test_join_is_idempotent_and_never_downgrades_owner(client):
    owner_h, _ = make_user(client, "owner")
    s = create_session(client, owner_h)
    r = join(client, owner_h, s["viewer_code"])
    assert r.status_code == 200 and r.json()["my_role"] == "OWNER"


def test_non_member_gets_404(client):
    owner_h, _ = make_user(client, "owner")
    other_h, _ = make_user(client, "stranger")
    s = create_session(client, owner_h)
    assert client.get(f"/sessions/{s['id']}", headers=other_h).status_code == 404
    assert client.get(f"/sessions/{s['id']}/events", headers=other_h).status_code == 404
    assert client.post(f"/sessions/{s['id']}/start", headers=other_h).status_code == 404


def test_list_only_my_sessions(client):
    a_h, _ = make_user(client, "alice")
    b_h, _ = make_user(client, "bob")
    create_session(client, a_h, name="Alice session")
    create_session(client, b_h, name="Bob session")
    names = [s["name"] for s in client.get("/sessions", headers=a_h).json()]
    assert names == ["Alice session"]


def test_invite_preview(client):
    owner_h, _ = make_user(client, "owner")
    guest_h, _ = make_user(client, "guest")
    s = create_session(client, owner_h)
    p = client.get(f"/sessions/invite/{s['viewer_code']}", headers=guest_h).json()
    assert p["role"] == "VIEWER" and p["already_member"] is False and p["session_id"] is None
    assert client.get("/sessions/invite/NOPE1234", headers=guest_h).status_code == 404


def test_lifecycle_permissions_and_transitions(client):
    owner_h, _ = make_user(client, "owner")
    ed_h, _ = make_user(client, "editor1")
    vw_h, _ = make_user(client, "viewer1")
    s = create_session(client, owner_h)
    join(client, ed_h, s["editor_code"])
    join(client, vw_h, s["viewer_code"])
    sid = s["id"]

    # only the owner may start
    assert client.post(f"/sessions/{sid}/start", headers=vw_h).status_code == 403
    assert client.post(f"/sessions/{sid}/start", headers=ed_h).status_code == 403
    r = client.post(f"/sessions/{sid}/start", headers=owner_h)
    assert r.status_code == 200 and r.json()["status"] == "RUNNING"

    # invalid transition
    assert client.post(f"/sessions/{sid}/start", headers=owner_h).status_code == 409
    assert client.post(f"/sessions/{sid}/resume", headers=owner_h).status_code == 409

    # viewer cannot pause, editor can
    assert client.post(f"/sessions/{sid}/pause", headers=vw_h).status_code == 403
    assert client.post(f"/sessions/{sid}/pause", headers=ed_h).json()["status"] == "PAUSED"
    assert client.post(f"/sessions/{sid}/resume", headers=ed_h).json()["status"] == "RUNNING"

    # editor cannot stop, owner can
    assert client.post(f"/sessions/{sid}/stop", headers=ed_h).status_code == 403
    assert client.post(f"/sessions/{sid}/stop", headers=owner_h).json()["status"] == "CANCELLED"


def test_events_are_persisted(client):
    h, _ = make_user(client, "owner")
    s = create_session(client, h)
    client.post(f"/sessions/{s['id']}/start", headers=h)
    events = client.get(f"/sessions/{s['id']}/events", headers=h).json()
    assert {e["type"] for e in events} == {"AGENT_STARTED", "STATUS_CHANGED", "AGENT_MESSAGE"}