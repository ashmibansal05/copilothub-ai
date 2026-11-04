from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "CoPilotHub AI"
    environment: str = "development"
    debug: bool = False
    demo_mode: bool = True

    database_url: str
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: str = "http://localhost:5173"

    # ---- LLM (Phase 6) ----
    llm_provider: str = "ollama"  # "ollama" | "openai_compatible"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3"
    # OPTIONAL - NOT REQUIRED: any OpenAI-compatible endpoint (e.g. a local server)
    optional_api_base_url: str = ""
    optional_api_key: str = ""
    optional_api_model: str = ""
    llm_timeout_seconds: float = 120.0
    llm_temperature: float = 0.2

    # ---- Agent (Phase 5) ----
    agent_max_steps: int = Field(default=8, ge=1, le=30)
    agent_max_retries: int = Field(default=2, ge=0, le=5)
    agent_retry_backoff_seconds: float = 1.0
    agent_step_delay_seconds: float = 1.5  # pacing of the demo agent
    agent_step_timeout_seconds: float = 180.0
    agent_max_runtime_seconds: float = 900.0  # paused time is not counted

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_long(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return value

    @field_validator("llm_provider")
    @classmethod
    def llm_provider_must_be_known(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"ollama", "openai_compatible"}:
            raise ValueError("LLM_PROVIDER must be 'ollama' or 'openai_compatible'")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()