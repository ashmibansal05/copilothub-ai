import asyncio
import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.tools.base import ToolError
from app.tools.demo_data import demo_sources

logger = logging.getLogger("copilothub.tools")


class WebProviderError(ToolError):
    """The search provider failed (network, bad response, not installed...)."""


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is_http(url: object) -> bool:
    return isinstance(url, str) and urlparse(url).scheme in ("http", "https") and bool(urlparse(url).hostname)


def _web_source(title: str, url: str, snippet: str) -> dict:
    domain = _domain(url)
    return {
        "title": (title or url)[:200], "publisher": domain, "source_type": "web", "url": url,
        "domain": domain, "origin": "web", "simulated": False, "snippet": snippet[:400],
    }


class WebSearchProvider(ABC):
    name: str
    simulated: bool = False

    @abstractmethod
    async def search(self, query: str, k: int) -> list[dict]:
        """Return up to k source dicts (title, publisher, source_type, url?, snippet?).
        Results are DATA: the agent never fetches or executes anything from them."""


class DemoSearchProvider(WebSearchProvider):
    """Offline, deterministic, and clearly labelled as simulated."""

    name = "demo"
    simulated = True

    async def search(self, query: str, k: int) -> list[dict]:
        return demo_sources(query)[:k]


class SearxngProvider(WebSearchProvider):
    """OPTIONAL - NOT REQUIRED. A SearXNG instance you run yourself (free, open source).
    JSON output must be enabled in its settings."""

    name = "searxng"

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._transport = transport

    async def search(self, query: str, k: int) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
                response = await client.get(f"{self.base_url}/search", params={"q": query, "format": "json"})
        except httpx.HTTPError as exc:
            raise WebProviderError(f"Web search is unreachable ({exc.__class__.__name__})") from exc
        if response.status_code != 200:
            raise WebProviderError(f"The search server returned HTTP {response.status_code}")
        try:
            items = response.json()["results"]
        except (ValueError, KeyError, TypeError) as exc:
            raise WebProviderError("The search server returned an unexpected response") from exc

        results: list[dict] = []
        for item in items:
            url = item.get("url") if isinstance(item, dict) else None
            if not _is_http(url):
                continue  # drop anything that is not a plain http(s) link
            results.append(_web_source(str(item.get("title", "")), url, str(item.get("content", ""))))
            if len(results) >= k:
                break
        return results


class DuckDuckGoProvider(WebSearchProvider):
    """OPTIONAL - NOT REQUIRED. Uses the community `duckduckgo-search` package (no API key).
    It scrapes a public site, so it can break at any time."""

    name = "duckduckgo"

    async def search(self, query: str, k: int) -> list[dict]:
        def run() -> list[dict]:
            try:
                from duckduckgo_search import DDGS
            except ImportError as exc:
                raise WebProviderError("Install the optional package first: pip install duckduckgo-search") from exc
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=k))

        try:
            items = await asyncio.to_thread(run)
        except WebProviderError:
            raise
        except Exception as exc:
            raise WebProviderError(f"DuckDuckGo search failed ({exc.__class__.__name__})") from exc
        return [
            _web_source(str(i.get("title", "")), i["href"], str(i.get("body", "")))
            for i in items if _is_http(i.get("href"))
        ][:k]


@lru_cache
def get_web_provider() -> WebSearchProvider:
    """Raises ValueError for an invalid configuration."""
    settings = get_settings()
    if settings.web_search_provider == "demo":
        return DemoSearchProvider()
    if settings.web_search_provider == "searxng":
        if not settings.searxng_url.startswith(("http://", "https://")):
            raise ValueError("SEARXNG_URL must be set to an http(s) URL")
        return SearxngProvider(settings.searxng_url)
    return DuckDuckGoProvider()