PASSWORD = "StrongPass123"


def make_user(client, username: str) -> tuple[dict, str]:
    """Register + log in. Returns (auth headers, raw token)."""
    email = f"{username}@example.com"
    client.post(
        "/auth/register",
        json={"email": email, "username": username, "full_name": username.title(), "password": PASSWORD},
    )
    token = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, token


def create_session(client, headers, name="Cloud research", task="Prepare a report comparing AWS, Azure and Google Cloud"):
    r = client.post("/sessions", json={"name": name, "task": task}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def join(client, headers, code):
    return client.post("/sessions/join", json={"code": code}, headers=headers)