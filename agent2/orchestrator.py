# agent/orchestrator.py
"""
Enhanced Orchestrator with Better Flow Control
"""

import logging
import secrets
from datetime import datetime
from typing import Dict, Any, Optional

from .models.memory import ConversationMemory
from .models.state import BookingState
from .models.api_models import AgentChatResponse
from .engine.fsm import BookingFSM
from .services.memory_service import MemoryService
from .services.knowledge_base_service import KnowledgeBaseService
from .config.config import AGENT_SETTINGS

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Enhanced orchestrator with better question handling"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.settings = AGENT_SETTINGS
        
        # Core services
        self.memory_service = MemoryService()
        self.knowledge_base = KnowledgeBaseService()
        
        # Active FSMs per session
        self.active_fsms = {}
        
        logger.info("✅ AgentOrchestrator initialized")
    
    # agent/orchestrator.py (UPDATE process_message method)

    async def process_message(self, message: str, session_id: Optional[str] = None, language: str = "en") -> Dict[str, Any]:
        """Process message with enhanced flow"""
        try:
            logger.info(f"📨 Processing: session={session_id}, lang={language}")
            
            # Validate input
            if not message or len(message.strip()) == 0:
                return self._build_error_response("Message cannot be empty", session_id, language)
            
            # Get or create session
            memory = self._get_or_create_session(session_id, language)
            
            # Initialize FSM for session
            if memory.session_id not in self.active_fsms:
                self.active_fsms[memory.session_id] = BookingFSM(memory.session_id, language)
            
            fsm = self.active_fsms[memory.session_id]
            
            # Handle special requests
            special_response = await self._handle_special_requests(message, memory, language)
            if special_response:
                return special_response
            
            # Add user message
            memory.add_message("user", message)
            
            # Process through FSM
            fsm_result = await fsm.process_message(message)
            
            # Extract result
            response_text = fsm_result.get("response", "")
            next_state = fsm_result.get("next_state", memory.stage)
            action = fsm_result.get("action", "continue")
            off_topic = fsm_result.get("off_topic", False)
            off_topic_count = fsm_result.get("off_topic_count", 0)
            
            # Handle OTP actions
            if action in ["send_otp", "resend_otp"]:
                return await self._handle_otp_action(action, memory, language)
            
            # Update memory from FSM
            memory.intent = fsm.memory.intent
            memory.stage = next_state
            memory.off_track_count = off_topic_count
            
            # Add assistant response
            if response_text:
                memory.add_message("assistant", response_text)
            
            # Update session
            self.memory_service.update_session(memory.session_id, memory)
            
            # Build response
            return self._build_response(
                response_text,
                memory,
                action,
                fsm_result,
                off_topic=off_topic
            )
            
        except Exception as e:
            logger.error(f"❌ Error: {e}", exc_info=True)
            error_session = session_id or secrets.token_urlsafe(8)
            return self._build_error_response(
                "Sorry, I encountered an error. Please try again.",
                error_session,
                language
            )

    async def _handle_otp_action(self, action: str, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle OTP actions"""
        try:
            # For demo purposes, just simulate OTP
            if action == "send_otp":
                memory.stage = "OTP_SENT"
                response = f"🔢 **OTP sent to {memory.intent.phone or 'your phone'}.**\n\nPlease enter the 6-digit OTP."
            elif action == "resend_otp":
                response = f"🔄 **OTP resent to {memory.intent.phone or 'your phone'}.**\n\nPlease enter the new 6-digit OTP."
            else:
                response = "Please enter the 6-digit OTP."
            
            memory.add_message("assistant", response)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(response, memory, action, {})
            
        except Exception as e:
            logger.error(f"OTP error: {e}")
            error_response = "Sorry, there was an issue with OTP. Please try again."
            return self._build_response(error_response, memory, "error", {})
    
    # agent/orchestrator.py (UPDATE _handle_special_requests)

    async def _handle_special_requests(
        self, 
        message: str, 
        memory: ConversationMemory, 
        language: str
    ) -> Optional[Dict[str, Any]]:
        """Handle special requests"""
        msg_lower = message.lower()
        
        # Exit
        if any(word in msg_lower for word in ['exit', 'quit', 'cancel', 'stop']):
            return await self._handle_exit(memory, language)
        
        # Restart
        if any(word in msg_lower for word in ['restart', 'start over', 'reset']):
            return await self._handle_restart(memory, language)
        
        # Chat mode
        if any(word in msg_lower for word in ['chat mode', 'just chat', 'only chat']):
            return await self._switch_to_chat_mode(memory, language)
        
        # OTP resend
        if memory.stage == BookingState.OTP_SENT.value:
            resend_keywords = ['resend', 'send again', 'didnt get', 'did not get', 
                            'not received', 'havent got', 'no otp', 'missed']
            if any(keyword in msg_lower for keyword in resend_keywords):
                return await self._handle_resend_otp(memory, language)
        
        return None
    
    async def _handle_exit(self, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle exit"""
        memory.reset()
        self.memory_service.update_session(memory.session_id, memory)
        
        # Clean up FSM
        if memory.session_id in self.active_fsms:
            del self.active_fsms[memory.session_id]
        
        response = "Booking cancelled. Have a great day!"
        return self._build_response(response, memory, "exit", {})
    
    async def _handle_restart(self, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle restart"""
        memory.reset()
        self.memory_service.update_session(memory.session_id, memory)
        
        # Reset FSM
        if memory.session_id in self.active_fsms:
            self.active_fsms[memory.session_id] = BookingFSM(memory.session_id, language)
        
        response = "Let's start over. How can I help you?"
        return self._build_response(response, memory, "restart", {})
    
    async def _switch_to_chat_mode(self, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Switch to chat mode"""
        memory.reset()
        memory.stage = "CHAT_MODE"
        self.memory_service.update_session(memory.session_id, memory)
        
        # Reset FSM
        if memory.session_id in self.active_fsms:
            del self.active_fsms[memory.session_id]
        
        response = "I've switched to chat mode. You can ask me anything!"
        return self._build_response(response, memory, "chat_mode", {})
    
    def _get_or_create_session(self, session_id: Optional[str], language: str) -> ConversationMemory:
        """Get or create session"""
        if session_id:
            memory = self.memory_service.get_session(session_id)
            if memory:
                return memory
        
        # Create new session
        new_session_id = self.memory_service.create_session(language)
        return self.memory_service.get_session(new_session_id)
    
    def _build_response(
        self, 
        reply: str, 
        memory: ConversationMemory, 
        action: str, 
        metadata: Dict[str, Any],
        off_topic: bool = False
    ) -> Dict[str, Any]:
        """Build response"""
        # Determine chat mode
        chat_mode = "normal" if memory.stage in ["GREETING", "CHAT_MODE"] else "agent"
        
        # Build response
        response_data = {
            "reply": reply,
            "session_id": memory.session_id,
            "stage": memory.stage,
            "action": action,
            "missing_fields": memory.intent.missing_fields(),
            "collected_info": memory.intent.get_summary(),
            "chat_mode": chat_mode,
            "off_track_count": memory.off_track_count,
            "off_topic": off_topic
        }
        
        # Add metadata
        response_data.update(metadata)
        
        try:
            return AgentChatResponse(**response_data).dict()
        except Exception as e:
            logger.error(f"Error building response: {e}")
            return response_data
    
    def _build_error_response(
        self, 
        error_message: str, 
        session_id: str, 
        language: str
    ) -> Dict[str, Any]:
        """Build error response"""
        return {
            "reply": error_message,
            "session_id": session_id or "error",
            "stage": "error",
            "action": "error",
            "missing_fields": [],
            "collected_info": {},
            "chat_mode": "normal",
            "off_track_count": 0,
            "off_topic": False
        }