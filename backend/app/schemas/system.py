from pydantic import BaseModel


class LLMInfo(BaseModel):
    provider: str
    model: str
    ready: bool
    detail: str


class SystemStatus(BaseModel):
    app_name: str
    version: str
    environment: str
    demo_mode: bool
    llm: LLMInfo
    embedding_backend: str
    embedding_model: str | None
    web_search_provider: str
    tools_enabled: bool
    enabled_tools: list[str]
    require_final_approval: bool
    nlp_auto_apply: bool
    risk_prediction_enabled: bool
    rate_limit_enabled: bool
    max_upload_mb: int