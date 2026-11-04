import os

# Must be set BEFORE importing the app (settings are read at import time).
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-1234567890"
os.environ["DEMO_MODE"] = "true"
os.environ["AGENT_STEP_DELAY_SECONDS"] = "0"
os.environ["AGENT_RETRY_BACKOFF_SECONDS"] = "0"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.runner import agent_runner
from app.db.base import Base
from app.db.session import get_db
from app.main import app
import app.models  # noqa: F401


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # A file database (not shared in-memory): the agent runs in a background task
    # next to request handlers, and each of them needs its own connection.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Code that opens its own DB sessions (WebSocket auth, the agent) must use the test DB too.
    monkeypatch.setattr("app.db.session.SessionLocal", TestingSession)
    monkeypatch.setattr("app.websocket.routes.SessionLocal", TestingSession)

    with TestClient(app) as c:
        c.session_factory = TestingSession  # handy for tests that inspect the DB
        yield c

    app.dependency_overrides.clear()
    agent_runner._tasks.clear()
    agent_runner._orchestrators.clear()
    engine.dispose()


@pytest.fixture()
def disable_agent(monkeypatch):
    """For tests of the Phase 3-4 control plane: 'start' must not launch the agent."""

    async def _noop(session_id):
        return False

    monkeypatch.setattr(agent_runner, "start", _noop)