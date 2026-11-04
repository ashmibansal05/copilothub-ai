import asyncio
import uuid

from app.agents.brain import AgentBrain, Evaluation, StepResult
from app.models.session import AgentSession, AgentStatus

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


def make_running_session(client) -> uuid.UUID:
    """A session already in RUNNING state, for driving the orchestrator directly."""
    headers, _ = make_user(client, "owner")
    session = create_session(client, headers)
    sid = uuid.UUID(session["id"])
    with client.session_factory() as db:
        row = db.get(AgentSession, sid)
        row.status = AgentStatus.RUNNING
        db.commit()
    return sid


class ScriptedBrain(AgentBrain):
    """Configurable brain for orchestrator tests."""

    engine = "scripted"
    description = "test brain"
    simulated = True

    def __init__(self, steps=5, delay=0.0, fail_first=0, fail_always=False):
        self.steps = steps
        self.delay = delay
        self.failures_left = fail_first
        self.fail_always = fail_always
        self.calls = 0

    async def make_plan(self, task, constraints, max_steps):
        return [f"step {i + 1}" for i in range(self.steps)]

    def tool_for_step(self, step):
        return "test_tool"

    async def execute_step(self, task, step, history, constraints):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_always or self.failures_left > 0:
            self.failures_left -= 1
            raise RuntimeError("boom")
        return StepResult(tool="test_tool", output=f"done {step}", simulated=True)

    async def evaluate(self, task, step, result, history):
        return Evaluation(confidence=0.8, ok=True)

    async def summarize(self, task, history):
        return "summary"

    def factory(self):
        async def _factory():
            return self, None

        return _factory