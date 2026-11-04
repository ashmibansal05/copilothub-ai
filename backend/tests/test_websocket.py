import pytest
from helpers import create_session, join, make_user
from starlette.websockets import WebSocketDisconnect


pytestmark = pytest.mark.usefixtures("disable_agent")


def open_ws(client, session_id):
    return client.websocket_connect(f"/ws/sessions/{session_id}")


def test_ws_rejects_bad_token(client):
    h, _ = make_user(client, "owner")
    s = create_session(client, h)
    with open_ws(client, s["id"]) as ws:
        ws.send_json({"type": "AUTH", "token": "garbage"})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_ws_rejects_non_member(client):
    owner_h, _ = make_user(client, "owner")
    _, stranger_token = make_user(client, "stranger")
    s = create_session(client, owner_h)
    with open_ws(client, s["id"]) as ws:
        ws.send_json({"type": "AUTH", "token": stranger_token})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4403


def test_ws_rejects_wrong_first_message(client):
    h, token = make_user(client, "owner")
    s = create_session(client, h)
    with open_ws(client, s["id"]) as ws:
        ws.send_json({"type": "PING"})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_ws_connected_event_and_ping(client):
    h, token = make_user(client, "owner")
    s = create_session(client, h)
    with open_ws(client, s["id"]) as ws:
        ws.send_json({"type": "AUTH", "token": token})
        msg = ws.receive_json()
        assert msg["type"] == "CONNECTED"
        assert msg["payload"]["my_role"] == "OWNER"
        assert msg["payload"]["status"] == "CREATED"
        assert [u["username"] for u in msg["payload"]["online_users"]] == ["owner"]
        ws.send_json({"type": "PING"})
        assert ws.receive_json()["type"] == "PONG"


def test_ws_viewer_receives_lifecycle_events(client):
    owner_h, _ = make_user(client, "owner")
    viewer_h, viewer_token = make_user(client, "viewer1")
    s = create_session(client, owner_h)
    join(client, viewer_h, s["viewer_code"])

    with open_ws(client, s["id"]) as ws:
        ws.send_json({"type": "AUTH", "token": viewer_token})
        assert ws.receive_json()["payload"]["my_role"] == "VIEWER"

        assert client.post(f"/sessions/{s['id']}/start", headers=owner_h).status_code == 200
        types = [ws.receive_json()["type"] for _ in range(3)]
        assert types == ["AGENT_STARTED", "STATUS_CHANGED", "AGENT_MESSAGE"]

        client.post(f"/sessions/{s['id']}/pause", headers=owner_h)
        types = [ws.receive_json()["type"] for _ in range(3)]
        assert types == ["PAUSED", "STATUS_CHANGED", "AGENT_MESSAGE"]


def test_ws_presence_join_and_leave(client):
    owner_h, owner_token = make_user(client, "owner")
    viewer_h, viewer_token = make_user(client, "viewer1")
    s = create_session(client, owner_h)
    join(client, viewer_h, s["viewer_code"])

    with open_ws(client, s["id"]) as ws_owner:
        ws_owner.send_json({"type": "AUTH", "token": owner_token})
        ws_owner.receive_json()  # CONNECTED

        with open_ws(client, s["id"]) as ws_viewer:
            ws_viewer.send_json({"type": "AUTH", "token": viewer_token})
            ws_viewer.receive_json()  # CONNECTED
            joined = ws_owner.receive_json()
            assert joined["type"] == "USER_JOINED"
            assert joined["payload"]["user"]["username"] == "viewer1"

        left = ws_owner.receive_json()
        assert left["type"] == "USER_LEFT"
        assert left["payload"]["user"]["username"] == "viewer1"