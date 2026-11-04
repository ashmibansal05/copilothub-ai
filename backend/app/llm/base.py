from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, TypedDict


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(Exception):
    """Base class for all LLM problems."""


class LLMUnavailableError(LLMError):
    """The model server cannot be reached or timed out."""


class LLMResponseError(LLMError):
    """The server answered, but the answer is an error or unusable."""


@dataclass
class ProviderHealth:
    reachable: bool
    model_available: bool
    detail: str

    @property
    def ready(self) -> bool:
        return self.reachable and self.model_available


class LLMProvider(ABC):
    """Everything the agent needs from a language model. Add a new backend by
    subclassing this and registering it in llm/factory.py."""

    name: str
    model: str

    @abstractmethod
    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Return the assistant's reply text (thinking blocks already removed)."""

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Quick check used before a run starts. Must not raise."""