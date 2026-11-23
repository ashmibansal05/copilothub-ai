from fastapi import APIRouter

from app.api import (
    agent, auth, conflicts, documents, health, instructions, interventions,
    reports, session_control, sessions, tools,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(sessions.router)
api_router.include_router(session_control.router)
api_router.include_router(interventions.router)
api_router.include_router(conflicts.router)
api_router.include_router(documents.router)
api_router.include_router(tools.router)
api_router.include_router(reports.router)
api_router.include_router(instructions.router)
api_router.include_router(agent.router)