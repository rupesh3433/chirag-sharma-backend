"""
Agent API Router
"""

from fastapi import APIRouter
from .endpoints import AgentEndpoints


def create_agent_router(orchestrator) -> APIRouter:
    """Create and configure agent router"""
    
    router = APIRouter(prefix="/agent", tags=["Agent Chat"])
    endpoints = AgentEndpoints(orchestrator)
    
    # Register endpoints
    router.post("/chat")(endpoints.chat)
    router.get("/sessions")(endpoints.get_sessions)
    router.post("/cleanup")(endpoints.cleanup)
    router.delete("/sessions/{session_id}")(endpoints.delete_session)
    router.get("/health")(endpoints.health_check)
    
    return router