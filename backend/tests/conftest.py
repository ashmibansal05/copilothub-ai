
import os
import tempfile

# ============================================================
# Test Environment Configuration
# Must be set BEFORE importing the application.
# ============================================================

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="copilothub-test-")
os.environ["EMBEDDING_BACKEND"] = "hashing"  # No model downloads during tests

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-1234567890"
os.environ["DEMO_MODE"] = "true"

os.environ["AGENT_STEP_DELAY_SECONDS"] = "0"
os.environ["AGENT_RETRY_BACKOFF_SECONDS"] = "0"

# Earlier phases use single-shot execution by default.
os.environ["AGENT_TOOLS_ENABLED"] = "false"

# Allow tests to complete without manual approval.
os.environ["AGENT_REQUIRE_FINAL_APPROVAL"] = "false"

# ============================================================
# Phase 13: Risk Prediction
# ============================================================

# Disabled globally; individual tests can enable it.
os.environ["RISK_PREDICTION_ENABLED"] = "false"

# Do not automatically train during normal test startup.
# The ml_sandbox fixture enables training for ML-specific tests.
os.environ["RISK_AUTO_TRAIN"] = "false"

# ============================================================
# Phase 14: Final Reports
# ============================================================

# Disabled globally; report tests can enable it explicitly.
os.environ["AGENT_GENERATE_FINAL_REPORT"] = "false"


# ============================================================
# Imports
# ============================================================

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.runner import agent_runner
from app.db.base import Base
from app.db.session import get_db

import app.models  # noqa: F401

from app.main import app


# ============================================================
# Database and Test Client
# ============================================================

@pytest.fixture()
def client(monkeypatch, tmp_path):
    """
    Create an isolated SQLite database for each test.

    A file-based database is required because the agent runs
    in a background task alongside HTTP request handlers.
    """

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(engine)

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    def override_get_db():
        db = TestingSession()

        try:
            yield db
        finally:
            db.close()

    # Override API database dependency.
    app.dependency_overrides[get_db] = override_get_db

    # Ensure background services and WebSockets use the test DB.
    monkeypatch.setattr(
        "app.db.session.SessionLocal",
        TestingSession,
    )

    monkeypatch.setattr(
        "app.websocket.routes.SessionLocal",
        TestingSession,
    )

    with TestClient(app) as c:
        # Allow tests to inspect database records.
        c.session_factory = TestingSession
        yield c

    # Clean up after each test.
    app.dependency_overrides.clear()
    agent_runner._tasks.clear()
    agent_runner._orchestrators.clear()

    engine.dispose()


# ============================================================
# Agent Control Fixtures
# ============================================================

@pytest.fixture()
def disable_agent(monkeypatch):
    """
    Prevent the agent from starting during tests that only
    exercise the session control API.
    """

    async def _noop(session_id):
        return False

    monkeypatch.setattr(agent_runner, "start", _noop)


@pytest.fixture()
def set_brain(monkeypatch):
    """
    Replace the agent brain for the duration of a test.
    """

    def _set(brain):
        monkeypatch.setattr(
            agent_runner,
            "brain_factory",
            brain.factory(),
        )

    return _set


@pytest.fixture()
def tools_on(monkeypatch):
    """
    Enable the agent tool loop for tests that need it.
    """

    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(),
        "agent_tools_enabled",
        True,
    )


# ============================================================
# Phase 13: ML Sandbox Fixture
# ============================================================

@pytest.fixture()
def ml_sandbox(monkeypatch, tmp_path):
    """
    Isolate ML model artifacts and enable synthetic training
    for tests that use this fixture.

    Normal application settings remain unchanged.
    """

    from app.core.config import get_settings
    from app.ml import service as risk_service
    from app.ml import train as trainer

    # Store model artifacts in a temporary test directory.
    monkeypatch.setattr(
        trainer,
        "model_dir",
        lambda: tmp_path,
    )

    settings = get_settings()

    # Keep synthetic training fast.
    monkeypatch.setattr(
        settings,
        "risk_synthetic_rows",
        600,
    )

    # Enable automatic training within this test fixture.
    monkeypatch.setattr(
        settings,
        "risk_auto_train",
        True,
    )

    # Ensure no model is cached from an earlier test.
    risk_service.reset_cache()

    yield tmp_path

    # Clear cached model after the test.
    risk_service.reset_cache()
