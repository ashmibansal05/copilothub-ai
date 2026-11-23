from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Rejects oversized bodies early and adds protective headers to every API response."""

    async def dispatch(self, request, call_next):
        settings = get_settings()
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > (settings.max_upload_mb + 1) * 1024 * 1024:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)

        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith(DOC_PATHS):  # Swagger UI needs to load its own scripts
            headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            headers.setdefault("Cache-Control", "no-store")  # API data is private
        if settings.environment.lower() == "production":
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response