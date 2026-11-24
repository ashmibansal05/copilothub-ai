import httpx

from app.llm.base import (
    ChatMessage,
    LLMProvider,
    LLMResponseError,
    LLMUnavailableError,
    ProviderHealth,
)
from app.llm.utils import strip_thinking


class OllamaProvider(LLMProvider):
    """Local models through Ollama's HTTP API (free, runs on your machine)."""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        temperature: float = 0.2,
        transport: httpx.AsyncBaseTransport | None = None,  # tests inject a mock
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self._transport = transport

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout or self.timeout, transport=self._transport
        )

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        options: dict = {"temperature": self.temperature if temperature is None else temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        body: dict = {
            "model": self.model,
            "messages": list(messages),
            "stream": False,
            "think": False,  # ask Qwen3 not to emit reasoning (older servers ignore this)
            "options": options,
        }
        if json_mode:
            body["format"] = "json"

        try:
            async with self._client() as client:
                response = await client.post("/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError(f"Ollama timed out after {self.timeout:.0f}s") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Cannot reach Ollama at {self.base_url}: {exc}") from exc

        if response.status_code != 200:
            raise LLMResponseError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMResponseError("Unexpected response format from Ollama") from exc

        text = strip_thinking(content)
        if not text:
            raise LLMResponseError("Model returned an empty response")
        return text

    async def health(self) -> ProviderHealth:
        try:
            async with self._client(timeout=3.0) as client:
                response = await client.get("/api/tags")
        except httpx.HTTPError:
            return ProviderHealth(False, False, f"cannot reach Ollama at {self.base_url}")
        if response.status_code != 200:
            return ProviderHealth(True, False, f"Ollama returned HTTP {response.status_code}")
        try:
            names = [m.get("name", "") for m in response.json().get("models", [])]
        except (ValueError, AttributeError):
            return ProviderHealth(True, False, "unexpected response from Ollama")

        wanted = self.model
        available = any(
            n == wanted or (":" not in wanted and n.split(":")[0] == wanted) for n in names
        )
        if not available:
            return ProviderHealth(True, False, f"model '{wanted}' is not installed (run: ollama pull {wanted})")
        return ProviderHealth(True, True, "ok")