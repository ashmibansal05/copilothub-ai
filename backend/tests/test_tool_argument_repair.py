"""Regression checks for real Llama tool argument errors in Sessions 1 and 2."""
from app.tools.base import describe_tools
from app.tools.builtin import CompareSourcesTool, RetrieveDocumentsTool, SearchWebTool
from app.tools.registry import normalize_known_llm_mistakes
import pytest
from pydantic import ValidationError


def test_clamp_known_web_and_retrieval_limits():
    web, repairs = normalize_known_llm_mistakes("search_web", {"query": "cloud platforms", "max_results": 10})
    assert web["max_results"] == 8 and repairs
    SearchWebTool.args_model.model_validate(web)
    docs, repairs = normalize_known_llm_mistakes("retrieve_documents", {"query": "cloud storage", "k": 10})
    assert docs["k"] == 8 and repairs
    RetrieveDocumentsTool.args_model.model_validate(docs)


def test_decode_only_stringified_lists():
    original = {"topics": '["AWS", "Azure"]', "criteria": "['cost', 'security']"}
    fixed, repairs = normalize_known_llm_mistakes("compare_sources", original)
    assert fixed == {"topics": ["AWS", "Azure"], "criteria": ["cost", "security"]}
    assert len(repairs) == 2
    assert isinstance(original["topics"], str)  # no mutation
    CompareSourcesTool.args_model.model_validate(fixed)


def test_still_rejects_invalid_arrays_and_unknown_tools():
    invalid, _ = normalize_known_llm_mistakes("compare_sources", {"topics": '["AWS"]'})
    with pytest.raises(ValidationError):
        CompareSourcesTool.args_model.model_validate(invalid)  # min 2 topics
    unknown, repairs = normalize_known_llm_mistakes("unknown", {"max_results": 10})
    assert unknown == {"max_results": 10} and not repairs
    boolean_value, repairs = normalize_known_llm_mistakes("search_web", {"max_results": True})
    assert boolean_value["max_results"] is True and not repairs


def test_tool_description_includes_real_bounds():
    descriptions = describe_tools([SearchWebTool().spec(), RetrieveDocumentsTool().spec(), CompareSourcesTool().spec()])
    assert "max 8" in descriptions
    assert "min items 2" in descriptions
    assert "array of string" in descriptions
