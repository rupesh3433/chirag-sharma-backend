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

            # NEW: Check for chat mode requests
            if self._is_chat_request(message):
                logger.info(f"📞 User requested chat mode: {message[:50]}")
                return await self._switch_to_chat_mode(memory, language)

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
        """Answer question using knowledge base and continue booking - IMPROVED"""
        try:
            logger.info(f"📚 Answering question during booking (off-track count: {memory.off_track_count}/{self.MAX_OFF_TRACK_ATTEMPTS})")
            
            msg_lower = message.lower()
            
            # 1. Check if we're asking for year (date completion)
            date_info = memory.intent.metadata.get('date_info', {})
            if date_info.get('needs_year', False):
                if self._is_year_response(message):
                    return await self._handle_year_response(message, memory, language)
            
            # 2. Check for chat requests
            if self._is_chat_request(msg_lower):
                logger.info(f"📞 User requested chat mode during booking")
                return await self._switch_to_chat_mode(memory, language)
            
            # 3. Check for service comparison requests
            requested_service = self._extract_requested_service(msg_lower)
            if requested_service and memory.intent.service != requested_service:
                return await self._handle_service_comparison(message, requested_service, memory, language)
            
            # 4. Handle booking-specific questions first (these are critical for flow)
            booking_specific_answer = await self._handle_booking_specific_questions(message, memory, language)
            if booking_specific_answer:
                # We have a booking-specific answer, show it with continuation
                return await self._show_answer_with_continuation(booking_specific_answer, message, memory, language)
            
            # 5. For ALL OTHER questions, use knowledge base
            # Build context about current booking state
            context = self._build_booking_context(memory)
            
            # Get answer from knowledge base
            answer = await self.knowledge_base_service.get_answer(message, language, context)
            
            # If knowledge base returns answer, use it
            if answer:
                return await self._show_answer_with_continuation(answer, message, memory, language)
            
            # 6. Fallback for when knowledge base has no answer
            # Only use generic fallback, not specific content
            fallback_answer = self._get_generic_fallback_answer(message, language)
            return await self._show_answer_with_continuation(fallback_answer, message, memory, language)
            
        except Exception as e:
            logger.error(f"Error answering question: {e}", exc_info=True)
            return await self._handle_question_error(memory, language, e)
    

    def _is_year_response(self, message: str) -> bool:
        """Check if message contains a valid year"""
        year_match = re.search(r'\b(20[2-9][0-9]|2100)\b', message)
        return bool(year_match)

    def _is_chat_request(self, message: str) -> bool:
        """Check if user wants to switch to chat mode"""
        msg_lower = message.lower().strip()
        
        chat_keywords = [
            'i want to chat', 'want to chat', 'let\'s chat', 'just chat',
            'don\'t book', 'don\'t ask me to book', 'not booking',
            'just talking', 'only chat', 'chat only', 'chat mode',
            'talk about', 'discuss', 'have a conversation', 'chat',
            'converse', 'talk', 'speak', 'have a talk', 'have discussion',
            'cancel booking and chat', 'stop booking and chat',
            'no booking just chat', 'skip booking'
        ]
        
        return any(kw in msg_lower for kw in chat_keywords)

    def is_service_switch_request(self, message: str) -> Tuple[bool, Optional[str]]:
        """Check if user wants to switch to a different service"""
        msg_lower = message.lower()
        
        # First exclude social media questions
        social_keywords =[
            'instagram', 'facebook', 'twitter', 'youtube', 'linkedin',
            'social media', 'social', 'media', 'follow', 'subscriber', 
            'subscribers', 'channel', 'profile', 'page', 'account',
            'handle', 'username', 'link', 'website', 'web', 'site',
            'online', 'internet', 'net', 'whatsapp channel', 'telegram',
            'tiktok', 'snapchat', 'pinterest'
        ]
        if any(keyword in msg_lower for keyword in social_keywords):
            return False, None
        
        switch_patterns = {
            'bridal': 'Bridal Makeup Services',
            'bride': 'Bridal Makeup Services',
            'wedding': 'Bridal Makeup Services',
            'party': 'Party Makeup Services',
            'function': 'Party Makeup Services',
            'celebration': 'Party Makeup Services',
            'engagement': 'Engagement & Pre-Wedding Makeup',
            'pre-wedding': 'Engagement & Pre-Wedding Makeup',
            'sangeet': 'Engagement & Pre-Wedding Makeup',
            'henna': 'Henna (Mehendi) Services',
            'mehendi': 'Henna (Mehendi) Services',
            'mehndi': 'Henna (Mehendi) Services'
        }
        
        for keyword, service in switch_patterns.items():
            if keyword in msg_lower:
                # Check if this is different from current
                return True, service
        
        return False, None




    def _extract_requested_service(self, message: str) -> Optional[str]:
        """Extract service name from message"""
        msg_lower = message.lower()
        
        # First check if it's about social media (not a service)
        social_keywords = [
            'instagram', 'facebook', 'twitter', 'youtube', 'linkedin',
            'social media', 'social', 'media', 'follow', 'subscriber', 
            'subscribers', 'channel', 'profile', 'page', 'account',
            'handle', 'username', 'link', 'website', 'web', 'site',
            'online', 'internet', 'net', 'whatsapp channel', 'telegram',
            'tiktok', 'snapchat', 'pinterest']
        if any(keyword in msg_lower for keyword in social_keywords):
            return None
        
        # Only then check for services
        service_keywords = {
            'bridal': 'Bridal Makeup Services',
            'party': 'Party Makeup Services', 
            'engagement': 'Engagement & Pre-Wedding Makeup',
            'pre-wedding': 'Engagement & Pre-Wedding Makeup',
            'henna': 'Henna (Mehendi) Services',
            'mehendi': 'Henna (Mehendi) Services',
            'mehndi': 'Henna (Mehendi) Services'
        }
        
        for keyword, service_name in service_keywords.items():
            if keyword in msg_lower:
                return service_name
        
        return None

    async def _handle_booking_specific_questions(
        self,
        message: str,
        memory: ConversationMemory,
        language: str
    ) -> Optional[str]:
        """Handle booking-specific questions that need special handling"""

        msg_lower = message.lower().strip()

        # --------------------------------------------------
        # 0️⃣ FIX: Address incorrectly contains date info
        # --------------------------------------------------
        if memory.intent.address:
            address_lower = memory.intent.address.lower()

            month_names = [
                "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december",
                # short forms (very important)
                "jan", "feb", "mar", "apr", "jun", "jul",
                "aug", "sep", "sept", "oct", "nov", "dec"
            ]

            has_month = any(month in address_lower for month in month_names)
            has_year = any(year in address_lower for year in ["2024", "2025", "2026", "2027", "2028"])

            # Heuristic: month + year OR number + month
            if has_month and (has_year or any(ch.isdigit() for ch in address_lower)):
                memory.intent.address = None
                logger.warning(
                    "Cleared address field because it contained date-like information"
                )

        # --------------------------------------------------
        # 1️⃣ HARD EXCLUSION: Social / Online presence queries
        # --------------------------------------------------
        social_media_keywords = [
            "instagram", "facebook", "twitter", "x", "youtube", "linkedin",
            "social media", "social", "media", "follow", "followers",
            "subscriber", "subscribers", "channel", "profile", "page",
            "account", "handle", "username", "link", "website", "web",
            "site", "online", "internet", "net", "whatsapp channel",
            "telegram", "tiktok", "snapchat", "pinterest"
        ]

        if any(k in msg_lower for k in social_media_keywords):
            return None

        # --------------------------------------------------
        # 2️⃣ PRICE / PACKAGE / ARTIST QUESTIONS
        # --------------------------------------------------
        price_keywords = [
            "price", "cost", "charges", "fee", "rate",
            "how much", "pricing", "budget"
        ]

        package_keywords = [
            "package", "packages", "plan", "plans",
            "lowest", "cheapest", "minimum", "basic",
            "premium", "luxury", "highest", "expensive"
        ]

        artist_keywords = [
            "senior", "junior", "artist", "makeup artist",
            "reception", "engagement", "cocktail"
        ]

        if any(k in msg_lower for k in price_keywords + package_keywords + artist_keywords):

            if "reception" in msg_lower:
                return self.prompt_templates.get_service_price_info(
                    "Reception",
                    language
                )

            if "senior" in msg_lower:
                return self.prompt_templates.get_service_price_info(
                    "Senior Artist",
                    language
                )

            if "cheapest" in msg_lower or "lowest" in msg_lower:
                return self.prompt_templates.get_lowest_price_package(language)

            if "premium" in msg_lower or "luxury" in msg_lower:
                return self.prompt_templates.get_premium_package(language)

            if memory.intent.service:
                return self.prompt_templates.get_service_price_info(
                    memory.intent.service,
                    language
                )

            return self.prompt_templates.get_service_details(language)

        # --------------------------------------------------
        # 3️⃣ LIST / OFFERING QUESTIONS
        # --------------------------------------------------
        list_keywords = [
            "list", "services", "what do you offer",
            "what services", "what are your services",
            "show services", "available services",
            "explain services", "service details"
        ]

        if any(k in msg_lower for k in list_keywords):
            return self.prompt_templates.get_service_details(language)

        # --------------------------------------------------
        # 4️⃣ SERVICE COMPARISON FLOW
        # --------------------------------------------------
        comparison_state = memory.intent.metadata.get(
            "service_comparison", {}
        )

        if comparison_state.get("waiting_for_response", False):
            return await self._handle_service_switch_response(
                message,
                memory,
                language
            )

        # --------------------------------------------------
        # 5️⃣ NOT HANDLED HERE → fallback
        # --------------------------------------------------
        return None


    async def _handle_service_comparison(self, message: str, requested_service: str, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle when user asks about different service"""
        logger.info(f"🔍 User asking about different service: {requested_service}")
        
        # Answer the question about that service
        context = f"User is currently selecting package for {memory.intent.service}. They are asking about {requested_service}."
        answer = await self.knowledge_base_service.get_answer(message, language, context)
        
        if not answer:
            # Fallback answer
            answer = f"For detailed information about {requested_service}, you can select it from our services list."
        
        # Show comparison: Current service vs Asked service
        if memory.intent.service:
            current_service_info = self.prompt_templates.get_service_price_info(memory.intent.service, language)
            asked_service_info = self.prompt_templates.get_service_price_info(requested_service, language)
            
            reply = f"{answer}\n\n🎯 **Comparison:**\n\n"
            reply += f"**Current Selection:** {memory.intent.service}\n{current_service_info}\n\n"
            reply += f"**{requested_service}:**\n{asked_service_info}\n\n"
            
            # Ask if they want to switch services
            if language == "hi":
                reply += "क्या आप इस सेवा को चुनना चाहेंगे? (हां/नहीं)"
            elif language == "ne":
                reply += "के तपाईं यो सेवा छनोट गर्न चाहनुहुन्छ? (हो/होइन)"
            elif language == "mr":
                reply += "तुम्हाला ही सेवा निवडायची आहे का? (हो/नाही)"
            else:
                reply += "Would you like to select this service instead? (yes/no)"
            
            # Set a flag to handle service switching
            memory.intent.metadata['service_comparison'] = {
                'requested_service': requested_service,
                'waiting_for_response': True
            }
            
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            return self._build_response(
                reply=reply,
                memory=memory,
                action="service_comparison",
                metadata={
                    "current_service": memory.intent.service,
                    "requested_service": requested_service,
                    "off_track_count": memory.off_track_count
                }
            )

    async def _handle_service_switch_response(self, message: str, memory: ConversationMemory, language: str) -> Optional[str]:
        """Handle user's response to service switch question"""
        msg_lower = message.lower()
        
        if 'yes' in msg_lower or 'हां' in msg_lower or 'हो' in msg_lower:
            # User wants to switch services
            requested_service = memory.intent.metadata['service_comparison']['requested_service']
            previous_service = memory.intent.service
            memory.intent.service = requested_service
            memory.intent.package = None  # Reset package selection
            memory.intent.metadata.pop('service_comparison', None)
            
            logger.info(f"🔄 User switched service from {previous_service} to {requested_service}")
            
            # Move to package selection for new service
            memory.stage = BookingState.SELECTING_PACKAGE.value
            
            reply = f"✅ **Switched to {requested_service}**\n\n"
            reply += self.fsm._get_package_prompt(requested_service, language)
            
            memory.add_message("assistant", reply)
            self.memory_service.update_session(memory.session_id, memory)
            
            # This returns None because we're handling it directly
            return None
        
        elif 'no' in msg_lower or 'नहीं' in msg_lower or 'होइन' in msg_lower:
            # User doesn't want to switch, clear comparison flag
            memory.intent.metadata.pop('service_comparison', None)
            return "Okay, let's continue with your current selection."
        
        return None

    async def _show_answer_with_continuation(self, answer: str, original_question: str, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Show answer and appropriate booking continuation"""
        # Get current state and missing fields
        state_enum = BookingState.from_string(memory.stage)
        missing = memory.intent.missing_fields()
        
        # Get appropriate continuation based on state
        continuation = ""
        
        if state_enum == BookingState.CONFIRMING:
            summary = memory.intent.get_summary()
            continuation = self.prompt_templates.get_confirmation_prompt(summary, language)
        
        elif state_enum == BookingState.COLLECTING_DETAILS and missing:
            continuation = self.fsm._get_collected_summary_prompt(memory.intent, missing, language)
        
        elif state_enum == BookingState.SELECTING_PACKAGE and memory.intent.service:
            continuation = self.fsm._get_package_prompt(memory.intent.service, language)
        
        else:
            try:
                continuation = self._get_booking_continuation(state_enum, memory, language)
            except AttributeError as e:
                logger.error(f"Error getting booking continuation: {e}")
                continuation = "How can I help you with your booking?"
        
        # Format final reply
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
                "question": original_question,
                "answer": answer,
                "off_track_count": memory.off_track_count,
                "max_attempts": self.MAX_OFF_TRACK_ATTEMPTS
            }
        )

    def _get_generic_fallback_answer(self, message: str, language: str) -> str:
        """Get generic fallback answer when knowledge base has no answer"""
        # VERY generic fallback - no specific content
        if language == "hi":
            return "मैं आपकी जानकारी के लिए यहां हूं। आपकी बुकिंग जारी रखें।"
        elif language == "ne":
            return "म तपाईंको जानकारीको लागि यहाँ छु। तपाईंको बुकिङ जारी राख्नुहोस्।"
        elif language == "mr":
            return "मी तुमच्या माहितीसाठी इथे आहे. तुमची बुकिंग सुरू ठेवा."
        else:
            return "I'm here for your information. Please continue with your booking."

    async def _handle_question_error(self, memory: ConversationMemory, language: str, error: Exception) -> Dict[str, Any]:
        """Handle errors in question answering"""
        logger.error(f"Question answering error: {error}")
        
        # Fallback: just continue with booking
        state_enum = BookingState.from_string(memory.stage)
        try:
            continuation = self._get_booking_continuation(state_enum, memory, language)
        except AttributeError:
            if language == "hi":
                continuation = "बुकिंग जारी रखें।"
            elif language == "ne":
                continuation = "बुकिङ जारी राख्नुहोस्।"
            else:
                continuation = "Continue with booking."
        
        reply = f"I understand. {continuation}"
        memory.add_message("assistant", reply)
        self.memory_service.update_session(memory.session_id, memory)
        
        return self._build_response(
            reply=reply,
            memory=memory,
            action="continue",
            metadata={"error": str(error)}
        )


    async def _handle_year_response(self, message: str, memory: ConversationMemory, language: str) -> Dict[str, Any]:
        """Handle year response for partial dates"""
        year_match = re.search(r'\b(20[2-9][0-9]|2100)\b', message)
        
        if year_match:
            year = int(year_match.group(1))
            # Update date with year
            date_info = memory.intent.metadata.get('date_info', {})
            
            if date_info.get('needs_year', False) and memory.intent.date:
                try:
                    from datetime import datetime
                    old_date = datetime.strptime(memory.intent.date, '%Y-%m-%d')
                    new_date = old_date.replace(year=year)
                    memory.intent.date = new_date.strftime('%Y-%m-%d')
                    
                    # Update metadata
                    memory.intent.metadata['date_info']['needs_year'] = False
                    memory.intent.metadata['date_info']['user_provided_year'] = year
                    
                    # Show updated summary
                    missing = memory.intent.missing_fields()
                    continuation = self.fsm._get_collected_summary_prompt(memory.intent, missing, language)
                    
                    reply = f"✅ Updated year to {year}. {continuation}"
                    memory.add_message("assistant", reply)
                    self.memory_service.update_session(memory.session_id, memory)
                    
                    return self._build_response(
                        reply=reply,
                        memory=memory,
                        action="year_provided",
                        metadata={"year": year}
                    )
                except Exception as e:
                    logger.error(f"Error updating year: {e}")
        
        # If no valid year, ask again
        date_original = memory.intent.metadata.get('date_info', {}).get('original', 'the date')
        
        if language == "hi":
            reply = f"📅 **आपने तारीख दी: '{date_original}' लेकिन साल नहीं दिया। कृपया साल दें (जैसे 2025, 2026):**"
        elif language == "ne":
            reply = f"📅 **तपाईंले मिति दिनुभयो: '{date_original}' तर वर्ष दिनुभएन। कृपया वर्ष दिनुहोस् (जस्तै 2025, 2026):**"
        elif language == "mr":
            reply = f"📅 **तुम्ही तारीख दिली: '{date_original}' पण वर्ष दिले नाही. कृपया वर्ष द्या (उदा. 2025, 2026):**"
        else:
            reply = f"📅 **You provided date: '{date_original}' but not the year. Please provide the year (e.g., 2025, 2026):**"
        
        memory.add_message("assistant", reply)
        self.memory_service.update_session(memory.session_id, memory)
        
        return self._build_response(
            reply=reply,
            memory=memory,
            action="ask_year",
            metadata={"error": "Invalid year provided"}
        )






    def _get_booking_continuation(self, state_enum: BookingState, memory: ConversationMemory, language: str) -> str:
        """Get the next step to continue booking - FIXED"""
        
        if state_enum == BookingState.GREETING:
            return self.prompt_templates.get_service_list(language)
        
        elif state_enum == BookingState.SELECTING_SERVICE:
            return self.prompt_templates.get_service_list(language)

        elif state_enum == BookingState.INFO_MODE:
            # In info mode, just acknowledge we're in chat mode
            if language == "hi":
                return "मैं सूचना मोड में हूं। आप मुझसे कुछ भी पूछ सकते हैं।"
            elif language == "ne":
                return "म जानकारी मोडमा छु। तपाईं मसँग केहि पनि सोध्न सक्नुहुन्छ।"
            else:
                return "I'm in information mode. You can ask me anything."
        
        elif state_enum == BookingState.SELECTING_PACKAGE:
            if memory.intent.service:
                # FIX: Show packages for the CURRENT service, not what was just discussed
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
        
        # Create new session if not found
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
        """Switch to chat mode - FIXED to properly set stage to INFO_MODE"""
        memory.reset()
        memory.stage = BookingState.INFO_MODE.value  # Use INFO_MODE instead of "chat_mode"
        self.memory_service.update_session(memory.session_id, memory)
        
        if language == "hi":
            reply = "मैंने सूचना मोड में स्विच कर दिया है। आप स्वतंत्र रूप से पूछ सकते हैं, और जब बुकिंग करने के लिए तैयार हों, तो मुझे बताएं!"
        elif language == "ne":
            reply = "मैले जानकारी मोडमा स्विच गरेको छु। तपाईं स्वतन्त्र रूपमा सोध्न सक्नुहुन्छ, र जब बुकिङ गर्न तयार हुनुहुन्छ, मलाई भन्नुहोस्!"
        else:
            reply = "I've switched to information mode. Feel free to ask any questions, and when you're ready to book, let me know!"
        
        memory.add_message("assistant", reply)
        self.memory_service.update_session(memory.session_id, memory)
        
        return self._build_response(
            reply=reply, 
            memory=memory, 
            action="switched_to_info", 
            metadata={"chat_mode": "normal"}
        )
    
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
        """Build response - FIXED chat_mode determination based on stage"""
        metadata = metadata or {}
        
        # Determine chat_mode based on stage
        state_enum = BookingState.from_string(memory.stage)
        if state_enum in [BookingState.GREETING, BookingState.INFO_MODE]:
            chat_mode = "normal"
        else:
            chat_mode = "agent"
        
        # Override with metadata if explicitly provided
        if "chat_mode" in metadata:
            chat_mode = metadata["chat_mode"]
        
        response_data = {
            "reply": reply,
            "session_id": memory.session_id,
            "stage": memory.stage,
            "action": action,
            "missing_fields": memory.intent.missing_fields(),
            "collected_info": memory.intent.get_summary(),
            "chat_mode": chat_mode,  # Use the determined value
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