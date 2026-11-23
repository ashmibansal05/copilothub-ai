import os
import tempfile

# These must be set BEFORE the app is imported (settings are read once). They also PIN every
# setting the tests rely on, so a developer's own backend/.env cannot change test behaviour.
os.environ.update({
    "DATA_DIR": tempfile.mkdtemp(prefix="copilothub-test-"),
    "DATABASE_URL": "sqlite://",
    "SECRET_KEY": "test-secret-key-test-secret-key-1234567890",
    "ENVIRONMENT": "development",
    "DEMO_MODE": "true",
    "EMBEDDING_BACKEND": "hashing",  # no model download in tests
    "LLM_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "qwen3",
    "WEB_SEARCH_PROVIDER": "demo",
    "SEARXNG_URL": "",
    "AGENT_STEP_DELAY_SECONDS": "0",
    "AGENT_RETRY_BACKOFF_SECONDS": "0",
    "AGENT_MAX_STEPS": "8",
    "AGENT_MAX_RETRIES": "2",
    "AGENT_STEP_TIMEOUT_SECONDS": "180",
    "AGENT_MAX_RUNTIME_SECONDS": "900",
    "AGENT_MAX_APPROVAL_ROUNDS": "3",
    "AGENT_MAX_REPLANS": "3",
    "AGENT_MAX_TOOL_CALLS_PER_STEP": "3",
    "AGENT_MAX_TOOL_CALLS_PER_RUN": "40",
    "AGENT_ENABLED_TOOLS": "",
    "AGENT_REQUIRE_FINAL_APPROVAL": "false",  # tests switch these on where needed
    "AGENT_TOOLS_ENABLED": "false",
    "AGENT_GENERATE_FINAL_REPORT": "false",
    "RISK_PREDICTION_ENABLED": "false",
    "RATE_LIMIT_ENABLED": "false",
    "NLP_AUTO_APPLY": "true",
    "NLP_AUTO_TRAIN": "true",
    "RISK_AUTO_TRAIN": "true",
    "MAX_UPLOAD_MB": "10",
    "MAX_DOCUMENTS_PER_SESSION": "20",
    "MAX_REPORTS_PER_SESSION": "5",
    "MAX_FINAL_REPORTS_PER_SESSION": "5",
    "CLEANUP_ORPHANS_ON_START": "false",
    "TOOL_TIMEOUT_SECONDS": "30",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
    "CORS_ORIGINS": "http://localhost:5173",
})

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.agents.runner import agent_runner
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app
import app.models  # noqa: F401


@pytest.fixture()
def client(monkeypatch, tmp_path, request):
    # A file database (not shared in-memory): the agent runs in a background task
    # next to request handlers, and each of them needs its own connection.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    if request.node.get_closest_marker("fk"):  # tests of ON DELETE CASCADE need real foreign keys

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    # Code that opens its own DB sessions (WebSocket auth, the agent) must use the test DB too.
    monkeypatch.setattr("app.db.session.SessionLocal", TestingSession)
    monkeypatch.setattr("app.websocket.routes.SessionLocal", TestingSession)

    with TestClient(fastapi_app) as c:
        c.session_factory = TestingSession  # handy for tests that inspect the DB
        yield c

    fastapi_app.dependency_overrides.clear()
    agent_runner._tasks.clear()
    agent_runner._orchestrators.clear()
    engine.dispose()


@pytest.fixture()
def disable_agent(monkeypatch):
    """For tests of the control plane: 'start' must not launch the agent."""

    async def _noop(session_id):
        return False

    monkeypatch.setattr(agent_runner, "start", _noop)


@pytest.fixture()
def set_brain(monkeypatch):
    """Replace the agent's brain for the duration of one test."""

    def _set(brain):
        monkeypatch.setattr(agent_runner, "brain_factory", brain.factory())

    return _set


@pytest.fixture()
def tools_on(monkeypatch):
    """Enable the tool loop for one test (conftest turns it off by default)."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "agent_tools_enabled", True)


@pytest.fixture()
def ml_sandbox(monkeypatch, tmp_path):
    """Isolated model files + a small synthetic training set, so ML tests are quick and clean."""
    from app.core.config import get_settings
    from app.ml import service as risk_service
    from app.ml import train as trainer

    monkeypatch.setattr(trainer, "model_dir", lambda: tmp_path)
    monkeypatch.setattr(get_settings(), "risk_synthetic_rows", 600)
    risk_service.reset_cache()
    yield tmp_path
    risk_service.reset_cache()


@pytest.fixture()
def rate_limits_on(monkeypatch):
    from app.api.limits import limiter
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    limiter.reset()
    yield
    limiter.reset()