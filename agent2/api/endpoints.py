"""
Agent API Endpoints - Enhanced with improved error handling and logging
"""

import logging
from fastapi import HTTPException
from datetime import datetime
from typing import Dict, Any

from ..models.api_models import AgentChatRequest, AgentChatResponse
from ..orchestrator import AgentOrchestrator
from ..services.memory_service import MemoryService
from ..config.config import SUPPORTED_LANGUAGES, AGENT_SETTINGS, SERVICE_LIST

logger = logging.getLogger(__name__)


class AgentEndpoints:
    """Agent API endpoint handlers - Enhanced and optimized"""
    
    def __init__(self, orchestrator: AgentOrchestrator):
        """Initialize endpoints with orchestrator"""
        self.orchestrator = orchestrator
        self.memory_service = orchestrator.memory_service
        
        # Constants
        self.MAX_MESSAGE_LENGTH = 1000
        self.MIN_MESSAGE_LENGTH = 1
        
        logger.info("✅ AgentEndpoints initialized")
    
    # ==================== MAIN CHAT ENDPOINT ====================
    
    async def chat(self, request: AgentChatRequest) -> AgentChatResponse:
        """
        Main chat endpoint - handles user messages
        
        Args:
            request: Chat request with message, session_id, language
            
        Returns:
            AgentChatResponse with reply and state information
            
        Raises:
            HTTPException: For validation errors or internal errors
        """
        start_time = datetime.utcnow()
        
        try:
            # Validate request
            self._validate_request(request)
            
            logger.info(
                f"📨 Chat request: session={request.session_id or 'new'}, "
                f"lang={request.language}, msg_len={len(request.message)}"
            )
            
            # Process message through orchestrator
            result = await self.orchestrator.process_message(
                message=request.message,
                session_id=request.session_id,
                language=request.language
            )
            
            # Build response
            response = self._build_response(result)
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                f"✅ Chat response: session={response.session_id}, "
                f"stage={response.stage}, action={response.action}, "
                f"time={processing_time:.2f}s"
            )
            
            return response
            
        except ValueError as e:
            logger.warning(f"⚠️ Validation error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Chat endpoint error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail="Internal server error occurred while processing your message"
            )
    
    # ==================== SESSION MANAGEMENT ENDPOINTS ====================
    
    async def get_sessions(self) -> Dict[str, Any]:
        """
        Get session statistics
        
        Returns:
            Dictionary with session stats and timestamp
        """
        try:
            stats = self.memory_service.get_stats()
            
            logger.info(f"📊 Session stats requested: {stats.get('active_sessions', 0)} active")
            
            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "stats": stats
            }
        except Exception as e:
            logger.error(f"❌ Get sessions error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail="Failed to retrieve session statistics"
            )
    
    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """
        Get specific session details
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with session information
            
        Raises:
            HTTPException: If session not found
        """
        try:
            memory = self.memory_service.get_session(session_id)
            
            if not memory:
                logger.warning(f"⚠️ Session not found: {session_id}")
                raise HTTPException(status_code=404, detail="Session not found")
            
            logger.info(f"📋 Session details retrieved: {session_id}")
            
            return {
                "status": "ok",
                "session_id": session_id,
                "language": memory.language,
                "stage": memory.stage,
                "created_at": memory.created_at.isoformat(),
                "last_updated": memory.last_updated.isoformat(),
                "message_count": len(memory.conversation_history),
                "off_track_count": memory.off_track_count,
                "has_booking": bool(memory.booking_id),
                "collected_fields": list(memory.intent.get_summary().keys())
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Get session error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail="Failed to retrieve session information"
            )
    
    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """
        Delete specific session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Confirmation message
            
        Raises:
            HTTPException: If session not found or deletion fails
        """
        try:
            deleted = self.memory_service.delete_session(session_id)
            
            if deleted:
                # Also clean up FSM if exists
                if session_id in self.orchestrator.active_fsms:
                    del self.orchestrator.active_fsms[session_id]
                
                logger.info(f"🗑️ Deleted session: {session_id}")
                
                return {
                    "status": "ok",
                    "message": "Session deleted successfully",
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                logger.warning(f"⚠️ Session not found for deletion: {session_id}")
                raise HTTPException(status_code=404, detail="Session not found")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Delete session error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail="Failed to delete session"
            )
    
    async def cleanup(self) -> Dict[str, Any]:
        """
        Force cleanup of expired sessions
        
        Returns:
            Number of cleaned sessions and FSMs
        """
        try:
            logger.info("🧹 Starting forced cleanup...")
            
            cleaned = self.memory_service.cleanup_old_sessions()
            
            # Clean up corresponding FSMs
            fsm_cleaned = 0
            for session_id in list(self.orchestrator.active_fsms.keys()):
                if not self.memory_service.get_session(session_id):
                    del self.orchestrator.active_fsms[session_id]
                    fsm_cleaned += 1
            
            logger.info(f"✅ Cleanup complete: {cleaned} sessions, {fsm_cleaned} FSMs")
            
            return {
                "status": "ok",
                "sessions_cleaned": cleaned,
                "fsms_cleaned": fsm_cleaned,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail="Failed to cleanup sessions"
            )
    
    # ==================== HEALTH & STATUS ENDPOINTS ====================
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Health check endpoint
        
        Returns:
            System health status with metrics
        """
        try:
            stats = self.memory_service.get_stats()
            
            health_status = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "services": {
                    "memory_service": "operational",
                    "orchestrator": "operational",
                    "fsm": "operational"
                },
                "metrics": {
                    "active_sessions": stats.get("active_sessions", 0),
                    "active_fsms": len(self.orchestrator.active_fsms),
                    "total_sessions": stats.get("total_sessions", 0)
                }
            }
            
            logger.debug(f"💚 Health check: {health_status['metrics']}")
            
            return health_status
            
        except Exception as e:
            logger.error(f"❌ Health check error: {e}", exc_info=True)
            raise HTTPException(
                status_code=503, 
                detail="Service unhealthy"
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """
        Get configuration information
        
        Returns:
            System configuration details
        """
        try:            
            config = {
                "status": "ok",
                "supported_languages": SUPPORTED_LANGUAGES,
                "services": SERVICE_LIST,
                "settings": {
                    "max_sessions": AGENT_SETTINGS.get("max_sessions"),
                    "session_ttl_hours": AGENT_SETTINGS.get("session_ttl_hours"),
                    "max_otp_attempts": AGENT_SETTINGS.get("max_otp_attempts"),
                    "otp_expiry_minutes": AGENT_SETTINGS.get("otp_expiry_minutes")
                }
            }
            
            logger.info("⚙️ Configuration retrieved")
            
            return config
            
        except Exception as e:
            logger.error(f"❌ Get config error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail="Failed to retrieve configuration"
            )
    
    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get detailed system metrics
        
        Returns:
            Detailed metrics dictionary
        """
        try:
            stats = self.memory_service.get_stats()
            
            # Calculate FSM metrics
            fsm_by_stage = {}
            for fsm in self.orchestrator.active_fsms.values():
                stage = fsm.current_state.value
                fsm_by_stage[stage] = fsm_by_stage.get(stage, 0) + 1
            
            metrics = {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "memory": stats,
                "fsm": {
                    "active_count": len(self.orchestrator.active_fsms),
                    "by_stage": fsm_by_stage
                },
                "orchestrator": {
                    "extractors_count": len(self.orchestrator.extractors),
                    "validators_count": len(self.orchestrator.validators)
                }
            }
            
            logger.info(f"📊 Metrics retrieved: {metrics['fsm']['active_count']} active FSMs")
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ Get metrics error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail="Failed to retrieve metrics"
            )
    
    # ==================== VALIDATION & HELPERS ====================
    
    def _validate_request(self, request: AgentChatRequest) -> None:
        """
        Validate incoming chat request
        
        Args:
            request: Chat request to validate
            
        Raises:
            ValueError: If request is invalid
        """
        # Message validation
        if not request.message:
            raise ValueError("Message cannot be empty")
        
        message_stripped = request.message.strip()
        
        if len(message_stripped) < self.MIN_MESSAGE_LENGTH:
            raise ValueError("Message is too short")
        
        if len(request.message) > self.MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"Message too long (max {self.MAX_MESSAGE_LENGTH} characters)"
            )
        
        # Language validation
        if request.language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language: {request.language}. "
                f"Supported: {', '.join(SUPPORTED_LANGUAGES)}"
            )
        
        # Session ID validation (if provided)
        if request.session_id:
            if len(request.session_id) > 100:
                raise ValueError("Session ID too long (max 100 characters)")
            if not request.session_id.strip():
                raise ValueError("Session ID cannot be empty or whitespace")
    
    def _build_response(self, result: Dict[str, Any]) -> AgentChatResponse:
        """
        Build response from orchestrator result
        
        Args:
            result: Result dictionary from orchestrator
            
        Returns:
            AgentChatResponse object
        """
        try:
            return AgentChatResponse(**result)
        except Exception as e:
            logger.error(
                f"❌ Error building AgentChatResponse: {e}", 
                exc_info=True
            )
            logger.debug(f"Original result data: {result}")
            
            # Create fallback response
            return AgentChatResponse(
                reply="Sorry, there was an error processing your request. Please try again.",
                session_id=result.get("session_id", "error"),
                stage=result.get("stage", "error"),
                action="error",
                missing_fields=[],
                collected_info={},
                chat_mode="normal",
                off_track_count=0
            )