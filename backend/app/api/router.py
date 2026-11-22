from fastapi import APIRouter

from app.api import agent, auth, health, interventions, session_control, sessions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(sessions.router)
api_router.include_router(session_control.router)
api_router.include_router(interventions.router)
api_router.include_router(agent.router)