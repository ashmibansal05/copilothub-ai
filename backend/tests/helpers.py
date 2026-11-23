
import asyncio
import io
import time
import uuid

from app.agents.brain import AgentBrain, Evaluation, StepResult
from app.models.session import AgentSession, AgentStatus
from app.agents.brain import FinalAnswer, ToolCall

PASSWORD = "StrongPass123"


def make_user(client, username: str) -> tuple[dict, str]:
    """Register + log in. Returns (auth headers, raw token)."""
    email = f"{username}@example.com"
    client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "full_name": username.title(),
            "password": PASSWORD,
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": email, "password": PASSWORD},
    ).json()["access_token"]

    return {"Authorization": f"Bearer {token}"}, token


def create_session(
    client,
    headers,
    name="Cloud research",
    task="Prepare a report comparing AWS, Azure and Google Cloud",
):
    r = client.post(
        "/sessions",
        json={"name": name, "task": task},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def join(client, headers, code):
    return client.post(
        "/sessions/join",
        json={"code": code},
        headers=headers,
    )


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
    {
        "title": "Cloud overview",
        "publisher": "Wikipedia",
        "source_type": "encyclopedia",
        "simulated": True,
    },
    {
        "title": "Pricing docs",
        "publisher": "ProviderCo",
        "source_type": "official documentation",
        "simulated": True,
    },
]


def read_until(ws, stop_types, limit=400):
    """Read WebSocket events until one of `stop_types`; returns the list of types seen."""
    seen = []

    for _ in range(limit):
        event = ws.receive_json()
        seen.append(event["type"])

        if event["type"] in stop_types:
            return seen

    raise AssertionError(
        f"Did not see {stop_types}; last events: {seen[-10:]}"
    )


class ScriptedBrain(AgentBrain):
    """Configurable brain for orchestrator tests."""

    engine = "scripted"
    description = "test brain"
    simulated = True

    # Phase 14: optional override for report narrative testing
    report_text = None

    def __init__(
        self,
        steps=5,
        delay=0.0,
        fail_first=0,
        fail_always=False,
        with_sources=False,
        on_call=None,
    ):
        self.steps = steps
        self.delay = delay
        self.failures_left = fail_first
        self.fail_always = fail_always
        self.with_sources = with_sources
        self.on_call = on_call

        self.calls = 0
        self.plan_tasks = []
        self.summarize_notes = []
        self.summarize_history = None

        # Phase 10: Record retrieved documents passed to the agent
        self.documents_seen = []

    async def make_plan(self, task, constraints, max_steps, notes=None):
        self.plan_tasks.append(task)
        return [f"step {i + 1}" for i in range(self.steps)]

    def tool_for_step(self, step):
        return "test_tool"

    async def execute_step(
        self,
        task,
        step,
        history,
        constraints,
        notes=None,
        documents=None,
    ):
        self.calls += 1

        # Phase 10: Track document context received at each step
        self.documents_seen.append(documents)

        if self.on_call:
            self.on_call(self.calls)

        if self.delay:
            await asyncio.sleep(self.delay)

        if self.fail_always or self.failures_left > 0:
            self.failures_left -= 1
            raise RuntimeError("boom")

        sources = (
            [dict(s) for s in SOURCES]
            if self.with_sources
            else []
        )

        return StepResult(
            tool="test_tool",
            output=f"done {step}",
            sources=sources,
            simulated=True,
        )

    async def evaluate(self, task, step, result, history):
        return Evaluation(
            confidence=0.8,
            ok=True,
        )

    async def summarize(
        self,
        task,
        history,
        constraints=None,
        notes=None,
    ):
        self.summarize_notes.append(list(notes or []))
        self.summarize_history = history
        return "summary"

    # ============================================================
    # Phase 14: Final Report Narrative Override
    # ============================================================

    async def write_report(
        self,
        task,
        history,
        constraints=None,
        notes=None,
    ):
        if self.report_text is not None:
            return {
                "executive_summary": self.report_text,
                "findings": "",
                "comparison": "",
                "conclusion": "",
            }

        return await super().write_report(
            task,
            history,
            constraints,
            notes,
        )

    def factory(self):
        async def _factory():
            return self, None

        return _factory


# ============================================================
# Phase 10: RAG Document Test Helpers
# ============================================================

def make_pdf(text: str) -> bytes:
    """A minimal valid one-page PDF containing text, without external libraries."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )

    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = b"%PDF-1.4\n"
    offsets = []

    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"

    out += b"".join(
        f"{offset:010d} 00000 n \n".encode()
        for offset in offsets
    )

    out += (
        f"trailer\n"
        f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()

    return out


def make_docx(*paragraphs: str) -> bytes:
    """Create a DOCX document in memory for upload tests."""
    import docx

    document = docx.Document()

    for text in paragraphs:
        document.add_paragraph(text)

    buffer = io.BytesIO()
    document.save(buffer)

    return buffer.getvalue()


def upload(
    client,
    headers,
    sid,
    name="notes.txt",
    content=b"hello world",
    content_type="text/plain",
    **form,
):
    """Upload a document to a session."""
    return client.post(
        f"/sessions/{sid}/documents",
        headers=headers,
        files={
            "file": (name, content, content_type)
        },
        data=form,
    )


def wait_ready(
    client,
    headers,
    sid,
    doc_id,
    timeout=20.0,
):
    """Wait until a document finishes processing or fails."""
    deadline = time.time() + timeout

    while time.time() < deadline:
        docs = client.get(
            f"/sessions/{sid}/documents",
            headers=headers,
        ).json()

        doc = next(
            d for d in docs
            if d["id"] == doc_id
        )

        if doc["status"] != "PROCESSING":
            return doc

        time.sleep(0.1)

    raise AssertionError("document is still processing")


class ScriptedToolBrain(AgentBrain):
    """A brain that speaks the tool protocol from a fixed script (one action per call)."""

    engine = "scripted-tools"
    description = "scripted tool brain"
    simulated = True
    uses_tools = True

    def __init__(self, actions_per_step, final="findings", steps=1):
        self.actions_per_step = list(actions_per_step)
        self.final = final
        self.steps = steps
        self.seen_observations = []
        self.force_flags = []

    async def make_plan(self, task, constraints, max_steps, notes=None):
        return [f"step {i + 1}" for i in range(self.steps)]

    def tool_for_step(self, step):
        return "scripted"

    async def next_action(
        self,
        task,
        step,
        observations,
        constraints,
        notes=None,
        tools=(),
        force_final=False,
    ):
        self.seen_observations.append(
            [(o.tool, o.ok, o.output) for o in observations]
        )
        self.force_flags.append(force_final)

        if force_final or len(observations) >= len(self.actions_per_step):
            return FinalAnswer(self.final)

        return self.actions_per_step[len(observations)]

    async def execute_step(self, *a, **k):
        raise AssertionError("single-shot path must not be used in tool mode")

    async def evaluate(self, task, step, result, history):
        return Evaluation(confidence=0.8, ok=True)

    async def summarize(self, task, history, constraints=None, notes=None):
        return "summary"

    def factory(self):
        async def _factory():
            return self, None

        return _factory