"""Checks that every file of CoPilotHub AI exists.   Run from the project root:  python scripts/check_files.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BACKEND_APP = {
    "": ["__init__", "main", "maintenance"],
    "core": ["__init__", "config", "logging", "security", "middleware"],
    "db": ["__init__", "base", "session"],
    "models": ["__init__", "user", "session", "event", "agent", "intervention", "approval", "constraint", "memory",
               "conflict", "document", "source", "tool_execution", "report", "intent_sample", "risk_prediction",
               "analytics_record"],
    "schemas": ["__init__", "user", "auth", "session", "agent", "intervention", "conflict", "document", "tools",
                "nlp", "ml", "analytics", "system"],
    "services": ["__init__", "user_service", "session_service", "event_service", "session_control", "agent_service",
                 "readers", "approval_service", "constraint_manager", "memory_manager", "intervention_service",
                 "conflict_manager", "report_service", "report_export", "analytics_service", "cleanup"],
    "api": ["__init__", "deps", "limits", "router", "health", "auth", "sessions", "session_control", "agent",
            "interventions", "conflicts", "documents", "tools", "reports", "instructions", "risk", "analytics", "system"],
    "agents": ["__init__", "state", "prompts", "brain", "mock_brain", "llm_brain", "factory", "orchestrator", "runner"],
    "llm": ["__init__", "base", "utils", "ollama", "openai_compatible", "factory"],
    "rag": ["__init__", "embeddings", "vector_store", "extract", "chunking", "injection", "validation", "service", "tasks"],
    "tools": ["__init__", "base", "registry", "calc", "summarize", "demo_data", "web", "builtin"],
    "nlp": ["__init__", "dataset", "slots", "classifier", "policy", "feedback", "service", "train"],
    "ml": ["__init__", "features", "synthetic", "collector", "train", "service"],
    "websocket": ["__init__", "events", "manager", "routes"],
}
BACKEND_TESTS = ["conftest", "helpers", "seed", "test_auth", "test_sessions", "test_websocket", "test_agent", "test_llm",
                 "test_interventions", "test_constraints", "test_agent_controls", "test_conflicts", "test_rag_units",
                 "test_documents", "test_tools", "test_tools_agent", "test_nlp_slots", "test_nlp_classifier",
                 "test_instructions_api", "test_ml_features", "test_ml_training", "test_risk_api", "test_reports",
                 "test_analytics", "test_security", "test_integration_flow"]
MIGRATIONS = ["0001_create_users", "0002_sessions_and_events", "0003_agent_state_and_actions",
              "0004_interventions_approvals", "0005_constraints_memory", "0006_conflicts", "0007_documents_sources",
              "0008_tools_reports", "0009_intent_samples", "0010_risk_analytics", "0011_report_sections",
              "0012_password_changed_at"]

FRONTEND_SRC = {
    "": ["main.tsx", "App.tsx", "index.css", "vite-env.d.ts"],
    "types": ["index.ts"],
    "services": ["api.ts", "authService.ts", "sessionService.ts", "api.test.ts"],
    "contexts": ["AuthContext.tsx", "ToastContext.tsx", "ToastContext.test.tsx"],
    "hooks": ["useSessionSocket.ts"],
    "utils": ["agentState.ts", "agentState.test.ts", "labels.ts"],
    "layouts": ["AuthLayout.tsx", "AppLayout.tsx"],
    "components": ["ProtectedRoute.tsx", "ProtectedRoute.test.tsx", "ApiStatus.tsx", "StatusBadge.tsx",
                   "EventTimeline.tsx", "EventTimeline.test.tsx", "AgentPanel.tsx", "ToolActivity.tsx",
                   "InterventionDialog.tsx", "InterventionDialog.test.tsx", "ConstraintsPanel.tsx",
                   "InterventionsPanel.tsx", "MemoryPanel.tsx", "ApprovalCard.tsx", "ConflictCard.tsx",
                   "ConflictCard.test.tsx", "DocumentsPanel.tsx", "ReportsPanel.tsx", "InstructionBox.tsx",
                   "InstructionBox.test.tsx", "InstructionConfirmDialog.tsx", "RiskCard.tsx", "RiskCard.test.tsx",
                   "ErrorBoundary.tsx"],
    "pages": ["Landing.tsx", "Login.tsx", "Register.tsx", "Dashboard.tsx", "CreateSession.tsx", "JoinSession.tsx",
              "SessionWorkspace.tsx", "ReportViewer.tsx", "AnalyticsOverview.tsx", "SessionAnalytics.tsx",
              "SessionHistory.tsx", "Settings.tsx", "SessionRecords.tsx", "NotFound.tsx"],
    "test": ["setup.ts"],
}


def expected() -> list[str]:
    files = ["docker-compose.yml", ".env.example", ".gitignore", "README.md", ".github/workflows/ci.yml",
             "scripts/smoke_test.py", "scripts/check_files.py",
             "docs/ARCHITECTURE.md", "docs/API.md", "docs/DEMO_GUIDE.md", "docs/EVALUATION.md", "docs/SETUP_GUIDE.md",
             "backend/Dockerfile", "backend/requirements.txt", "backend/.env.example", "backend/pytest.ini",
             "backend/alembic.ini", "backend/alembic/env.py", "backend/alembic/script.py.mako",
             "frontend/Dockerfile", "frontend/package.json", "frontend/vite.config.ts", "frontend/tsconfig.json",
             "frontend/tsconfig.node.json", "frontend/index.html", "frontend/tailwind.config.js",
             "frontend/postcss.config.js"]
    for folder, names in BACKEND_APP.items():
        files += [f"backend/app/{folder + '/' if folder else ''}{n}.py" for n in names]
    files += [f"backend/tests/{n}.py" for n in BACKEND_TESTS]
    files += [f"backend/alembic/versions/{n}.py" for n in MIGRATIONS]
    for folder, names in FRONTEND_SRC.items():
        files += [f"frontend/src/{folder + '/' if folder else ''}{n}" for n in names]
    return files


def main() -> int:
    missing = [f for f in expected() if not (ROOT / f).is_file()]
    total = len(expected())
    if not missing:
        print(f"All {total} project files are present.")
        return 0
    print(f"{len(missing)} of {total} files are missing:\n")
    for f in missing:
        print("  " + f)
    return 1


if __name__ == "__main__":
    sys.exit(main())