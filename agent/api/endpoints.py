"""
Agent API Endpoints
"""

import logging
from fastapi import HTTPException, Depends
from datetime import datetime
from typing import Dict

from ..models.api_models import AgentChatRequest, AgentChatResponse
from ..orchestrator import AgentOrchestrator
from ..services.memory_service import MemoryService

logger = logging.getLogger(__name__)


class AgentEndpoints:
    """Agent API endpoint handlers"""
    
    def __init__(self, orchestrator: AgentOrchestrator):
        """Initialize endpoints"""
        self.orchestrator = orchestrator
        self.memory_service = orchestrator.memory_service
        
        logger.info("AgentEndpoints initialized")
    
    async def chat(self, request: AgentChatRequest) -> AgentChatResponse:
        """Main chat endpoint"""
        try:
            # Validate request
            self._validate_request(request)
            
            logger.info(f"Chat request: session={request.session_id}, lang={request.language}")
            
            # Process message
            result = await self.orchestrator.process_message(
                message=request.message,
                session_id=request.session_id,
                language=request.language
            )
            
            # Convert to AgentChatResponse
            response = self._build_response(result)
            
            logger.info(f"Chat response: session={response.session_id}, stage={response.stage}")
            
            return response
            
        except ValueError as e:
            logger.warning(f"Validation error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Chat endpoint error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    
    async def get_sessions(self):
        """Get session statistics"""
        try:
            stats = self.memory_service.get_stats()
            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "stats": stats
            }
        except Exception as e:
            logger.error(f"Get sessions error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    async def cleanup(self):
        """Force cleanup of expired sessions"""
        try:
            cleaned = self.memory_service.cleanup_old_sessions()
            return {
                "status": "ok",
                "cleaned": cleaned,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    async def delete_session(self, session_id: str):
        """Delete specific session"""
        try:
            deleted = self.memory_service.delete_session(session_id)
            if deleted:
                return {
                    "status": "ok",
                    "message": "Session deleted",
                    "session_id": session_id
                }
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Delete session error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    async def health_check(self):
        """Health check endpoint"""
        try:
            stats = self.memory_service.get_stats()
            return {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "active_sessions": stats.get("active_sessions", 0),
                "memory_service": "operational"
            }
        except Exception as e:
            logger.error(f"Health check error: {e}")
            raise HTTPException(status_code=503, detail="Service unhealthy")
    
    def _validate_request(self, request: AgentChatRequest) -> None:
        """Validate incoming request"""
        # Message validation
        if not request.message or len(request.message.strip()) == 0:
            raise ValueError("Message cannot be empty")
        
        if len(request.message) > 1000:
            raise ValueError("Message too long (max 1000 characters)")
        
        # Language validation
        if request.language not in ["en", "ne", "hi", "mr"]:
            raise ValueError(f"Unsupported language: {request.language}")
    
    def _build_response(self, result: dict) -> AgentChatResponse:
        """Build response from orchestrator result"""
        try:
            return AgentChatResponse(**result)
        except Exception as e:
            logger.error(f"Error building AgentChatResponse: {e}")
            
            # Create a fallback response
            return AgentChatResponse(
                reply="Sorry, there was an error processing your request.",
                session_id=result.get("session_id", "error"),
                stage="error",
                action="error",
                missing_fields=[],
                collected_info={},
                chat_mode="normal"
            )