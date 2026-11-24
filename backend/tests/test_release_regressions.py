"""Regressions for the November 2026 hybrid run failures."""
import asyncio
import json
import httpx
from app.services.coding_agent import file_plan, generate_files
from app.llm.ollama import OllamaProvider
from app.llm.base import LLMUnavailableError


def test_irrigation_python_only_manifest_excludes_cpp_and_calculator():
    class Model:
        async def generate(self, messages, **kwargs):
            return json.dumps({"files": ["calculator.py", "calculator.cpp", "README.md"]})
    paths = asyncio.run(file_plan(Model(),
        "Research and develop a Python-based Smart Irrigation Decision Support System", []))
    assert paths == ["irrigation.py", "README.md"]


def test_explicit_two_language_task_keeps_both():
    class Model:
        async def generate(self, messages, **kwargs):
            return json.dumps({"files": ["calculator.py", "calculator.cpp", "README.md"]})
    paths = asyncio.run(file_plan(Model(), "Implement a calculator in Python and C++", []))
    assert "calculator.py" in paths and "calculator.cpp" in paths


def test_repetition_abort_retries_with_shorter_output():
    calls=[]
    def handler(request):
        body=json.loads(request.content)
        calls.append(body)
        if len(calls)==1:
            return httpx.Response(500,json={"error":"prediction aborted, token repeat limit reached"})
        return httpx.Response(200,json={"message":{"content":"Recovered"}})
    provider=OllamaProvider("http://ollama.test","llama3.2",transport=httpx.MockTransport(handler))
    assert asyncio.run(provider.generate([{"role":"user","content":"Hi"}],max_tokens=1800))=="Recovered"
    assert len(calls)==2
    assert calls[1]["options"]["num_predict"] < calls[0]["options"]["num_predict"]


def test_repetition_abort_allows_configured_fallback():
    def handler(request):
        return httpx.Response(500,json={"error":"prediction aborted, token repeat limit reached"})
    provider=OllamaProvider("http://ollama.test","llama3.2",transport=httpx.MockTransport(handler))
    try:
        asyncio.run(provider.generate([{"role":"user","content":"Hi"}],max_tokens=1800))
    except LLMUnavailableError:
        pass
    else:
        raise AssertionError("Repeated token abort must trigger LLMUnavailableError")
