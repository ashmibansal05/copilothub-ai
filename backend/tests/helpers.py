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


SOURCES = [
    {"title": "Cloud overview", "publisher": "Wikipedia", "source_type": "encyclopedia", "simulated": True},
    {"title": "Pricing docs", "publisher": "ProviderCo", "source_type": "official documentation", "simulated": True},
]


def read_until(ws, stop_types, limit=400):
    """Read WebSocket events until one of `stop_types`; returns the list of types seen."""
    seen = []
    for _ in range(limit):
        event = ws.receive_json()
        seen.append(event["type"])
        if event["type"] in stop_types:
            return seen
    raise AssertionError(f"Did not see {stop_types}; last events: {seen[-10:]}")


class ScriptedBrain(AgentBrain):
    """Configurable brain for orchestrator tests."""

    engine = "scripted"
    description = "test brain"
    simulated = True

    def __init__(self, steps=5, delay=0.0, fail_first=0, fail_always=False, with_sources=False, on_call=None):
        self.steps = steps
        self.delay = delay
        self.failures_left = fail_first
        self.fail_always = fail_always
        self.with_sources = with_sources
        self.on_call = on_call  # called with the execute_step call number (sync)
        self.calls = 0
        self.plan_tasks = []
        self.summarize_notes = []
        self.summarize_history = None

    async def make_plan(self, task, constraints, max_steps, notes=None):
        self.plan_tasks.append(task)
        return [f"step {i + 1}" for i in range(self.steps)]

    def tool_for_step(self, step):
        return "test_tool"

    async def execute_step(self, task, step, history, constraints, notes=None):
        self.calls += 1
        if self.on_call:
            self.on_call(self.calls)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_always or self.failures_left > 0:
            self.failures_left -= 1
            raise RuntimeError("boom")
        sources = [dict(s) for s in SOURCES] if self.with_sources else []
        return StepResult(tool="test_tool", output=f"done {step}", sources=sources, simulated=True)

    async def evaluate(self, task, step, result, history):
        return Evaluation(confidence=0.8, ok=True)

    async def summarize(self, task, history, constraints=None, notes=None):
        self.summarize_notes.append(list(notes or []))
        self.summarize_history = history
        return "summary"

    def factory(self):
        async def _factory():
            return self, None

        return _factory