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
    agent_require_final_approval: bool = True
    agent_max_approval_rounds: int = Field(default=3, ge=1, le=10)
    agent_max_replans: int = Field(default=3, ge=0, le=10)
        # ---- RAG (Phase 10) ----
    data_dir: str = "../data"  # documents/ and embeddings/ live here
    embedding_backend: str = "sentence_transformers"  # or "hashing" (lexical, no download)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_chunk_size: int = Field(default=900, ge=100, le=4000)
    rag_chunk_overlap: int = Field(default=120, ge=0, le=1000)
    rag_top_k: int = Field(default=4, ge=1, le=20)
    rag_min_score: float = 0.15
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    max_documents_per_session: int = Field(default=20, ge=1, le=200)
    rag_max_chunks_per_document: int = Field(default=400, ge=1, le=5000)

    @field_validator("embedding_backend")
    @classmethod
    def embedding_backend_must_be_known(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"sentence_transformers", "hashing"}:
            raise ValueError("EMBEDDING_BACKEND must be 'sentence_transformers' or 'hashing'")
        return value

    @property
    def data_path(self):
        from pathlib import Path

        return Path(self.data_dir).expanduser().resolve()

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