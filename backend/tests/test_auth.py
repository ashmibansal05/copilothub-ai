PASSWORD = "StrongPass123"


def register(client, email="alice@example.com", username="alice", password=PASSWORD):
    return client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "full_name": "Alice Example",
            "password": password,
        },
    )


def login(client, email="alice@example.com", password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_success_defaults_to_editor(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "EDITOR"
    assert "password" not in body and "hashed_password" not in body


def test_register_cannot_choose_role(client):
    r = client.post(
        "/auth/register",
        json={
            "email": "evil@example.com",
            "username": "evil",
            "full_name": "Evil",
            "password": PASSWORD,
            "role": "OWNER",
        },
    )
    assert r.status_code == 201
    assert r.json()["role"] == "EDITOR"


def test_register_duplicate_email(client):
    register(client)
    r = register(client, username="alice2")
    assert r.status_code == 409


def test_register_duplicate_username(client):
    register(client)
    r = register(client, email="other@example.com")
    assert r.status_code == 409


def test_register_weak_password(client):
    assert register(client, password="short1").status_code == 422
    assert register(client, password="onlyletters").status_code == 422


def test_login_and_me(client):
    register(client)
    r = login(client)
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_login_wrong_password(client):
    register(client)
    assert login(client, password="WrongPass123").status_code == 401


def test_login_unknown_user(client):
    assert login(client, email="nobody@example.com").status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401