import logging

from app.agents.brain import AgentBrain
from app.agents.llm_brain import LLMBrain
from app.agents.mock_brain import MockBrain
from app.core.config import get_settings
from app.llm.factory import get_llm_provider

logger = logging.getLogger("copilothub.agent")


async def create_brain() -> tuple[AgentBrain, str | None]:
    """Pick the agent brain. Returns (brain, notice). `notice` is a warning that
    is shown to the humans in the session when we had to fall back to demo mode."""
    settings = get_settings()
    demo = MockBrain(delay=settings.agent_step_delay_seconds)

    if settings.demo_mode:
        return demo, None

    try:
        provider = get_llm_provider()
    except ValueError as exc:
        return demo, f"LLM configuration problem ({exc}). Falling back to demo mode."

    health = await provider.health()
    if not health.ready:
        logger.warning("LLM not ready: %s", health.detail)
        return demo, f"{provider.name} is not ready ({health.detail}). Falling back to demo mode."
    return LLMBrain(provider), None