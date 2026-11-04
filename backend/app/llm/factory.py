from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai_compatible import OpenAICompatibleProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Raises ValueError for an invalid configuration."""
    s = get_settings()
    if s.llm_provider == "ollama":
        return OllamaProvider(
            base_url=s.ollama_base_url,
            model=s.ollama_model,
            timeout=s.llm_timeout_seconds,
            temperature=s.llm_temperature,
        )
    if s.llm_provider == "openai_compatible":
        if not s.optional_api_base_url or not s.optional_api_model:
            raise ValueError("OPTIONAL_API_BASE_URL and OPTIONAL_API_MODEL must be set")
        return OpenAICompatibleProvider(
            base_url=s.optional_api_base_url,
            api_key=s.optional_api_key,
            model=s.optional_api_model,
            timeout=s.llm_timeout_seconds,
            temperature=s.llm_temperature,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {s.llm_provider}")