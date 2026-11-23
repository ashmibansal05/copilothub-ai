from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.config import APP_VERSION, get_settings
from app.llm.factory import get_llm_provider
from app.models.user import User
from app.schemas.system import LLMInfo, SystemStatus
from app.tools import get_registry

router = APIRouter(tags=["system"])


@router.get("/system/status", response_model=SystemStatus)
async def system_status(_: User = Depends(get_current_user)) -> SystemStatus:
    """A read-only summary of how the platform is configured. Contains no secrets and no URLs."""
    s = get_settings()
    try:
        provider = get_llm_provider()
        health = await provider.health()
        llm = LLMInfo(provider=provider.name, model=provider.model, ready=health.ready, detail=health.detail)
    except Exception as exc:
        llm = LLMInfo(provider=s.llm_provider, model="", ready=False, detail=str(exc)[:200])
    return SystemStatus(
        app_name=s.app_name, version=APP_VERSION, environment=s.environment, demo_mode=s.demo_mode, llm=llm,
        embedding_backend=s.embedding_backend,
        embedding_model=s.embedding_model if s.embedding_backend == "sentence_transformers" else None,
        web_search_provider=s.web_search_provider, tools_enabled=s.agent_tools_enabled,
        enabled_tools=get_registry().names(), require_final_approval=s.agent_require_final_approval,
        nlp_auto_apply=s.nlp_auto_apply, risk_prediction_enabled=s.risk_prediction_enabled,
        rate_limit_enabled=s.rate_limit_enabled, max_upload_mb=s.max_upload_mb,
    )