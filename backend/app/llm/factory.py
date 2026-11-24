from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai_compatible import OpenAICompatibleProvider


@lru_cache
def _get_primary_llm_provider() -> LLMProvider:
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

# One shared instance wraps the original provider without altering its construction.
from app.llm.failover import FailoverProvider


def _configured_fallback(settings):
    if settings.llm_fallback_provider == "none":
        return None
    if settings.llm_fallback_provider == "ollama":
        if not settings.llm_fallback_ollama_model:
            raise ValueError("Set LLM_FALLBACK_OLLAMA_MODEL")
        return OllamaProvider(
            base_url=settings.llm_fallback_ollama_base_url or settings.ollama_base_url,
            model=settings.llm_fallback_ollama_model,
            timeout=settings.llm_fallback_timeout_seconds,
            temperature=settings.llm_temperature,
        )
    if settings.llm_fallback_provider == "openai_compatible":
        if not settings.llm_fallback_api_base_url or not settings.llm_fallback_api_model:
            raise ValueError("Set LLM_FALLBACK_API_BASE_URL and LLM_FALLBACK_API_MODEL")
        return OpenAICompatibleProvider(
            base_url=settings.llm_fallback_api_base_url,
            api_key=settings.llm_fallback_api_key,
            model=settings.llm_fallback_api_model,
            timeout=settings.llm_fallback_timeout_seconds,
            temperature=settings.llm_temperature,
        )
    raise ValueError("LLM_FALLBACK_PROVIDER must be none, ollama, or openai_compatible")


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    return FailoverProvider(
        _get_primary_llm_provider(),
        _configured_fallback(settings),
        serialize_requests=settings.llm_serialize_requests,
    )
