"""
Agent API Router - Enhanced with proper endpoint configuration
"""

from fastapi import APIRouter, Path, Query, Request
from typing import Optional
from datetime import datetime

from .endpoints import AgentEndpoints
from ..models.api_models import AgentChatRequest, AgentChatResponse


def create_agent_router(orchestrator) -> APIRouter:
    """
    Create and configure agent router with all endpoints
    
    Args:
        orchestrator: AgentOrchestrator instance
        
    Returns:
        Configured APIRouter with all agent endpoints
    """
    
    router = APIRouter(
        prefix="/agent",
        tags=["Agent Chat"],
        responses={
            500: {"description": "Internal server error"},
            503: {"description": "Service unavailable"}
        }
    )
    
    endpoints = AgentEndpoints(orchestrator)
    
    # ==================== CHAT ENDPOINTS ====================
    
    @router.post(
        "/chat",
        response_model=AgentChatResponse,
        summary="Send a chat message",
        description="""
        Main endpoint for chatting with the booking agent.
        
        **Features:**
        - Multi-language support (English, Hindi, Nepali, Marathi)
        - Session-based conversation continuity
        - Automatic field extraction and validation
        - Stage-based booking flow management
        
        **Rate Limiting:**
        This endpoint may be rate-limited to prevent abuse.
        """,
        responses={
            200: {"description": "Successful response from agent"},
            400: {"description": "Invalid request (e.g., empty message, unsupported language)"},
            429: {"description": "Too many requests - rate limit exceeded"},
            500: {"description": "Internal server error"}
        }
    )
    async def chat(request: AgentChatRequest) -> AgentChatResponse:
        """
        Send a message to the agent and get a response
        
        **Request Body:**
        - **message**: The user's message (required, 1-1000 chars)
        - **session_id**: Optional session ID for conversation continuity
        - **language**: Language code (en, hi, ne, mr) - default: en
        
        **Response:**
        - **reply**: Agent's response message
        - **session_id**: Session ID for conversation continuity
        - **stage**: Current booking stage
        - **action**: Action taken by agent
        - **missing_fields**: Fields still needed for booking
        - **collected_info**: Information collected so far
        - **chat_mode**: Current chat mode (normal/agent)
        - **off_track_count**: Number of off-topic messages
        
        **Example Request:**
```json
        {
            "message": "I want to book a pandit for my wedding",
            "language": "en"
        }
```
        """
        return await endpoints.chat(request)
    
    # ==================== SESSION MANAGEMENT ====================
    
    @router.get(
        "/sessions",
        summary="Get all sessions statistics",
        description="Retrieve statistics about all active sessions",
        responses={
            200: {"description": "Session statistics retrieved successfully"}
        }
    )
    async def get_sessions():
        """
        Get statistics about all active sessions
        
        **Returns:**
        - **status**: Operation status
        - **timestamp**: Current timestamp
        - **stats**: Session statistics including:
          - active_sessions: Number of currently active sessions
          - total_sessions: Total sessions created
          - sessions_by_stage: Breakdown by booking stage
          - sessions_by_language: Breakdown by language
        """
        return await endpoints.get_sessions()
    
    @router.get(
        "/sessions/{session_id}",
        summary="Get specific session details",
        description="Retrieve detailed information about a specific session",
        responses={
            200: {"description": "Session details retrieved successfully"},
            404: {"description": "Session not found"}
        }
    )
    async def get_session(
        session_id: str = Path(
            ..., 
            description="Session ID to retrieve",
            min_length=1,
            max_length=100
        )
    ):
        """
        Get detailed information about a specific session
        
        **Path Parameters:**
        - **session_id**: The session ID to retrieve
        
        **Returns:**
        - **session_id**: Session identifier
        - **language**: Session language
        - **stage**: Current booking stage
        - **created_at**: Session creation timestamp
        - **last_updated**: Last activity timestamp
        - **message_count**: Number of messages in conversation
        - **off_track_count**: Number of off-topic messages
        - **has_booking**: Whether booking is created
        - **collected_fields**: List of collected field names
        """
        return await endpoints.get_session(session_id)
    
    @router.delete(
        "/sessions/{session_id}",
        summary="Delete a session",
        description="Delete a specific session and its associated data",
        responses={
            200: {"description": "Session deleted successfully"},
            404: {"description": "Session not found"}
        }
    )
    async def delete_session(
        session_id: str = Path(
            ..., 
            description="Session ID to delete",
            min_length=1,
            max_length=100
        )
    ):
        """
        Delete a specific session
        
        **Path Parameters:**
        - **session_id**: The session ID to delete
        
        **Returns:**
        - **status**: Operation status
        - **message**: Confirmation message
        - **session_id**: Deleted session ID
        - **timestamp**: Deletion timestamp
        
        **Note:** This also cleans up associated FSM instances.
        """
        return await endpoints.delete_session(session_id)
    
    @router.post(
        "/cleanup",
        summary="Cleanup expired sessions",
        description="Force cleanup of expired sessions and FSMs",
        responses={
            200: {"description": "Cleanup completed successfully"}
        }
    )
    async def cleanup():
        """
        Force cleanup of expired sessions
        
        **Returns:**
        - **status**: Operation status
        - **sessions_cleaned**: Number of sessions cleaned
        - **fsms_cleaned**: Number of FSMs cleaned
        - **timestamp**: Cleanup timestamp
        
        **Note:** Sessions are automatically cleaned based on TTL settings.
        This endpoint forces immediate cleanup.
        """
        return await endpoints.cleanup()
    
    # ==================== HEALTH & STATUS ====================
    
    @router.get(
        "/health",
        summary="Health check",
        description="Check the health status of the agent service",
        responses={
            200: {"description": "Service is healthy"},
            503: {"description": "Service is unhealthy"}
        }
    )
    async def health_check():
        """
        Health check endpoint
        
        **Returns:**
        - **status**: Health status (healthy/unhealthy)
        - **timestamp**: Current timestamp
        - **services**: Status of individual services
          - memory_service: Memory service status
          - orchestrator: Orchestrator status
          - fsm: FSM service status
        - **metrics**: Current metrics
          - active_sessions: Number of active sessions
          - active_fsms: Number of active FSM instances
          - total_sessions: Total sessions count
        """
        return await endpoints.health_check()
    
    @router.get(
        "/config",
        summary="Get configuration",
        description="Retrieve system configuration and settings",
        responses={
            200: {"description": "Configuration retrieved successfully"}
        }
    )
    async def get_config():
        """
        Get system configuration
        
        **Returns:**
        - **status**: Operation status
        - **supported_languages**: List of supported language codes
        - **services**: Available booking services
        - **settings**: System settings
          - max_sessions: Maximum concurrent sessions
          - session_ttl_hours: Session time-to-live in hours
          - max_otp_attempts: Maximum OTP verification attempts
          - otp_expiry_minutes: OTP expiration time in minutes
        """
        return await endpoints.get_config()
    
    @router.get(
        "/metrics",
        summary="Get system metrics",
        description="Retrieve detailed system metrics and statistics",
        responses={
            200: {"description": "Metrics retrieved successfully"}
        }
    )
    async def get_metrics():
        """
        Get detailed system metrics
        
        **Returns:**
        - **status**: Operation status
        - **timestamp**: Current timestamp
        - **memory**: Memory service statistics
        - **fsm**: FSM statistics
          - active_count: Number of active FSMs
          - by_stage: FSM count breakdown by stage
        - **orchestrator**: Orchestrator component counts
          - extractors_count: Number of registered extractors
          - validators_count: Number of registered validators
        """
        return await endpoints.get_metrics()
    
    return router


# ==================== ADDITIONAL UTILITY FUNCTION ====================

def create_minimal_router(orchestrator) -> APIRouter:
    """
    Create a minimal router with only essential endpoints
    Useful for production deployments with limited endpoints
    
    Args:
        orchestrator: AgentOrchestrator instance
        
    Returns:
        Minimal APIRouter with only chat and health endpoints
    """
    
    router = APIRouter(
        prefix="/agent",
        tags=["Agent Chat - Minimal"]
    )
    
    endpoints = AgentEndpoints(orchestrator)
    
    @router.post(
        "/chat", 
        response_model=AgentChatResponse,
        summary="Send a chat message",
        description="Minimal chat endpoint for production use"
    )
    async def chat(request: AgentChatRequest) -> AgentChatResponse:
        """Send a message to the agent"""
        return await endpoints.chat(request)
    
    @router.get(
        "/health",
        summary="Health check",
        description="Check service health status"
    )
    async def health_check():
        """Health check endpoint"""
        return await endpoints.health_check()
    
    return router