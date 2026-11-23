
from functools import lru_cache

from app.core.config import get_settings
from app.tools.builtin import BUILTIN_TOOLS
from app.tools.registry import ToolRegistry


@lru_cache
def get_registry() -> ToolRegistry:
    """The approved tools. AGENT_ENABLED_TOOLS can restrict them further."""
    allowed = {
        n.strip()
        for n in get_settings().agent_enabled_tools.split(",")
        if n.strip()
    }
    return ToolRegistry(
        [cls() for cls in BUILTIN_TOOLS],
        enabled=allowed or None,
    )
