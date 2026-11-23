import math
import threading
import time
from collections import deque

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models.user import User


class RateLimiter:
    """Sliding-window limiter kept in memory (single process, like the rest of the app).
    Behind a reverse proxy, put a real limiter in front as well."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float) -> float | None:
        """Record a hit. Returns None if allowed, else the seconds to wait."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                return window - (now - hits[0])
            hits.append(now)
            if len(self._hits) > 5000:  # keep memory bounded
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] <= window}
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def enforce(name: str, key: str, limit: int, window: float) -> None:
    if not get_settings().rate_limit_enabled:
        return
    retry = limiter.check(f"{name}:{key}", limit, window)
    if retry is not None:
        seconds = max(1, math.ceil(retry))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many requests. Please try again in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def ip_limit(name: str, limit: int, window: float):
    def dependency(request: Request) -> None:
        enforce(name, client_ip(request), limit, window)

    return dependency


def user_limit(name: str, limit: int, window: float):
    def dependency(user: User = Depends(get_current_user)) -> None:
        enforce(name, str(user.id), limit, window)

    return dependency