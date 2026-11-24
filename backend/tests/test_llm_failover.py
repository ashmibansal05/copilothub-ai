"""Fast deterministic tests: no Ollama/network/API key required."""
import asyncio
import pytest

from app.llm.base import LLMProvider, LLMResponseError, LLMUnavailableError, ProviderHealth
from app.llm.failover import FailoverProvider


class Stub(LLMProvider):
    name = "stub"
    def __init__(self, model, answer="ok", ready=True):
        self.model, self.answer, self.ready = model, answer, ready
        self.calls = 0
    async def generate(self, messages, *, json_mode=False, temperature=None, max_tokens=None):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer
    async def health(self):
        return ProviderHealth(self.ready, self.ready, "ok" if self.ready else "offline")


def test_primary_success_skips_fallback():
    a, b = Stub("a"), Stub("b")
    p = FailoverProvider(a, b)
    assert asyncio.run(p.generate([{"role":"user","content":"hi"}])) == "ok"
    assert (a.calls, b.calls) == (1, 0)


def test_timeout_uses_fallback():
    a, b = Stub("a", LLMUnavailableError("timeout")), Stub("b", "fallback answer")
    p = FailoverProvider(a, b)
    assert asyncio.run(p.generate([{"role":"user","content":"hi"}])) == "fallback answer"
    assert p.last_used == "stub:b"
    assert (a.calls, b.calls) == (1, 1)


def test_no_fallback_propagates_error():
    p = FailoverProvider(Stub("a", LLMUnavailableError("timeout")))
    with pytest.raises(LLMUnavailableError):
        asyncio.run(p.generate([]))


def test_bad_model_output_is_not_silently_retried():
    a, b = Stub("a", LLMResponseError("invalid")), Stub("b")
    with pytest.raises(LLMResponseError):
        asyncio.run(FailoverProvider(a, b).generate([]))
    assert b.calls == 0


def test_fallback_health_used_when_primary_unavailable():
    p = FailoverProvider(Stub("a", ready=False), Stub("b"))
    assert asyncio.run(p.health()).ready


def test_requests_are_serialized():
    active, peak = 0, 0
    class Slow(Stub):
        async def generate(self, messages, *, json_mode=False, temperature=None, max_tokens=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return "ok"
    p = FailoverProvider(Slow("a"))
    async def run():
        return await asyncio.gather(*(p.generate([]) for _ in range(4)))
    assert asyncio.run(run()) == ["ok"] * 4
    assert peak == 1
