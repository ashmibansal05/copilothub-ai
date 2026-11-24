"""Optional LLM failover and in-process serialization.

One shared provider wrapper protects expensive local inference from simultaneous
requests. Only LLM transport/service errors trigger failover: JSON/schema errors
must be handled by the caller, not mistaken for provider downtime.

This lock does NOT coordinate across separate backend processes/replicas. A
persistent job queue is required before running multiple workers at scale.
"""
import asyncio
import logging

from app.llm.base import (
    ChatMessage, LLMProvider, LLMUnavailableError, ProviderHealth,
)

logger = logging.getLogger(__name__)


class FailoverProvider(LLMProvider):
    def __init__(
        self, primary: LLMProvider, fallback: LLMProvider | None = None,
        serialize_requests: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name
        self.model = primary.model
        self._serialize = serialize_requests
        self._lock = asyncio.Lock()
        self.last_used = primary.name

    async def generate(
        self, messages: list[ChatMessage], *, json_mode: bool = False,
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> str:
        async def run() -> str:
            kwargs = dict(json_mode=json_mode, temperature=temperature, max_tokens=max_tokens)
            try:
                answer = await self.primary.generate(messages, **kwargs)
                self.last_used = f"{self.primary.name}:{self.primary.model}"
                return answer
            except LLMUnavailableError as exc:
                if self.fallback is None:
                    raise
                logger.warning(
                    "Primary LLM unavailable (%s); using configured fallback %s:%s",
                    type(exc).__name__, self.fallback.name, self.fallback.model,
                )
                # Never log input messages or API keys.
                answer = await self.fallback.generate(messages, **kwargs)
                self.last_used = f"{self.fallback.name}:{self.fallback.model}"
                return answer
        if not self._serialize:
            return await run()
        async with self._lock:
            return await run()

    async def health(self) -> ProviderHealth:
        first = await self.primary.health()
        if first.ready or self.fallback is None:
            return first
        other = await self.fallback.health()
        if other.ready:
            return ProviderHealth(True, True, f"fallback ready: {self.fallback.name}:{self.fallback.model} (primary: {first.detail})")
        return ProviderHealth(first.reachable or other.reachable, False,
                              f"primary: {first.detail}; fallback: {other.detail}")
