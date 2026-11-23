import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import APP_VERSION, get_settings
from app.core.logging import setup_logging
from app.core.middleware import SecurityHeadersMiddleware
from app.services.agent_service import recover_orphaned_sessions
from app.websocket.routes import router as ws_router

settings = get_settings()
setup_logging(settings.debug)
logger = logging.getLogger("copilothub")
production = settings.environment.strip().lower() == "production"


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "Starting %s %s (env=%s, demo_mode=%s, llm=%s, embeddings=%s)",
        settings.app_name, APP_VERSION, settings.environment, settings.demo_mode,
        settings.llm_provider, settings.embedding_backend,
    )
    try:
        await recover_orphaned_sessions()
    except Exception:
        logger.exception("Could not check for interrupted sessions (is the database migrated?)")
    if settings.cleanup_orphans_on_start:
        try:
            from app.db import session as db_session
            from app.services import cleanup

            with db_session.SessionLocal() as db:
                removed = cleanup.purge(cleanup.find_orphans(db))
            if removed:
                logger.warning("Removed %d orphaned file(s)/folder(s)", removed)
        except Exception:
            logger.exception("Orphan cleanup failed")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Collaborative human-in-the-loop platform for controlling AI agents",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)

# Added first = inner. CORS is added last so it wraps everything (even error responses).
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router)
app.include_router(ws_router)