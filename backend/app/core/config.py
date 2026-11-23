
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ============================================================
# Application Version (Phase 15)
# ============================================================

APP_VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Application ----
    app_name: str = "CoPilotHub AI"
    environment: str = "development"
    debug: bool = False
    demo_mode: bool = True

    # ---- Database and Authentication ----
    database_url: str
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ---- CORS ----
    cors_origins: str = "http://localhost:5173"

    # ---- LLM (Phase 6) ----
    llm_provider: str = "ollama"
    # "ollama" | "openai_compatible"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3"

    # OPTIONAL - any OpenAI-compatible endpoint
    optional_api_base_url: str = ""
    optional_api_key: str = ""
    optional_api_model: str = ""

    llm_timeout_seconds: float = 120.0
    llm_temperature: float = 0.2

    # ---- Agent (Phase 5) ----
    agent_max_steps: int = Field(default=8, ge=1, le=30)
    agent_max_retries: int = Field(default=2, ge=0, le=5)
    agent_retry_backoff_seconds: float = 1.0
    agent_step_delay_seconds: float = 1.5
    agent_step_timeout_seconds: float = 180.0
    agent_max_runtime_seconds: float = 900.0
    agent_require_final_approval: bool = True
    agent_max_approval_rounds: int = Field(
        default=3, ge=1, le=10
    )
    agent_max_replans: int = Field(
        default=3, ge=0, le=10
    )

    # ---- RAG (Phase 10) ----
    data_dir: str = "../data"

    # "hashing" works without downloading Sentence-Transformers.
    # Docker Compose currently overrides this setting to "hashing".
    embedding_backend: str = "sentence_transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    rag_chunk_size: int = Field(default=900, ge=100, le=4000)
    rag_chunk_overlap: int = Field(default=120, ge=0, le=1000)
    rag_top_k: int = Field(default=4, ge=1, le=20)
    rag_min_score: float = 0.15
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    max_documents_per_session: int = Field(
        default=20, ge=1, le=200
    )
    rag_max_chunks_per_document: int = Field(
        default=400, ge=1, le=5000
    )

    # ---- Tools (Phase 11) ----
    agent_tools_enabled: bool = True
    # False = use Phase 10 single-shot agent steps

    agent_enabled_tools: str = ""
    # Comma-separated allow-list; empty = all built-in tools

    agent_max_tool_calls_per_step: int = Field(
        default=3, ge=1, le=8
    )
    agent_max_tool_calls_per_run: int = Field(
        default=40, ge=1, le=500
    )

    tool_timeout_seconds: float = 30.0

    tool_output_max_chars: int = Field(
        default=4000, ge=200, le=20000
    )

    max_reports_per_session: int = Field(
        default=5, ge=1, le=50
    )

    # "demo" = simulated offline results
    # "searxng" and "duckduckgo" are optional live providers
    web_search_provider: str = "demo"
    searxng_url: str = ""

    # ---- NLP Intervention Classifier (Phase 12) ----
    nlp_auto_apply: bool = True
    # False = always ask for user confirmation

    nlp_auto_train: bool = True
    # Train on first use when no saved model exists

    # ---- ML Intervention-Risk Predictor (Phase 13) ----
    risk_prediction_enabled: bool = True

    risk_auto_train: bool = False
    # False = train explicitly using python -m app.ml.train.
    # Synthetic training data does not establish real-world accuracy.

    risk_synthetic_rows: int = Field(
        default=3000, ge=500, le=50000
    )

    # ---- Final Reports (Phase 14) ----
    agent_generate_final_report: bool = True

    max_final_reports_per_session: int = Field(
        default=5, ge=1, le=50
    )

    # ============================================================
    # Phase 15: Security and Maintenance
    # ============================================================

    rate_limit_enabled: bool = True
    # Enable rate limiting on authentication and sensitive endpoints.

    cleanup_orphans_on_start: bool = False
    # If enabled, remove uploaded files and indexes belonging
    # to sessions that no longer exist in the database.

    # ============================================================
    # Field Validators
    # ============================================================

    @field_validator("embedding_backend")
    @classmethod
    def embedding_backend_must_be_known(cls, value: str) -> str:
        value = value.strip().lower()

        if value not in {"sentence_transformers", "hashing"}:
            raise ValueError(
                "EMBEDDING_BACKEND must be "
                "'sentence_transformers' or 'hashing'"
            )

        return value

    @field_validator("web_search_provider")
    @classmethod
    def web_search_provider_must_be_known(cls, value: str) -> str:
        value = value.strip().lower()

        if value not in {"demo", "searxng", "duckduckgo"}:
            raise ValueError(
                "WEB_SEARCH_PROVIDER must be "
                "'demo', 'searxng' or 'duckduckgo'"
            )

        return value

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_long(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long"
            )

        return value

    @field_validator("llm_provider")
    @classmethod
    def llm_provider_must_be_known(cls, value: str) -> str:
        value = value.strip().lower()

        if value not in {"ollama", "openai_compatible"}:
            raise ValueError(
                "LLM_PROVIDER must be 'ollama' or 'openai_compatible'"
            )

        return value

    # ============================================================
    # Phase 15: Production Security Validator
    # ============================================================

    @model_validator(mode="after")
    def production_needs_a_real_secret(self):
        """
        Prevent the application from starting in production
        when a known placeholder SECRET_KEY is configured.
        """
        if self.environment.strip().lower() == "production":
            lowered = self.secret_key.lower()

            if (
                "replace_with" in lowered
                or "change_me" in lowered
            ):
                raise ValueError(
                    "Set a real SECRET_KEY before running "
                    "with ENVIRONMENT=production"
                )

        return self

    # ============================================================
    # Properties
    # ============================================================

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).expanduser().resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()