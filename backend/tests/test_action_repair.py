"""Regression tests: malformed research actions and schema-specific repair."""
import asyncio
import pytest
from app.agents.llm_brain import LLMBrain
from app.agents.brain import FinalAnswer, ToolCall
from app.llm.base import LLMResponseError


class ScriptedProvider:
    name = "scripted"
    model = "test"

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    async def generate(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return next(self.outputs)


def call(provider, force_final=False):
    return asyncio.run(LLMBrain(provider).next_action(
        "Research AWS service offerings", "Compare cloud services", [], [],
        tools=[], force_final=force_final
    ))


def test_repairs_missing_action_with_final_findings():
    provider = ScriptedProvider(['{"status":"done"}', '{"action":"final","findings":"AWS services vary by region."}'])
    answer = call(provider)
    assert isinstance(answer, FinalAnswer)
    assert "vary by region" in answer.text
    assert len(provider.calls) == 2
    assert "previous reply was invalid" in provider.calls[1][0][-1]["content"]


def test_malformed_json_repaired_without_fabricating_tools():
    provider = ScriptedProvider(['{"action":', '{"action":"final","findings":"Insufficient evidence to verify prices."}'])
    answer = call(provider)
    assert isinstance(answer, FinalAnswer)
    assert "Insufficient evidence" in answer.text


def test_force_final_rejects_tool_then_repairs():
    provider = ScriptedProvider(['{"action":"tool","tool":"search_web","arguments":{}}', '{"action":"final","findings":"No verified sources were retrieved."}'])
    answer = call(provider, force_final=True)
    assert isinstance(answer, FinalAnswer)
    assert "MUST use action=final" in provider.calls[1][0][-1]["content"]


def test_two_invalid_replies_still_raise():
    provider = ScriptedProvider(['{"status":"done"}', '{"status":"still done"}'])
    with pytest.raises(LLMResponseError, match="no valid 'action'"):
        call(provider)
    assert len(provider.calls) == 2


def test_existing_final_does_not_retry():
    provider = ScriptedProvider(['{"action":"final","findings":"AWS offers cloud storage."}'])
    assert isinstance(call(provider), FinalAnswer)
    assert len(provider.calls) == 1


def test_plain_findings_backward_compatible():
    provider = ScriptedProvider(['{"findings":"AWS provides cloud compute options."}'])
    assert isinstance(call(provider), FinalAnswer)
    assert len(provider.calls) == 1
