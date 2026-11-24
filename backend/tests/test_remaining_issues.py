"""Guardrails for regression of confirmed Issues 03-08."""
import ast
import inspect
from pathlib import Path
from app.agents.llm_brain import LLMBrain
from app.services import report_service


def test_report_generation_has_approval_context():
    assert 'approved_final' in inspect.signature(report_service.generate_report).parameters
    assert 'approved_final' in inspect.signature(report_service._store).parameters


def test_interim_snapshot_and_final_are_distinct():
    text = inspect.getsource(report_service._store)
    assert 'kind = "FINAL" if approved_final else "DRAFT"' in text


def test_report_formatting_does_not_stringify_model_lists():
    text = inspect.getsource(LLMBrain.write_report)
    assert '"\\n".join' in text or 'join(f"- ' in text
    assert 'str(data.get(key) or "")' not in text


def test_replanning_does_not_reset_global_step_counter():
    from app.agents.orchestrator import AgentOrchestrator
    plan_source = inspect.getsource(AgentOrchestrator.plan_node)
    assert 'steps_executed": 0' not in plan_source
    complete_source = inspect.getsource(AgentOrchestrator._complete)
    assert 'incomplete_plan' in complete_source
