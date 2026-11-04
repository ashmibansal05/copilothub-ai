import httpx

from app.llm.base import (
    ChatMessage,
    LLMProvider,
    LLMResponseError,
    LLMUnavailableError,
    ProviderHealth,
)
from app.llm.utils import strip_thinking


class OpenAICompatibleProvider(LLMProvider):
    """OPTIONAL - NOT REQUIRED.

    Talks to any server that implements POST /chat/completions (LM Studio,
    llama.cpp server, vLLM, ... or a hosted service if you choose one). The
    project never needs this: the default provider is local Ollama."""

    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        temperature: float = 0.2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self._transport = transport

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout or self.timeout,
            headers=headers,
            transport=self._transport,
        )

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        body: dict = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            async with self._client() as client:
                response = await client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError(f"LLM API timed out after {self.timeout:.0f}s") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Cannot reach LLM API at {self.base_url}: {exc}") from exc

        if response.status_code != 200:
            raise LLMResponseError(f"LLM API returned HTTP {response.status_code}: {response.text[:200]}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("Unexpected response format from LLM API") from exc

        text = strip_thinking(content or "")
        if not text:
            raise LLMResponseError("Model returned an empty response")
        return text

    async def health(self) -> ProviderHealth:
        try:
            async with self._client(timeout=3.0) as client:
                response = await client.get("/models")
        except httpx.HTTPError:
            return ProviderHealth(False, False, f"cannot reach LLM API at {self.base_url}")
        if response.status_code != 200:
            return ProviderHealth(True, False, f"LLM API returned HTTP {response.status_code}")
        try:
            ids = [m.get("id", "") for m in response.json().get("data", [])]
        except (ValueError, AttributeError):
            return ProviderHealth(True, True, "reachable (model list unavailable)")
        if ids and self.model not in ids:
            return ProviderHealth(True, False, f"model '{self.model}' not offered by the server")
        return ProviderHealth(True, True, "ok")