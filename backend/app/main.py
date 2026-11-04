import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.websocket.routes import router as ws_router

settings = get_settings()
setup_logging(settings.debug)
logger = logging.getLogger("copilothub")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "Starting %s (env=%s, demo_mode=%s)",
        settings.app_name,
        settings.environment,
        settings.demo_mode,
    )
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Collaborative human-in-the-loop platform for controlling AI agents",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)