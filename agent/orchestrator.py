"""
Agent Orchestrator - OPTIMIZED VERSION
Clean separation of concerns with minimal duplication
"""

import logging
import secrets
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from .models.memory import ConversationMemory
from .models.state import BookingState
from .models.api_models import AgentChatResponse
from .engine.fsm import BookingFSM
from .services.memory_service import MemoryService
from .services.otp_service import OTPService
from .services.booking_service import BookingService
from .services.knowledge_base_service import KnowledgeBaseService
from .prompts.templates import PromptTemplates

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Main orchestrator - delegates to FSM and services"""
    
    MAX_OFF_TRACK_ATTEMPTS = 6
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize orchestrator"""
        self.config = config or {}
        
        # Core components
        self.fsm = BookingFSM()
        self.memory_service = MemoryService()
        self.prompts = PromptTemplates()
        
        # Initialize knowledge base
        try:
            from database import knowledge_collection
            self.knowledge_base = KnowledgeBaseService(knowledge_collection)
        except ImportError:
            logger.warning("Knowledge collection not found")
            self.knowledge_base = KnowledgeBaseService()
        
        # Services initialized on demand
        self.otp_service = None
        self.booking_service = None
        
        logger.info("AgentOrchestrator initialized")
    
    async def process_message(
        self, 
        message: str, 
        session_id: Optional[str] = None, 
        language: str = "en"
    ) -> Dict[str, Any]:
        """Main entry point for processing messages"""
        try:
            # Validate input
            if not message or not message.strip():
                return self._error_response("Message cannot be empty", session_id)
            
            # Get or create session
            memory = self._get_or_create_session(session_id, language)
            
            # Handle special commands
            if self._is_exit_request(message):
                return await self._handle_exit(memory, language)
            
            if self._is_restart_request(message):
                return await self._handle_restart(memory, language)
            
            if self._is_chat_request(message):
                return await self._switch_to_chat_mode(memory, language)
            
            # Handle OTP resend before processing
            if memory.stage == BookingState.OTP_SENT.value:
                if self._is_resend_otp_request(message):
                    return await self._handle_resend_otp(memory, language)
            
            # Add user message to history
            memory.add_message("user", message)
            
            # Process through FSM
            next_state, updated_intent, metadata = self.fsm.process_message(
                message=message,
                current_state=memory.stage,
                intent=memory.intent,
                language=language,
                conversation_history=memory.conversation_history
            )
            
            # Check if FSM understood the message
            understood = metadata.get("understood", False)
            
            if understood:
                # FSM handled it - update memory and process action
                return await self._handle_understood(
                    next_state, updated_intent, metadata, memory, language
                )
            else:
                # FSM didn't understand - handle as question or fallback
                return await self._handle_not_understood(
                    message, memory, language
                )
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return self._error_response(
                "Sorry, I encountered an error. Please try again.",
                session_id or secrets.token_urlsafe(8)
            )
    
    async def _handle_understood(
        self,
        next_state: str,
        updated_intent,
        metadata: Dict,
        memory: ConversationMemory,
        language: str
    ) -> Dict[str, Any]:
        """Handle when FSM understood the message"""
        # Reset off-track counter
        memory.off_track_count = 0
        
        # Update memory
        memory.intent = updated_intent
        memory.stage = next_state
        
        # Handle special actions
        action = metadata.get("action")
        
        if action == "send_otp":
            return await self._handle_send_otp(memory, language)
        
        elif action == "verify_otp":
            otp = metadata.get("otp")
            return await self._handle_verify_otp(otp, memory, language)
        
        elif action == "resend_otp":
            return await self._handle_resend_otp(memory, language)
        
        # Update last shown list
        if hasattr(self.fsm, 'last_shown_list'):
            memory.last_shown_list = self.fsm.last_shown_list
        
        # Add assistant response if provided
        reply = metadata.get("message", "")
        if reply:
            memory.add_message("assistant", reply)
        
        # Update session
        self.memory_service.update_session(memory.session_id, memory)
        
        # Build response
        return self._build_response(
            reply=reply,
            memory=memory,
            action=action or "continue",
            metadata=metadata
        )
    
    async def _handle_not_understood(
        self,
        message: str,
        memory: ConversationMemory,
        language: str
    ) -> Dict[str, Any]:
        """Handle when FSM didn't understand the message"""
        logger.info(f"FSM did not understand, checking alternatives...")
        
        # Increment off-track counter
        memory.off_track_count += 1
        
        # Check if exceeded max attempts
        if memory.off_track_count >= self.MAX_OFF_TRACK_ATTEMPTS:
            logger.info(f"Too many off-track attempts, switching to chat mode")
            return await self._switch_to_chat_mode(memory, language)
        
        # Try to answer as question
        try:
            answer = await self._answer_question(message, memory, language)
            
            if answer:
                # Check if we're in booking mode
                state = BookingState.from_string(memory.stage)
                
                if state.is_booking_flow():
                    # BOOKING MODE: Show answer + reminder + spacing + continuation
                    continuation = self._get_booking_continuation(memory, language)
                    
                    if continuation:
                        # answer already has reminder + \n at the end
                        # Add one more \n for blank line before continuation
                        reply = answer + "\n" + continuation
                    else:
                        reply = answer
                else:
                    # NOT IN BOOKING MODE: Just show answer, no spacing, no continuation
                    reply = answer
                
                memory.add_message("assistant", reply)
                self.memory_service.update_session(memory.session_id, memory)
                
                return self._build_response(
                    reply=reply,
                    memory=memory,
                    action="question_answered",
                    metadata={
                        "off_track_count": memory.off_track_count,
                        "max_attempts": self.MAX_OFF_TRACK_ATTEMPTS
                    }
                )
            
        except Exception as e:
            logger.error(f"Error answering question: {e}")
        
        # Fallback - show current state continuation
        continuation = self._get_booking_continuation(memory, language)
        reply = continuation or "Please continue with your booking."
        
        memory.add_message("assistant", reply)
        self.memory_service.update_session(memory.session_id, memory)
        
        return self._build_response(
            reply=reply,
            memory=memory,
            action="continue",
            metadata={"fallback": True}
        )
    
    async def _answer_question(
        self,
        question: str,
        memory: ConversationMemory,
        language: str
    ) -> Optional[str]:
        """Answer question using knowledge base with clean formatting"""
        # Build context
        context_parts = []
        
        if memory.intent.service:
            context_parts.append(f"Service: {memory.intent.service}")
        
        if memory.intent.package:
            context_parts.append(f"Package: {memory.intent.package}")
        
        context_parts.append(f"Stage: {memory.stage}")
        
        missing = memory.intent.missing_fields()
        if missing:
            context_parts.append(f"Waiting for: {', '.join(missing)}")
        
        context = " | ".join(context_parts)
        
        # Get answer from knowledge base
        answer = await self.knowledge_base.get_answer(question, language, context)
        
        # Clean the answer
        if answer:
            answer = self._clean_reply(answer)
            
            # ONLY add booking reminder if in booking flow
            state = BookingState.from_string(memory.stage)
            if state.is_booking_flow():
                # Add reminder with proper spacing and visual separator for booking mode
                separator = "\n" + "─" * 50 + "\n"
                
                if language == "hi":
                    reminder = f"{separator}📌 बुकिंग जारी रखने के लिए जानकारी दें या 'रद्द करें' टाइप करें{separator}"
                elif language == "ne":
                    reminder = f"{separator}📌 बुकिङ जारी राख्न जानकारी दिनुहोस् वा 'रद्द गर्नुहोस्' टाइप गर्नुहोस्{separator}"
                else:
                    reminder = f"{separator}📌 Continue booking by providing details or type 'cancel' to exit{separator}"
                
                answer += reminder
        
        return answer
    
    def _get_booking_continuation(
        self,
        memory: ConversationMemory,
        language: str
    ) -> str:
        """Get appropriate continuation message based on current state - CLEAN FORMAT"""
        state = BookingState.from_string(memory.stage)
        
        continuation = ""
        
        if state == BookingState.GREETING:
            continuation = self.prompts.get_service_list(language)
        
        elif state == BookingState.SELECTING_SERVICE:
            continuation = self.prompts.get_service_list(language)
        
        elif state == BookingState.SELECTING_PACKAGE:
            if memory.intent.service:
                continuation = self.prompts.get_package_options(memory.intent.service, language)
            else:
                continuation = self.prompts.get_service_list(language)
        
        elif state == BookingState.COLLECTING_DETAILS:
            missing = memory.intent.missing_fields()
            if missing:
                continuation = self.prompts.get_bulk_request_message(missing, language)
            else:
                continuation = self.prompts.get_confirmation_prompt(memory.intent.get_summary(), language)
        
        elif state == BookingState.CONFIRMING:
            continuation = self.prompts.get_confirmation_prompt(memory.intent.get_summary(), language)
        
        elif state == BookingState.OTP_SENT:
            if language == "hi":
                continuation = "कृपया 6-अंकीय OTP दर्ज करें"
            elif language == "ne":
                continuation = "कृपया 6-अङ्कको OTP प्रविष्ट गर्नुहोस्"
            else:
                continuation = "Please enter the 6-digit OTP"
        
        elif state == BookingState.INFO_MODE:
            if language == "hi":
                continuation = "मैं सूचना मोड में हूं। आप मुझसे कुछ भी पूछ सकते हैं।"
            elif language == "ne":
                continuation = "म जानकारी मोडमा छु। तपाईं मसँग केहि पनि सोध्न सक्नुहुन्छ।"
            else:
                continuation = "I'm in information mode. You can ask me anything."
        
        else:
            continuation = "How can I help you?"
        
        # Clean the continuation
        return self._clean_reply(continuation)
    
    async def _switch_to_chat_mode(
        self,
        memory: ConversationMemory,
        language: str
    ) -> Dict[str, Any]:
        """Switch to chat/info mode"""
        memory.reset()
        memory.stage = BookingState.INFO_MODE.value
        
        if language == "hi":
            reply = "मैंने सूचना मोड में स्विच कर दिया है। आप स्वतंत्र रूप से पूछ सकते हैं!"
        elif language == "ne":
            reply = "मैले जानकारी मोडमा स्विच गरेको छु। तपाईं स्वतन्त्र रूपमा सोध्न सक्नुहुन्छ!"
        else:
            reply = "I've switched to information mode. Feel free to ask any questions!"
        
        memory.add_message("assistant", reply)
        self.memory_service.update_session(memory.session_id, memory)
        
        return self._build_response(
            reply=reply,
            memory=memory,
            action="switched_to_info",
            metadata={"chat_mode": "normal"}
        )
    
    async def _handle_exit(
        self,
        memory: ConversationMemory,
        language: str
    ) -> Dict[str, Any]:
        """Handle exit request"""
        memory.reset()
        self.memory_service.update_session(memory.session_id, memory)
        
        reply = self.prompts.get_exit_message(language)
        
        return self._build_response(
            reply=reply,
            memory=memory,
            action="exit",
            metadata={"status": "cancelled"}
        )
    
    async def _handle_restart(
        self,
        memory: ConversationMemory,
        language: str
    ) -> Dict[str, Any]:
        """Handle restart request"""
        memory.reset()
        self.memory_service.update_session(memory.session_id, memory)
        
        reply = self.prompts.get_restart_message(language)
        
        return self._build_response(
            reply=reply,
            memory=memory,
            action="restart",
            metadata={"status": "restarted"}
        )
    
    async def _handle_send_otp(
        self,
        memory: ConversationMemory,
        language: str
    ) -> Dict[str, Any]:
        """Handle OTP sending"""
        try:
            # Initialize OTP service if needed
            if not self.otp_service:
                from config import TWILIO_WHATSAPP_FROM
                from services import twilio_client
                
                self.otp_service = OTPService(
                    twilio_client=twilio_client,
                    from_number=TWILIO_WHATSAPP_FROM,
                    expiry_minutes=5
                )
            
            # Generate IDs and OTP
            booking_id = self.otp_service.generate_booking_id()
            otp = self.otp_service.generate_otp()
            
            # Prepare booking data
            booking_data = {
                "intent": memory.intent.dict(),
                "session_id": memory.session_id,
                "language": language,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Store OTP
            self.otp_service.store_otp_data(
                booking_id=booking_id,
                otp=otp,
                phone=memory.intent.phone,
                booking_data=booking_data,
                language=language
            )
            
            # Send OTP
            otp_sent = self.otp_service.send_otp(
                phone=memory.intent.phone,
                otp=otp,
                language=language
            )
            
            # Update memory
            memory.booking_id = booking_id
            memory.stage = BookingState.OTP_SENT.value
            self.memory_service.update_session(memory.session_id, memory)
            
            # Build response
            reply = self.prompts.get_otp_sent_message(language, memory.intent.phone)
            
            logger.info(f"OTP sent for booking {booking_id[:8]}...")
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="send_otp",
                metadata={
                    "booking_id": booking_id,
                    "next_expected": "OTP verification",
                    "otp_sent": otp_sent
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending OTP: {e}", exc_info=True)
            
            # Revert to confirmation state
            memory.stage = BookingState.CONFIRMING.value
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply="Sorry, there was an error sending OTP. Please try again.",
                memory=memory,
                action="error",
                metadata={"error": str(e)}
            )
    
    async def _handle_verify_otp(
        self,
        otp: str,
        memory: ConversationMemory,
        language: str
    ) -> Dict[str, Any]:
        """Handle OTP verification"""
        if not otp or not memory.booking_id:
            reply = "Please enter the 6-digit OTP."
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="retry",
                metadata={"error": "No OTP provided"}
            )
        
        try:
            # Initialize OTP service if needed
            if not self.otp_service:
                from config import TWILIO_WHATSAPP_FROM
                from services import twilio_client
                
                self.otp_service = OTPService(
                    twilio_client=twilio_client,
                    from_number=TWILIO_WHATSAPP_FROM,
                    expiry_minutes=5
                )
            
            # Verify OTP
            verification_result = self.otp_service.verify_otp(memory.booking_id, otp)
            
            if not verification_result.get("valid", False):
                # OTP invalid
                memory.otp_attempts += 1
                
                if memory.otp_attempts >= 3 or verification_result.get("should_restart"):
                    # Too many attempts or expired - reset
                    memory.reset()
                    self.memory_service.update_session(memory.session_id, memory)
                    
                    error_msg = verification_result.get("error", "Too many failed attempts")
                    reply = f"{error_msg}. Please start a new booking."
                    
                    return self._build_response(
                        reply=reply,
                        memory=memory,
                        action="reset",
                        metadata={"status": "otp_failed"}
                    )
                
                # Show error with attempts left
                attempts_left = 3 - memory.otp_attempts
                error_msg = verification_result.get("error", "Invalid OTP")
                reply = f"{error_msg}"
                
                memory.add_message("assistant", reply)
                self.memory_service.update_session(memory.session_id, memory)
                
                return self._build_response(
                    reply=reply,
                    memory=memory,
                    action="retry",
                    metadata={"attempts_left": attempts_left}
                )
            
            # OTP verified - save booking
            logger.info(f"OTP verified, saving booking...")
            
            # Initialize booking service if needed
            if not self.booking_service:
                from database import booking_collection
                from services import twilio_client
                from config import TWILIO_WHATSAPP_FROM
                
                self.booking_service = BookingService(
                    booking_collection=booking_collection,
                    twilio_client=twilio_client,
                    whatsapp_from=TWILIO_WHATSAPP_FROM
                )
            
            # Create and save booking
            booking_data = self.booking_service.create_booking_payload(memory)
            saved_booking_id = self.booking_service.save_booking(booking_data)
            
            # Delete OTP data
            verified_booking_id = verification_result.get("booking_id")
            if verified_booking_id:
                self.otp_service.delete_otp_data(verified_booking_id)
            
            # Send confirmation
            if memory.intent.phone:
                self.booking_service.send_confirmation_whatsapp(
                    memory.intent.phone,
                    booking_data,
                    language
                )
            
            # Build success response
            reply = self.prompts.get_booking_confirmed_message(language, memory.intent.name)
            
            # Reset memory
            memory.reset()
            self.memory_service.update_session(memory.session_id, memory)
            
            logger.info(f"Booking completed: {saved_booking_id}")
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="booking_confirmed",
                metadata={
                    "booking_id": saved_booking_id,
                    "status": "completed"
                }
            )
            
        except Exception as e:
            logger.error(f"Error verifying OTP: {e}", exc_info=True)
            
            reply = "Error saving booking. Your OTP is still valid, please try again."
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="error",
                metadata={"error": str(e)}
            )
    
    async def _handle_resend_otp(
        self,
        memory: ConversationMemory,
        language: str
    ) -> Dict[str, Any]:
        """Handle OTP resend request"""
        logger.info(f"OTP resend requested for session {memory.session_id}")
        
        try:
            # Initialize OTP service if needed
            if not self.otp_service:
                from config import TWILIO_WHATSAPP_FROM
                from services import twilio_client
                
                self.otp_service = OTPService(
                    twilio_client=twilio_client,
                    from_number=TWILIO_WHATSAPP_FROM,
                    expiry_minutes=5
                )
            
            if not memory.booking_id:
                reply = "No active OTP session. Please confirm your booking details first."
                memory.add_message("assistant", reply)
                self.memory_service.update_session(memory.session_id, memory)
                
                return self._build_response(
                    reply=reply,
                    memory=memory,
                    action="error",
                    metadata={"error": "No booking_id"}
                )
            
            # Resend OTP
            resend_result = self.otp_service.resend_otp(memory.booking_id)
            
            if resend_result.get("success"):
                reply = f"A fresh OTP has been sent to {memory.intent.phone}."
            elif resend_result.get("error"):
                reply = resend_result.get("error")
            else:
                reply = "Could not resend OTP. Please try again."
            
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="resend_otp",
                metadata={"resend_result": resend_result}
            )
            
        except Exception as e:
            logger.error(f"Error resending OTP: {e}", exc_info=True)
            
            reply = "Sorry, there was an error resending the OTP. Please try again."
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="error",
                metadata={"error": str(e)}
            )
    
    def _get_or_create_session(
        self,
        session_id: Optional[str],
        language: str
    ) -> ConversationMemory:
        """Get existing session or create new one"""
        if session_id:
            memory = self.memory_service.get_session(session_id)
            if memory:
                return memory
        
        # Create new session
        new_session_id = self.memory_service.create_session(language)
        return self.memory_service.get_session(new_session_id)
    
    def _is_exit_request(self, message: str) -> bool:
        """Check if message is exit request"""
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in ['exit', 'cancel', 'quit', 'stop', 'abort'])
    
    def _is_restart_request(self, message: str) -> bool:
        """Check if message is restart request"""
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in ['restart', 'start over', 'reset', 'new booking'])
    
    def _is_resend_otp_request(self, message: str) -> bool:
        """Check if message is resend OTP request"""
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in ['resend', 'send again', 'missed', 'didn\'t get'])
    
    def _is_chat_request(self, message: str) -> bool:
        """Check if user wants chat mode"""
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in [
            'chat mode', 'just chat', 'don\'t book', 'no booking',
            'only chat', 'switch to chat'
        ])
    
    def _build_response(
        self,
        reply: str,
        memory: ConversationMemory,
        action: str,
        metadata: Dict = None
    ) -> Dict[str, Any]:
        """Build standardized response"""
        metadata = metadata or {}
        
        # Clean reply
        reply = self._clean_reply(reply)
        
        # Determine chat mode
        state = BookingState.from_string(memory.stage)
        chat_mode = "normal" if state in [BookingState.GREETING, BookingState.INFO_MODE] else "agent"
        
        # Override with metadata if provided
        if "chat_mode" in metadata:
            chat_mode = metadata["chat_mode"]
        
        response_data = {
            "reply": reply,
            "session_id": memory.session_id,
            "stage": memory.stage,
            "action": action,
            "missing_fields": memory.intent.missing_fields(),
            "collected_info": memory.intent.get_summary(),
            "chat_mode": chat_mode,
            "next_expected": metadata.get("next_expected"),
            "booking_id": metadata.get("booking_id"),
            "off_track_count": memory.off_track_count
        }
        
        # Add extra metadata
        for key, value in metadata.items():
            if key not in response_data:
                response_data[key] = value
        
        try:
            return AgentChatResponse(**response_data).dict()
        except Exception as e:
            logger.error(f"Error building response: {e}")
            return response_data
    
    def _error_response(self, error_message: str, session_id: str) -> Dict[str, Any]:
        """Build error response"""
        return {
            "reply": error_message,
            "session_id": session_id or "error",
            "stage": "error",
            "action": "error",
            "missing_fields": [],
            "collected_info": {},
            "chat_mode": "normal",
            "off_track_count": 0
        }
    
    def _clean_reply(self, reply: str) -> str:
        """Clean and normalize reply text - Remove ALL markdown but KEEP intentional line breaks"""
        if not reply:
            return reply
        
        import re
        
        # Remove ALL markdown formatting
        # 1. Remove bold/italic/emphasis (**, *, ***)
        reply = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', reply)
        reply = reply.replace("*", "")
        
        # 2. Remove markdown headers (##, ###, etc.)
        reply = re.sub(r'^#{1,6}\s+', '', reply, flags=re.MULTILINE)
        
        # 3. Clean up emoji-based sections (keep emojis but remove ** around text after them)
        reply = re.sub(r'([\U0001F300-\U0001F9FF])\s*\*\*([^*]+)\*\*', r'\1 \2', reply)
        
        # 5. Clean whitespace but PRESERVE intentional line breaks
        # Remove trailing spaces from each line
        lines = [line.rstrip() for line in reply.splitlines()]
        
        # Remove completely empty lines ONLY at start and end
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        
        return reply