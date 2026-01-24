# agent/orchestrator.py
"""
Agent Orchestrator - FIXED with proper question answering during booking
"""

import logging
import secrets
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
import re

from .models.memory import ConversationMemory
from .models.state import BookingState
from .models.api_models import AgentChatResponse
from .engine.fsm import BookingFSM
from .services.memory_service import MemoryService
from .services.otp_service import OTPService
from .services.booking_service import BookingService
from .services.knowledge_base_service import KnowledgeBaseService
from .engine.intent_detector import IntentDetector
from .prompts.templates import PromptTemplates

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Main orchestrator for agent operations"""
    
    # Maximum off-track attempts before switching to chat mode
    MAX_OFF_TRACK_ATTEMPTS = 6
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize orchestrator"""
        self.config = config or {}
        
        # Initialize components
        self._initialize_components()
        
        logger.info("AgentOrchestrator initialized")
    
    def _initialize_components(self):
        """Initialize all components (FSM, services, handlers)"""
        self.fsm = BookingFSM()
        self.memory_service = MemoryService()
        self.intent_detector = IntentDetector()
        self.prompt_templates = PromptTemplates()
        
        # Initialize knowledge base service
        try:
            from database import knowledge_collection
            self.knowledge_base_service = KnowledgeBaseService(knowledge_collection)
        except ImportError:
            logger.warning("Knowledge collection not found, using default")
            self.knowledge_base_service = KnowledgeBaseService()
        
        # Services will be initialized when needed
        self.otp_service = None
        self.booking_service = None
        
        logger.info("All components initialized")
    
    async def process_message(self, message: str, session_id: Optional[str] = None, language: str = "en") -> Dict[str, Any]:
        """Main entry point for processing user messages"""
        try:
            logger.info(f"Processing message: session={session_id}, lang={language}, msg='{message[:50]}...'")
            
            # Validate input
            if not message or len(message.strip()) == 0:
                return self._build_error_response("Message cannot be empty", session_id)
            
            # Get or create session
            memory = self._get_or_create_session(session_id, language)
            
            # Check for exit/restart requests
            if self._is_exit_request(message):
                return await self._handle_exit(memory, language)
            
            if self._is_restart_request(message):
                return await self._handle_restart(memory, language)
            
            # Check for OTP resend request BEFORE processing
            if memory.stage == BookingState.OTP_SENT.value:
                if self._is_resend_otp_request(message):
                    return await self._handle_resend_otp(memory, language)
            
            # Add user message to history
            memory.add_message("user", message)
            
            # Process through FSM
            fsm_result = self.fsm.process_message(
                message=message,
                current_state=memory.stage,
                intent=memory.intent,
                language=language,
                conversation_history=memory.conversation_history
            )
            
            next_state, updated_intent, metadata = fsm_result
            
            # Check if FSM understood the message
            fsm_understood = metadata.get("understood", False)
            
            if fsm_understood:
                # FSM understood - reset off-track counter
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
                
                # Update last shown list if provided
                if hasattr(self.fsm, 'last_shown_list'):
                    memory.last_shown_list = self.fsm.last_shown_list
                
                # Add assistant response to history if provided
                reply = metadata.get("message", "")
                if reply:
                    memory.add_message("assistant", reply)
                
                # Update session
                self.memory_service.update_session(memory.session_id, memory)
                
                # Build response
                return await self._handle_fsm_result(fsm_result, message, memory, language)
            
            else:
                # ✅ FSM did NOT understand - this is a QUESTION during booking
                logger.info(f"📚 FSM detected QUESTION during booking, answering...")
                
                # Increment off-track counter
                memory.off_track_count += 1
                
                # Check if we should switch to chat mode
                if memory.off_track_count >= self.MAX_OFF_TRACK_ATTEMPTS:
                    logger.info(f"⚠️ Too many off-track attempts ({memory.off_track_count}), switching to chat mode")
                    return await self._switch_to_chat_mode(memory, language)
                
                # ✅ Handle as question during booking
                return await self._handle_question_during_booking(message, memory, language)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            
            session_id_for_error = session_id if session_id else secrets.token_urlsafe(8)
            
            return self._build_error_response(
                "Sorry, I encountered an error. Please try again.",
                session_id_for_error
            )
    
    async def _handle_question_during_booking(self, message: str, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Answer question using knowledge base and continue booking"""
        try:
            logger.info(f"📚 Answering question during booking (off-track count: {memory.off_track_count}/{self.MAX_OFF_TRACK_ATTEMPTS})")
            
            # Check if we're asking for year
            date_info = memory.intent.metadata.get('date_info', {})
            if date_info.get('needs_year', False):
                # Check if this is a year response
                if self._is_year_response(message):
                    # Handle year response
                    year_match = re.search(r'\b(20[2-9][0-9]|2100)\b', message)
                    if year_match:
                        year = int(year_match.group(1))
                        
                        # Update the date with provided year
                        if memory.intent.date:
                            try:
                                # Parse current date and update year
                                date_parts = memory.intent.date.split('-')
                                if len(date_parts) == 3:
                                    month = int(date_parts[1])
                                    day = int(date_parts[2])
                                    
                                    # Create new date with provided year
                                    new_date = datetime(year, month, day)
                                    memory.intent.date = new_date.strftime('%Y-%m-%d')
                                    
                                    # Update metadata
                                    memory.intent.metadata['date_info']['needs_year'] = False
                                    memory.intent.metadata['date_info']['user_provided_year'] = year
                                    memory.intent.metadata['date_info']['assumed_year'] = year
                                    
                                    # Show updated summary
                                    missing = memory.intent.missing_fields()
                                    summary = self.fsm._get_collected_summary_prompt(memory.intent, missing, language)
                                    
                                    reply = f"✅ **Year updated to {year}**\n\n{summary}"
                                    
                                    memory.add_message("assistant", reply)
                                    self.memory_service.update_session(memory.session_id, memory)
                                    
                                    return self._build_response(
                                        reply=reply,
                                        memory=memory,
                                        action="year_updated",
                                        metadata={
                                            "year_provided": year,
                                            "updated_date": memory.intent.date
                                        }
                                    )
                            except Exception as e:
                                logger.error(f"Error updating year: {e}")
            
            # Build context about current booking state
            context = self._build_booking_context(memory)
            
            # Get answer from knowledge base using LLM
            answer = await self.knowledge_base_service.get_answer(message, language, context)
            
            # Get current state and show collected summary + missing fields
            state_enum = BookingState.from_string(memory.stage)
            missing = memory.intent.missing_fields()
            
            if state_enum == BookingState.COLLECTING_DETAILS and missing:
                # Show what we have and what we need
                continuation = self.fsm._get_collected_summary_prompt(memory.intent, missing, language)
            else:
                # For other states, use standard continuation
                continuation = self._get_booking_continuation(state_enum, memory, language)
            
            # Combine: Answer + booking continuation
            if answer and continuation:
                reply = f"{answer}\n\n{continuation}"
            elif answer:
                reply = answer
            else:
                reply = continuation
            
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="question_answered",
                metadata={
                    "question": message,
                    "answer": answer,
                    "off_track_count": memory.off_track_count,
                    "max_attempts": self.MAX_OFF_TRACK_ATTEMPTS
                }
            )
            
        except Exception as e:
            logger.error(f"Error answering question: {e}", exc_info=True)
            
            # Fallback: just continue with booking
            state_enum = BookingState.from_string(memory.stage)
            continuation = self._get_booking_continuation(state_enum, memory, language)
            
            reply = f"I understand. {continuation}"
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="continue",
                metadata={"error": str(e)}
            )
    

    def _is_year_response(self, message: str) -> bool:
        """Check if message contains a valid year"""
        year_match = re.search(r'\b(20[2-9][0-9]|2100)\b', message)
        return bool(year_match)


    def _get_booking_continuation(self, state_enum: BookingState, memory: ConversationMemory, language: str) -> str:
        """Get the next step to continue booking"""
        
        if state_enum == BookingState.GREETING:
            return self.prompt_templates.get_service_list(language)
        
        elif state_enum == BookingState.SELECTING_SERVICE:
            return self.prompt_templates.get_service_list(language)
        
        elif state_enum == BookingState.SELECTING_PACKAGE:
            if memory.intent.service:
                return self.fsm._get_package_prompt(memory.intent.service, language)
            else:
                return self.prompt_templates.get_service_list(language)
        
        elif state_enum == BookingState.COLLECTING_DETAILS:
            # Check what's missing and ask for it
            missing = memory.intent.missing_fields()
            
            if not missing:
                # All details collected - move to confirmation
                summary = memory.intent.get_summary()
                return self.prompt_templates.get_confirmation_prompt(summary, language)
            
            # If we just entered details collection, show full prompt
            if memory.off_track_count == 0 or len(missing) >= 5:
                return self.fsm._get_details_prompt(memory.intent, language)
            else:
                # Ask for specific missing field(s)
                if len(missing) == 1:
                    return self._get_field_specific_prompt(missing[0], language)
                else:
                    return self.fsm._get_missing_fields_prompt(missing, language)
        
        elif state_enum == BookingState.CONFIRMING:
            summary = memory.intent.get_summary()
            return self.prompt_templates.get_confirmation_prompt(summary, language)
        
        elif state_enum == BookingState.OTP_SENT:
            if language == "hi":
                return "🔢 **कृपया 6-अंकीय OTP दर्ज करें:**"
            elif language == "ne":
                return "🔢 **कृपया 6-अङ्कको OTP प्रविष्ट गर्नुहोस्:**"
            elif language == "mr":
                return "🔢 **कृपया 6-अंकी OTP प्रविष्ट करा:**"
            else:
                return "🔢 **Please enter the 6-digit OTP:**"
        
        else:
            if language == "hi":
                return "📋 बुकिंग जारी रखें।"
            elif language == "ne":
                return "📋 बुकिङ जारी राख्नुहोस्।"
            elif language == "mr":
                return "📋 बुकिंग सुरू ठेवा."
            else:
                return "📋 Continue with booking."
    
    def _get_full_details_prompt(self, language: str) -> str:
        """Get full details prompt asking for all details at once"""
        if language == "hi":
            return """📋 **कृपया अपना विवरण दें:**

आप एक बार में सभी विवरण दे सकते हैं:

• **पूरा नाम:**
• **व्हाट्सएप नंबर** (देश कोड के साथ, जैसे +919876543210):
• **ईमेल:**
• **इवेंट तारीख** (जैसे 25 मार्च 2025):
• **इवेंट स्थान:**
• **पिन कोड:**
• **देश** (भारत/नेपाल/पाकिस्तान/बांग्लादेश/दुबई):

**उदाहरण:** "रमेश कुमार, +919876543210, ramesh@email.com, 15 अप्रैल 2025, दिल्ली, 110001, भारत"

आपका विवरण क्या है?"""
        elif language == "ne":
            return """📋 **कृपया आफ्नो विवरण दिनुहोस्:**

तपाईं एकै पटक सबै विवरण दिन सक्नुहुन्छ:

• **पूरा नाम:**
• **व्हाट्सएप नम्बर** (देश कोड सहित, जस्तै +9779876543210):
• **इमेल:**
• **कार्यक्रम मिति** (जस्तै 25 मार्च 2025):
• **कार्यक्रम स्थान:**
• **पिन कोड:**
• **देश** (भारत/नेपाल/पाकिस्तान/बंगलादेश/दुबई):

**उदाहरण:** "रमेश कुमार, +9779876543210, ramesh@email.com, 15 अप्रैल 2025, काठमाडौं, 44600, नेपाल"

तपाईंको विवरण के हो?"""
        elif language == "mr":
            return """📋 **कृपया तुमचे तपशील द्या:**

तुम्ही एकाच वेळी सर्व तपशील देऊ शकता:

• **पूर्ण नाव:**
• **व्हाट्सएप नंबर** (देश कोडसह, उदा. +919876543210):
• **ईमेल:**
• **कार्यक्रम तारीख** (उदा. 25 मार्च 2025):
• **कार्यक्रम स्थान:**
• **पिन कोड:**
• **देश** (भारत/नेपाळ/पाकिस्तान/बांग्लादेश/दुबई):

**उदाहरण:** "रमेश कुमार, +919876543210, ramesh@email.com, 15 एप्रिल 2025, मुंबई, 400001, भारत"

तुमचे तपशील काय आहेत?"""
        else:
            return """📋 **Please provide your details:**

You can provide all details at once:

• **Full Name:**
• **WhatsApp Number** (with country code, e.g., +919876543210):
• **Email:**
• **Event Date** (e.g., March 25, 2025):
• **Event Location:**
• **PIN Code:**
• **Country** (India/Nepal/Pakistan/Bangladesh/Dubai):

**Example:** "Ramesh Kumar, +919876543210, ramesh@email.com, April 15, 2025, Delhi, 110001, India"

What are your details?"""
    
    def _get_field_specific_prompt(self, field: str, language: str) -> str:
        """Get prompt for specific missing field"""
        prompts = {
            "en": {
                "name": "📝 **Please provide your full name:**",
                "phone": "📱 **Please provide your WhatsApp number:** (with country code, e.g., +919876543210)",
                "email": "📧 **Please provide your email:**",
                "event_date": "📅 **Please provide event date:** (e.g., March 25, 2025)",
                "location": "📍 **Please provide event location:**",
                "pincode": "📮 **Please provide PIN code:**",
                "service_country": "🌍 **Please provide country:** (India/Nepal/Pakistan/Bangladesh/Dubai)"
            },
            "hi": {
                "name": "📝 **कृपया अपना पूरा नाम दें:**",
                "phone": "📱 **कृपया व्हाट्सएप नंबर दें:** (देश कोड के साथ, जैसे +919876543210)",
                "email": "📧 **कृपया ईमेल दें:**",
                "event_date": "📅 **कृपया इवेंट तारीख दें:** (जैसे 25 मार्च 2025)",
                "location": "📍 **कृपया इवेंट स्थान दें:**",
                "pincode": "📮 **कृपया पिन कोड दें:**",
                "service_country": "🌍 **कृपया देश दें:** (भारत/नेपाल/पाकिस्तान/बांग्लादेश/दुबई)"
            },
            "ne": {
                "name": "📝 **कृपया आफ्नो पूरा नाम दिनुहोस्:**",
                "phone": "📱 **कृपया व्हाट्सएप नम्बर दिनुहोस्:** (देश कोड सहित, जस्तै +9779876543210)",
                "email": "📧 **कृपया इमेल दिनुहोस्:**",
                "event_date": "📅 **कृपया कार्यक्रम मिति दिनुहोस्:** (जस्तै 25 मार्च 2025)",
                "location": "📍 **कृपया कार्यक्रम स्थान दिनुहोस्:**",
                "pincode": "📮 **कृपया पिन कोड दिनुहोस्:**",
                "service_country": "🌍 **कृपया देश दिनुहोस्:** (भारत/नेपाल/पाकिस्तान/बंगलादेश/दुबई)"
            },
            "mr": {
                "name": "📝 **कृपया तुमचे पूर्ण नाव द्या:**",
                "phone": "📱 **कृपया व्हाट्सएप नंबर द्या:** (देश कोडसह, उदा. +919876543210)",
                "email": "📧 **कृपया ईमेल द्या:**",
                "event_date": "📅 **कृपया कार्यक्रम तारीख द्या:** (उदा. 25 मार्च 2025)",
                "location": "📍 **कृपया कार्यक्रम स्थान द्या:**",
                "pincode": "📮 **कृपया पिन कोड द्या:**",
                "service_country": "🌍 **कृपया देश द्या:** (भारत/नेपाळ/पाकिस्तान/बांग्लादेश/दुबई)"
            }
        }
        
        lang_prompts = prompts.get(language, prompts["en"])
        return lang_prompts.get(field, f"Please provide: {field}")
    
    def _get_missing_fields_prompt(self, missing_fields: List[str], language: str) -> str:
        """Get prompt for multiple missing fields"""
        field_names = {
            "en": {
                "name": "full name",
                "phone": "phone number",
                "email": "email",
                "event_date": "event date",
                "location": "event location",
                "pincode": "PIN code",
                "service_country": "country"
            },
            "hi": {
                "name": "पूरा नाम",
                "phone": "व्हाट्सएप नंबर",
                "email": "ईमेल",
                "event_date": "इवेंट तारीख",
                "location": "इवेंट स्थान",
                "pincode": "पिन कोड",
                "service_country": "देश"
            },
            "ne": {
                "name": "पूरा नाम",
                "phone": "व्हाट्सएप नम्बर",
                "email": "इमेल",
                "event_date": "कार्यक्रम मिति",
                "location": "कार्यक्रम स्थान",
                "pincode": "पिन कोड",
                "service_country": "देश"
            },
            "mr": {
                "name": "पूर्ण नाव",
                "phone": "व्हाट्सएप नंबर",
                "email": "ईमेल",
                "event_date": "कार्यक्रम तारीख",
                "location": "कार्यक्रम स्थान",
                "pincode": "पिन कोड",
                "service_country": "देश"
            }
        }
        
        lang_fields = field_names.get(language, field_names["en"])
        
        # Get display names for missing fields
        display_fields = [lang_fields.get(field, field) for field in missing_fields]
        
        if len(display_fields) == 1:
            return self._get_field_specific_prompt(missing_fields[0], language)
        else:
            if language == "hi":
                return f"📋 **कृपया दें:** {', '.join(display_fields)}"
            elif language == "ne":
                return f"📋 **कृपया दिनुहोस्:** {', '.join(display_fields)}"
            elif language == "mr":
                return f"📋 **कृपया द्या:** {', '.join(display_fields)}"
            else:
                return f"📋 **Please provide:** {', '.join(display_fields)}"
    
    def _build_booking_context(self, memory: ConversationMemory) -> str:
        """Build context for knowledge base"""
        parts = []
        
        if memory.intent.service:
            parts.append(f"Service: {memory.intent.service}")
        
        if memory.intent.package:
            parts.append(f"Package: {memory.intent.package}")
        
        if memory.intent.name:
            parts.append(f"Name: {memory.intent.name}")
        
        current_stage = BookingState.from_string(memory.stage)
        parts.append(f"Current stage: {current_stage.value}")
        
        # Add missing fields if any
        missing = memory.intent.missing_fields()
        if missing:
            parts.append(f"Waiting for: {', '.join(missing)}")
        
        return " | ".join(parts) if parts else "New booking"
    
    def _get_or_create_session(self, session_id: Optional[str], language: str) -> ConversationMemory:
        """Get or create session"""
        if session_id:
            memory = self.memory_service.get_session(session_id)
            if memory:
                return memory
        new_session_id = self.memory_service.create_session(language)
        return self.memory_service.get_session(new_session_id)
    
    def _is_exit_request(self, message: str) -> bool:
        """Check exit"""
        msg_lower = message.lower()
        exit_keywords = ['exit', 'cancel', 'quit', 'stop', 'nevermind', 'abort']
        return any(kw in msg_lower for kw in exit_keywords)
    
    def _is_restart_request(self, message: str) -> bool:
        """Check restart"""
        msg_lower = message.lower()
        restart_keywords = ['restart', 'start over', 'reset', 'new booking']
        return any(kw in msg_lower for kw in restart_keywords)
    
    def _is_resend_otp_request(self, message: str) -> bool:
        """Check resend OTP"""
        msg_lower = message.lower()
        keywords = ['resend', 'send again', 'missed', 'didn\'t get', 'not received']
        return any(kw in msg_lower for kw in keywords)
    
    async def _switch_to_chat_mode(self, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Switch to chat mode"""
        memory.reset()
        memory.stage = "chat_mode"
        self.memory_service.update_session(memory.session_id, memory)
        
        reply = "I notice you have questions. Feel free to ask, and when ready to book, let me know!"
        memory.add_message("assistant", reply)
        self.memory_service.update_session(memory.session_id, memory)
        
        return self._build_response(reply, memory, "switched_to_chat", {"chat_mode": "normal"})
    
    async def _handle_exit(self, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle exit"""
        memory.reset()
        self.memory_service.update_session(memory.session_id, memory)
        reply = self.prompt_templates.get_exit_message(language)
        return self._build_response(reply, memory, "exit", {"status": "cancelled"})
    
    async def _handle_restart(self, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle restart"""
        memory.reset()
        self.memory_service.update_session(memory.session_id, memory)
        reply = self.prompt_templates.get_restart_message(language)
        return self._build_response(reply, memory, "restart", {"status": "restarted"})
    
    async def _handle_resend_otp(self, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle resend OTP"""
        logger.info(f"OTP resend requested for session {memory.session_id}")
        
        try:
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
            
            resend_result = self.otp_service.resend_otp(memory.booking_id)
            
            if resend_result.get("success"):
                reply = f"A fresh OTP has been sent to {self._mask_phone(memory.intent.phone)}."
            elif resend_result.get("error"):
                error_msg = resend_result.get("error")
                reply = f"{error_msg}"
            else:
                reply = "Could not resend OTP. Please try again."
            
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="resend_otp",
                metadata={
                    "booking_id": memory.booking_id,
                    "next_expected": "OTP verification",
                    "resend_result": resend_result
                }
            )
            
        except Exception as e:
            logger.error(f"Error resending OTP: {e}", exc_info=True)
            
            reply = "Sorry, there was an error resending the OTP. Please try again or contact support."
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="error",
                metadata={"error": str(e)}
            )
    
    def _mask_phone(self, phone: str) -> str:
        """Mask phone"""
        if not phone:
            return "your number"
        
        digits = re.sub(r'\D', '', phone)
        
        if len(digits) >= 10:
            if phone.startswith('+'):
                return f"{phone[:8]}****{digits[-4:]}"
            else:
                return f"+XX{digits[:2]}****{digits[-4:]}"
        
        return phone
    
    async def _handle_fsm_result(self, fsm_result: Tuple, message: str, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle FSM processing result"""
        next_state, updated_intent, metadata = fsm_result
        
        # Build response
        reply = metadata.get("message", "")
        if not reply:
            state_enum = BookingState.from_string(next_state)
            reply = self._get_booking_continuation(state_enum, memory, language)
        
        # Determine chat mode
        chat_mode = "agent" if next_state != BookingState.GREETING.value else "normal"
        
        return self._build_response(
            reply=reply,
            memory=memory,
            action=metadata.get("action", "continue"),
            metadata={
                "collected_info": metadata.get("collected", {}),
                "missing_fields": updated_intent.missing_fields(),
                "next_expected": BookingState.from_string(next_state).get_next_expected(),
                "chat_mode": chat_mode
            }
        )
    
    async def _handle_send_otp(self, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle send OTP"""
        try:
            if not self.otp_service:
                from config import TWILIO_WHATSAPP_FROM
                from services import twilio_client
                
                self.otp_service = OTPService(
                    twilio_client=twilio_client,
                    from_number=TWILIO_WHATSAPP_FROM,
                    expiry_minutes=5
                )
            
            booking_id = self.otp_service.generate_booking_id()
            otp = self.otp_service.generate_otp()
            
            booking_data = {
                "intent": memory.intent.dict(),
                "session_id": memory.session_id,
                "language": language,
                "created_at": datetime.utcnow().isoformat()
            }
            
            self.otp_service.store_otp_data(
                booking_id=booking_id,
                otp=otp,
                phone=memory.intent.phone,
                booking_data=booking_data,
                language=language
            )
            
            otp_sent = self.otp_service.send_otp(
                phone=memory.intent.phone,
                otp=otp,
                language=language
            )
            
            if not otp_sent:
                logger.warning(f"OTP send failed for {memory.intent.phone}")
            
            memory.booking_id = booking_id
            memory.stage = BookingState.OTP_SENT.value
            self.memory_service.update_session(memory.session_id, memory)
            
            reply = self.prompt_templates.get_otp_sent_message(language, memory.intent.phone)
            
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
            
            memory.stage = BookingState.CONFIRMING.value
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply="Sorry, there was an error sending OTP. Please try again or contact support.",
                memory=memory,
                action="error",
                metadata={"error": str(e)}
            )
    
    async def _handle_verify_otp(self, otp: str, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle verify OTP"""
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
            if not self.otp_service:
                from config import TWILIO_WHATSAPP_FROM
                from services import twilio_client
                
                self.otp_service = OTPService(
                    twilio_client=twilio_client,
                    from_number=TWILIO_WHATSAPP_FROM,
                    expiry_minutes=5
                )
            
            verification_result = self.otp_service.verify_otp(memory.booking_id, otp)
            
            if not verification_result.get("valid", False):
                memory.otp_attempts += 1
                
                if memory.otp_attempts >= 3 or verification_result.get("should_restart"):
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
            
            logger.info(f"✅ OTP verified, saving booking...")
            
            if not self.booking_service:
                from database import booking_collection
                from services import twilio_client
                from config import TWILIO_WHATSAPP_FROM
                
                self.booking_service = BookingService(
                    booking_collection=booking_collection,
                    twilio_client=twilio_client,
                    whatsapp_from=TWILIO_WHATSAPP_FROM
                )
            
            booking_data = self.booking_service.create_booking_payload(memory)
            saved_booking_id = self.booking_service.save_booking(booking_data)
            
            verified_booking_id = verification_result.get("booking_id")
            if verified_booking_id:
                self.otp_service.delete_otp_data(verified_booking_id)
            
            if memory.intent.phone:
                self.booking_service.send_confirmation_whatsapp(
                    memory.intent.phone,
                    booking_data,
                    language
                )
            
            reply = self.prompt_templates.get_booking_confirmed_message(language, memory.intent.name)
            
            memory.reset()
            self.memory_service.update_session(memory.session_id, memory)
            
            logger.info(f"✅ Booking completed: {saved_booking_id}")
            
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
            logger.error(f"Error verifying OTP or saving booking: {e}", exc_info=True)
            
            reply = "Error saving booking. Your OTP is still valid, please try again."
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="error",
                metadata={"error": str(e)}
            )
    
    def _build_response(self, reply: str, memory: ConversationMemory, action: str, metadata: Dict = None) -> Dict[str, Any]:
        """Build response"""
        metadata = metadata or {}
        
        response_data = {
            "reply": reply,
            "session_id": memory.session_id,
            "stage": memory.stage,
            "action": action,
            "missing_fields": memory.intent.missing_fields(),
            "collected_info": memory.intent.get_summary(),
            "chat_mode": metadata.get("chat_mode", "agent"),
            "next_expected": metadata.get("next_expected"),
            "booking_id": metadata.get("booking_id"),
            "off_track_count": memory.off_track_count
        }
        
        for key, value in metadata.items():
            if key not in response_data:
                response_data[key] = value
        
        try:
            return AgentChatResponse(**response_data).dict()
        except Exception as e:
            logger.error(f"Error building response: {e}")
            return response_data
    
    def _build_error_response(self, error_message: str, session_id: str) -> Dict[str, Any]:
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