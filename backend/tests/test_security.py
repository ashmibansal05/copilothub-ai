import time
import uuid

import jwt
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from starlette.websockets import WebSocketDisconnect

from app.api.limits import limiter
from app.core.config import Settings, get_settings
from app.models.document import Document
from app.models.session import SessionMember
from app.services import cleanup
from helpers import PASSWORD, create_session, join, make_user, upload, wait_ready


# ---------------------------------------------------------------- headers, size, production guard
def test_security_headers_on_api_responses_but_not_on_the_docs(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "strict-transport-security" not in r.headers  # development
    docs = client.get("/docs")
    assert docs.status_code == 200 and "content-security-policy" not in docs.headers  # Swagger needs its scripts


def test_oversized_requests_are_rejected_before_parsing(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    r = client.post("/auth/login", content=b"x" * (3 * 1024 * 1024), headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["detail"] == "Request body too large"


def test_cors_allows_only_the_configured_origin(client):
    ok = client.options("/auth/login", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/auth/login", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_production_refuses_a_placeholder_secret():
    kwargs = dict(_env_file=None, database_url="sqlite://", environment="production")
    with pytest.raises(ValidationError, match="real SECRET_KEY"):
        Settings(secret_key="replace_with_a_long_random_string_at_least_32_chars", **kwargs)
    with pytest.raises(ValidationError):
        Settings(secret_key="change_me_" + "x" * 30, **kwargs)
    assert Settings(secret_key="k" * 48, **kwargs).environment == "production"


# ---------------------------------------------------------------- rate limits
def test_login_attempts_are_limited_per_account(client, rate_limits_on):
    make_user(client, "alice")
    limiter.reset()
    wrong = {"email": "alice@example.com", "password": "WrongPass123"}
    for _ in range(8):
        assert client.post("/auth/login", json=wrong).status_code == 401
    blocked = client.post("/auth/login", json=wrong)
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1
    assert "Too many requests" in blocked.json()["detail"]
    # other accounts are not affected
    assert client.post("/auth/login", json={"email": "nobody@example.com", "password": "WrongPass123"}).status_code == 401
    limiter.reset()
    assert client.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 200


def test_registration_is_limited_per_ip(client, rate_limits_on):
    for n in range(10):
        body = {"email": f"user{n}@example.com", "username": f"user{n}", "full_name": "User", "password": PASSWORD}
        assert client.post("/auth/register", json=body).status_code == 201
    extra = {"email": "user11@example.com", "username": "user11", "full_name": "User", "password": PASSWORD}
    assert client.post("/auth/register", json=extra).status_code == 429


def test_guessing_invite_codes_is_limited(client, rate_limits_on):
    headers, _ = make_user(client, "guesser")
    limiter.reset()
    for _ in range(20):
        assert client.post("/sessions/join", json={"code": "ZZZZZZZZ"}, headers=headers).status_code == 404
    assert client.post("/sessions/join", json={"code": "ZZZZZZZZ"}, headers=headers).status_code == 429


def test_the_limiter_forgets_after_its_window():
    from app.api.limits import RateLimiter

    small = RateLimiter()
    assert small.check("k", 2, 0.2) is None and small.check("k", 2, 0.2) is None
    assert small.check("k", 2, 0.2) > 0
    time.sleep(0.25)
    assert small.check("k", 2, 0.2) is None


# ---------------------------------------------------------------- passwords and tokens
def test_changing_the_password_revokes_old_tokens(client):
    headers, _ = make_user(client, "alice")
    time.sleep(1.1)  # JWT timestamps have one-second resolution
    new = "NewStrong456"
    url = "/auth/change-password"
    assert client.post(url, json={"current_password": "WrongPass123", "new_password": new}, headers=headers).status_code == 400
    assert client.post(url, json={"current_password": PASSWORD, "new_password": PASSWORD}, headers=headers).status_code == 400
    assert client.post(url, json={"current_password": PASSWORD, "new_password": "short1"}, headers=headers).status_code == 422
    assert client.post(url, json={"current_password": PASSWORD, "new_password": "onlyletters"}, headers=headers).status_code == 422

    changed = client.post(url, json={"current_password": PASSWORD, "new_password": new}, headers=headers)
    assert changed.status_code == 200
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/auth/me", headers=headers).status_code == 401  # the old token is dead
    assert client.get("/auth/me", headers=fresh).status_code == 200  # the new one works

    login = lambda password: client.post("/auth/login", json={"email": "alice@example.com", "password": password})  # noqa: E731
    assert login(PASSWORD).status_code == 401 and login(new).status_code == 200
    assert client.post(url, json={"current_password": new, "new_password": "Another789"}).status_code == 401


def test_a_websocket_closes_when_its_token_expires(client):
    headers, _ = make_user(client, "owner")
    s = create_session(client, headers)
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    now = int(time.time())
    settings = get_settings()
    short_lived = jwt.encode(
        {"sub": user_id, "type": "access", "iat": now, "exp": now + 4}, settings.secret_key, algorithm=settings.jwt_algorithm
    )
    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": short_lived})
        assert ws.receive_json()["type"] == "CONNECTED"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4401


def test_a_websocket_refuses_tokens_issued_before_a_password_change(client):
    headers, old_token = make_user(client, "owner")
    s = create_session(client, headers)
    time.sleep(1.1)
    client.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": "NewStrong456"}, headers=headers)
    with client.websocket_connect(f"/ws/sessions/{s['id']}") as ws:
        ws.send_json({"type": "AUTH", "token": old_token})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4401


# ---------------------------------------------------------------- deleting data
@pytest.mark.fk
def test_deleting_a_session_removes_everything_it_stored(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "data"))
    owner, _ = make_user(client, "owner")
    editor, _ = make_user(client, "editor1")
    stranger, _ = make_user(client, "stranger")
    s = create_session(client, owner)
    sid = s["id"]
    join(client, editor, s["editor_code"])
    doc = upload(client, owner, sid, name="notes.txt", content=b"Cloud pricing notes for a small startup team.").json()
    wait_ready(client, owner, sid, doc["id"])
    folder = get_settings().data_path / "documents" / sid
    index = get_settings().data_path / "embeddings" / f"{sid}.faiss"
    assert folder.exists() and index.exists()

    assert client.delete(f"/sessions/{sid}", headers=editor).status_code == 403  # owner only
    assert client.delete(f"/sessions/{sid}", headers=stranger).status_code == 404
    assert client.delete(f"/sessions/{sid}", headers=owner).status_code == 204

    assert client.get(f"/sessions/{sid}", headers=owner).status_code == 404
    assert not folder.exists() and not index.exists()
    with client.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Document).where(Document.session_id == uuid.UUID(sid))) == 0
        assert db.scalar(select(func.count()).select_from(SessionMember).where(SessionMember.session_id == uuid.UUID(sid))) == 0


def test_orphaned_files_are_found_and_purged_but_nothing_else(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "data"))
    owner, _ = make_user(client, "owner")
    s = create_session(client, owner)
    doc = upload(client, owner, s["id"], name="keep.txt", content=b"A real document that must be kept safe.").json()
    wait_ready(client, owner, s["id"], doc["id"])

    base = get_settings().data_path
    ghost = uuid.uuid4()
    (base / "documents" / str(ghost)).mkdir(parents=True)
    (base / "documents" / str(ghost) / "x.txt").write_text("x")
    (base / "embeddings" / f"{ghost}.faiss").write_bytes(b"x")
    (base / "documents" / "not-a-uuid").mkdir()  # unrelated: must be left alone

    with client.session_factory() as db:
        found = cleanup.find_orphans(db)
    assert {p.name for p in found} == {str(ghost), f"{ghost}.faiss"}
    assert cleanup.purge(found) == 2
    assert not (base / "documents" / str(ghost)).exists() and not (base / "embeddings" / f"{ghost}.faiss").exists()
    assert (base / "documents" / s["id"]).exists() and (base / "documents" / "not-a-uuid").exists()
    with client.session_factory() as db:
        assert cleanup.find_orphans(db) == []


def test_system_status_has_no_secrets(client):
    headers, _ = make_user(client, "owner")
    assert client.get("/system/status").status_code == 401
    status = client.get("/system/status", headers=headers).json()
    assert status["version"] and status["embedding_backend"] == "hashing" and len(status["enabled_tools"]) == 7
    assert status["llm"]["provider"] == "ollama"
    text = str(status).lower()
    assert "secret" not in text and "password" not in text and "postgresql" not in text