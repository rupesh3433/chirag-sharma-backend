# agent/engine/fsm.py
"""
Enhanced FSM with Smart Question Handling
"""

import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

from ..models.memory import ConversationMemory
from ..models.intent import BookingIntent
from ..models.state import BookingState
from .state_manager import StateManager
from ..utils.extractors import FieldExtractor, extract_fields_smart
from ..utils.question_detector import QuestionDetector
from ..utils.knowledge_base import KnowledgeBaseService
from ..config.config import (
    SERVICES, 
    AGENT_SETTINGS,
    validate_language
)
from ..prompts.templates import (
    build_service_selection_message,
    build_package_selection_message,
    build_details_collection_message,
    build_confirmation_message,
    get_greeting_message,
    get_otp_message,
    get_booking_success_message,
    build_missing_fields_message
)

logger = logging.getLogger(__name__)


class BookingFSM:
    """Finite State Machine with intelligent question handling"""
    
    def __init__(self, session_id: str, language: str = "en"):
        """Initialize FSM"""
        self.memory = ConversationMemory(session_id=session_id, language=language)
        self.state_manager = StateManager()
        self.current_state = BookingState.GREETING
        self.intent = self.memory.intent
        self.services = list(SERVICES.keys())
        
        # Initialize services
        self.question_detector = QuestionDetector()
        self.field_extractor = FieldExtractor(self.question_detector)
        self.knowledge_base = KnowledgeBaseService()
        
        # Settings
        self.max_off_topic = AGENT_SETTINGS.get("max_off_topic_attempts", 5)
        self.off_topic_count = 0
        
        logger.info(f"🚀 FSM initialized for session {session_id}")
    
    async def process_message(self, user_message: str) -> Dict[str, Any]:
        """Process user message with smart question handling"""
        self.memory.add_message("user", user_message)
        language = self.memory.language
        state_value = self.current_state.value
        
        logger.info(f"🎯 Processing in state {state_value}: {user_message[:50]}")
        
        # Step 1: Check for social media questions
        is_social, platform = self.question_detector.is_social_media_question(user_message)
        if is_social:
            logger.info(f"📱 Handling social media question: {platform}")
            return await self._handle_social_media_question(user_message, platform, language)
        
        # Step 2: Check if it's off-topic
        is_off_topic = self.question_detector.is_off_topic(user_message, state_value)
        if is_off_topic:
            logger.info(f"🔍 Off-topic query detected")
            return await self._handle_off_topic_question(user_message, language)
        
        # Step 3: Check if it's a booking-related question
        is_booking_question = self.question_detector.is_booking_related_question(user_message)
        if is_booking_question:
            logger.info(f"❓ Booking-related question detected")
            return await self._handle_booking_question(user_message, language)
        
        # Step 4: Process based on current state
        return await self._process_by_state(user_message, language)
    
    async def _process_by_state(self, message: str, language: str) -> Dict[str, Any]:
        """Process message based on current state"""
        handlers = {
            BookingState.GREETING: self._handle_greeting_state,
            BookingState.SELECTING_SERVICE: self._handle_service_selection,
            BookingState.SELECTING_PACKAGE: self._handle_package_selection,
            BookingState.COLLECTING_DETAILS: self._handle_details_collection,
            BookingState.CONFIRMING: self._handle_confirmation,
            BookingState.OTP_SENT: self._handle_otp_verification
        }
        
        handler = handlers.get(self.current_state)
        if handler:
            return await handler(message, language)
        
        # Default fallback
        return await self._handle_unknown_state(message, language)
    
    async def _handle_greeting_state(self, message: str, language: str) -> Dict[str, Any]:
        """Handle greeting state"""
        msg_lower = message.lower()
        
        # Check for booking intent
        if any(word in msg_lower for word in ['book', 'booking', 'reserve', 'appointment']):
            self.memory.last_shown_list = "services"
            response = build_service_selection_message(language)
            self.current_state = BookingState.SELECTING_SERVICE
            
            return {
                "response": response,
                "next_state": self.current_state.value,
                "action": "ask_service",
                "understood": True
            }
        
        # Default greeting
        response = get_greeting_message(language)
        return {
            "response": response,
            "next_state": self.current_state.value,
            "action": "greeting",
            "understood": True
        }
    
    async def _handle_service_selection(self, message: str, language: str) -> Dict[str, Any]:
        """Handle service selection"""
        msg_lower = message.lower()
        
        # Check numeric selection
        num_match = re.search(r'\b([1-4])\b', message)
        if num_match:
            idx = int(num_match.group(1)) - 1
            if 0 <= idx < len(self.services):
                service = self.services[idx]
                self.intent.service = service
                self.memory.last_shown_list = "packages"
                self.current_state = BookingState.SELECTING_PACKAGE
                
                logger.info(f"✅ Service selected: {service}")
                return {
                    "response": build_package_selection_message(service, language),
                    "next_state": self.current_state.value,
                    "action": "service_selected",
                    "understood": True
                }
        
        # Check service keywords
        for service_name, service_data in SERVICES.items():
            keywords = service_data.get("keywords", [])
            if any(keyword in msg_lower for keyword in keywords):
                self.intent.service = service_name
                self.memory.last_shown_list = "packages"
                self.current_state = BookingState.SELECTING_PACKAGE
                
                logger.info(f"✅ Service selected via keyword: {service_name}")
                return {
                    "response": build_package_selection_message(service_name, language),
                    "next_state": self.current_state.value,
                    "action": "service_selected",
                    "understood": True
                }
        
        # Not understood
        return {
            "response": build_service_selection_message(language),
            "next_state": self.current_state.value,
            "action": "retry_service",
            "understood": False
        }
    
    async def _handle_package_selection(self, message: str, language: str) -> Dict[str, Any]:
        """Handle package selection"""
        if not self.intent.service:
            logger.error("No service selected")
            return {
                "response": build_service_selection_message(language),
                "next_state": BookingState.SELECTING_SERVICE.value,
                "action": "ask_service",
                "understood": True
            }
        
        msg_lower = message.lower()
        service_data = SERVICES.get(self.intent.service, {})
        packages = list(service_data.get("packages", {}).keys())
        
        # Check numeric selection
        num_match = re.search(r'\b([1-3])\b', message)
        if num_match:
            idx = int(num_match.group(1)) - 1
            if 0 <= idx < len(packages):
                package = packages[idx]
                self.intent.package = package
                self.current_state = BookingState.COLLECTING_DETAILS
                
                logger.info(f"✅ Package selected: {package}")
                return {
                    "response": build_details_collection_message(language),
                    "next_state": self.current_state.value,
                    "action": "package_selected",
                    "understood": True
                }
        
        # Check package keywords
        package_keywords = {
            "chirag": "Chirag Sharma",
            "senior": "Senior Artist",
            "signature": "Signature",
            "luxury": "Luxury",
            "basic": "Basic"
        }
        
        for keyword, package_prefix in package_keywords.items():
            if keyword in msg_lower:
                for package in packages:
                    if package_prefix in package:
                        self.intent.package = package
                        self.current_state = BookingState.COLLECTING_DETAILS
                        
                        logger.info(f"✅ Package selected via keyword: {package}")
                        return {
                            "response": build_details_collection_message(language),
                            "next_state": self.current_state.value,
                            "action": "package_selected",
                            "understood": True
                        }
        
        # Not understood
        return {
            "response": build_package_selection_message(self.intent.service, language),
            "next_state": self.current_state.value,
            "action": "retry_package",
            "understood": False
        }

    # agent/engine/fsm.py (UPDATE _handle_details_collection METHOD)

    async def _handle_details_collection(self, message: str, language: str) -> Dict[str, Any]:
        """Handle details collection - IMPROVED with 'already provided' handling"""
        msg_lower = message.lower()
        
        # Check if user says they already provided information
        already_provided_keywords = ['already', 'gave', 'provided', 'i gave', 'i provided', 'i already']
        if any(keyword in msg_lower for keyword in already_provided_keywords):
            logger.info(f"👤 User says they already provided info: {message}")
            
            # Try to extract any remaining fields from this message
            extracted = extract_fields_smart(message, self.question_detector)
            if extracted:
                self._update_intent_with_fields(extracted)
                logger.info(f"✅ Extracted additional fields: {extracted}")
            
            # Check what's still missing
            missing = self.intent.missing_fields()
            collected = self._get_collected_fields()
            
            if not missing:
                # All details collected
                self.current_state = BookingState.CONFIRMING
                return {
                    "response": build_confirmation_message(self._get_summary(), language),
                    "next_state": self.current_state.value,
                    "action": "ask_confirmation",
                    "understood": True
                }
            else:
                # Build a more helpful response
                response = self._build_already_provided_response(missing, collected, language)
                return {
                    "response": response,
                    "next_state": self.current_state.value,
                    "action": "clarify_missing",
                    "understood": True
                }
        
        # Check for completion
        if any(word in msg_lower for word in ['done', 'complete', 'finished', 'ready', 'proceed']):
            missing = self.intent.missing_fields()
            if not missing:
                # All details collected
                self.current_state = BookingState.CONFIRMING
                return {
                    "response": build_confirmation_message(self._get_summary(), language),
                    "next_state": self.current_state.value,
                    "action": "ask_confirmation",
                    "understood": True
                }
            else:
                response = self._build_details_prompt(missing, self._get_collected_fields(), language)
                return {
                    "response": response,
                    "next_state": self.current_state.value,
                    "action": "ask_missing_fields",
                    "understood": True
                }
        
        # Extract fields
        extracted = extract_fields_smart(message, self.question_detector)
        logger.info(f"🔍 Extracted fields: {extracted}")
        
        if extracted:
            self._update_intent_with_fields(extracted)
            
            # Check if all fields collected
            missing = self.intent.missing_fields()
            if not missing:
                self.current_state = BookingState.CONFIRMING
                return {
                    "response": build_confirmation_message(self._get_summary(), language),
                    "next_state": self.current_state.value,
                    "action": "ask_confirmation",
                    "understood": True
                }
            else:
                response = self._build_details_prompt(missing, self._get_collected_fields(), language)
                return {
                    "response": response,
                    "next_state": self.current_state.value,
                    "action": "ask_missing_fields",
                    "understood": True
                }
        
        # Not understood
        missing = self.intent.missing_fields()
        response = self._build_details_prompt(missing, self._get_collected_fields(), language)
        
        return {
            "response": response,
            "next_state": self.current_state.value,
            "action": "ask_details",
            "understood": False
        }

    def _build_already_provided_response(self, missing_fields: List[str], collected_fields: Dict[str, str], language: str) -> str:
        """Build response when user says they already provided info"""
        if language == "hi":
            response = "मैं आपकी जानकारी समझ गया।\n\n"
            
            if collected_fields:
                response += "**आपकी जानकारी:**\n"
                for field, value in collected_fields.items():
                    field_names = {
                        "service": "सेवा",
                        "package": "पैकेज",
                        "name": "नाम",
                        "phone": "फोन",
                        "email": "ईमेल",
                        "date": "तारीख",
                        "address": "पता",
                        "pincode": "पिन कोड",
                        "service_country": "देश"
                    }
                    display_name = field_names.get(field, field)
                    response += f"✅ **{display_name}:** {value}\n"
            
            if missing_fields:
                response += "\n**कृपया फिर से दें:**\n"
                missing_display = []
                for field in missing_fields:
                    field_names = {
                        "name": "पूरा नाम",
                        "phone": "व्हाट्सएप नंबर",
                        "email": "ईमेल",
                        "date": "तारीख (जैसे 25 नवंबर 2026)",
                        "address": "पूरा पता (जैसे पुणे, महाराष्ट्र)",
                        "pincode": "पिन कोड",
                        "service_country": "देश (भारत/नेपाल/दुबई)"
                    }
                    missing_display.append(field_names.get(field, field))
                
                for field in missing_display:
                    response += f"• {field}\n"
            
            response += "\n**उदाहरण:** \"25 नवंबर 2026, पुणे, महाराष्ट्र, भारत\""
            
        else:  # English
            response = "I understand you've provided some information.\n\n"
            
            if collected_fields:
                response += "**Your Information:**\n"
                for field, value in collected_fields.items():
                    field_names = {
                        "service": "Service",
                        "package": "Package",
                        "name": "Name",
                        "phone": "Phone",
                        "email": "Email",
                        "date": "Date",
                        "address": "Address",
                        "pincode": "PIN Code",
                        "service_country": "Country"
                    }
                    display_name = field_names.get(field, field)
                    response += f"✅ **{display_name}:** {value}\n"
            
            if missing_fields:
                response += "\n**Please provide again:**\n"
                missing_display = []
                for field in missing_fields:
                    field_names = {
                        "name": "Full Name",
                        "phone": "WhatsApp Number",
                        "email": "Email Address",
                        "date": "Event Date (e.g., 25 November 2026)",
                        "address": "Full Address (e.g., Pune, Maharashtra)",
                        "pincode": "PIN Code",
                        "service_country": "Country (India/Nepal/Dubai)"
                    }
                    missing_display.append(field_names.get(field, field))
                
                for field in missing_display:
                    response += f"• {field}\n"
            
            response += "\n**Example:** \"25 November 2026, Pune, Maharashtra, India\""
        
        return response


    def _build_details_prompt(self, missing_fields: List[str], collected_fields: Dict[str, str], language: str) -> str:
        """Build details collection prompt"""
        if language == "hi":
            prompt = "📋 **आपकी जानकारी:**\n\n"
            
            # Show collected fields
            for field, value in collected_fields.items():
                field_names = {
                    "service": "सेवा",
                    "package": "पैकेज",
                    "name": "नाम",
                    "phone": "फोन",
                    "email": "ईमेल",
                    "date": "तारीख",
                    "address": "पता",
                    "pincode": "पिन कोड",
                    "service_country": "देश"
                }
                display_name = field_names.get(field, field)
                prompt += f"✅ **{display_name}:** {value}\n"
            
            if missing_fields:
                prompt += "\n📝 **कृपया दें:**\n"
                missing_display = []
                for field in missing_fields:
                    field_names = {
                        "name": "पूरा नाम",
                        "phone": "व्हाट्सएप नंबर",
                        "email": "ईमेल पता",
                        "date": "इवेंट तारीख (जैसे 25 नवंबर 2026)",
                        "address": "इवेंट स्थान (जैसे पुणे, महाराष्ट्र)",
                        "pincode": "पिन कोड",
                        "service_country": "देश (भारत/नेपाल/दुबई)"
                    }
                    missing_display.append(field_names.get(field, field))
                
                for field in missing_display:
                    prompt += f"• {field}\n"
                
                # Add format hints
                if "date" in missing_fields:
                    prompt += "\n💡 **तारीख फॉर्मेट:** 25 नवंबर 2026, 15 मार्च 2025, 2026-11-25"
                if "address" in missing_fields:
                    prompt += "\n💡 **पता फॉर्मेट:** शहर, राज्य (जैसे पुणे, महाराष्ट्र)"
                if "service_country" in missing_fields:
                    prompt += "\n💡 **देश:** भारत, नेपाल, दुबई"
            
            return prompt
        
        else:  # English
            prompt = "📋 **Your Information:**\n\n"
            
            # Show collected fields
            for field, value in collected_fields.items():
                field_names = {
                    "service": "Service",
                    "package": "Package",
                    "name": "Name",
                    "phone": "Phone",
                    "email": "Email",
                    "date": "Date",
                    "address": "Address",
                    "pincode": "PIN Code",
                    "service_country": "Country"
                }
                display_name = field_names.get(field, field)
                prompt += f"✅ **{display_name}:** {value}\n"
            
            if missing_fields:
                prompt += "\n📝 **Please provide:**\n"
                missing_display = []
                for field in missing_fields:
                    field_names = {
                        "name": "Full Name",
                        "phone": "WhatsApp Number",
                        "email": "Email Address",
                        "date": "Event Date (e.g., 25 November 2026)",
                        "address": "Event Location (e.g., Pune, Maharashtra)",
                        "pincode": "PIN Code",
                        "service_country": "Country (India/Nepal/Dubai)"
                    }
                    missing_display.append(field_names.get(field, field))
                
                for field in missing_display:
                    prompt += f"• {field}\n"
                
                # Add format hints
                if "date" in missing_fields:
                    prompt += "\n💡 **Date format:** 25 November 2026, 15 March 2025, 2026-11-25"
                if "address" in missing_fields:
                    prompt += "\n💡 **Address format:** City, State (e.g., Pune, Maharashtra)"
                if "service_country" in missing_fields:
                    prompt += "\n💡 **Country:** India, Nepal, Dubai"
            
            return prompt

    
    # In agent/engine/fsm.py, update the _handle_confirmation method:

    async def _handle_confirmation(self, message: str, language: str) -> Dict[str, Any]:
        """Handle confirmation"""
        msg_lower = message.lower()
        
        if any(word in msg_lower for word in ['yes', 'confirm', 'correct', 'proceed', 'ok', 'okay', 'yep']):
            self.current_state = BookingState.OTP_SENT
            return {
                "response": self._get_otp_prompt(language),
                "next_state": self.current_state.value,
                "action": "send_otp",
                "understood": True
            }
        elif any(word in msg_lower for word in ['no', 'change', 'edit', 'wrong', 'incorrect']):
            self.current_state = BookingState.COLLECTING_DETAILS
            return {
                "response": "What would you like to change? Please provide the corrected information.",
                "next_state": self.current_state.value,
                "action": "edit_details",
                "understood": True
            }
        
        # Not understood
        return {
            "response": build_confirmation_message(self._get_summary(), language),
            "next_state": self.current_state.value,
            "action": "retry_confirmation",
            "understood": False
        }
    
    # agent/engine/fsm.py (UPDATE THE _handle_otp_verification METHOD)

    async def _handle_otp_verification(self, message: str, language: str) -> Dict[str, Any]:
        """Handle OTP verification - IMPROVED"""
        msg_lower = message.lower()
        
        # Check for resend/didn't get requests
        resend_keywords = ['resend', 'send again', 'didnt get', 'not received', 
                        'i did not get', 'did not get', 'havent got', 'havent received',
                        'no otp', 'not get', 'missed']
        
        if any(keyword in msg_lower for keyword in resend_keywords):
            logger.info(f"🔄 OTP resend requested: {message}")
            return {
                "response": self._get_otp_resend_message(language),
                "next_state": self.current_state.value,
                "action": "resend_otp",
                "understood": True
            }
        
        # Check for OTP
        otp_match = re.search(r'\b(\d{6})\b', message)
        if otp_match:
            otp = otp_match.group(1)
            logger.info(f"✅ OTP entered: {otp}")
            self.current_state = BookingState.COMPLETED
            return {
                "response": get_booking_success_message(language, self.intent.name or "Customer"),
                "next_state": self.current_state.value,
                "action": "booking_confirmed",
                "otp": otp,
                "understood": True
            }
        
        # Check for "ok", "yes", etc. during OTP
        if any(word in msg_lower for word in ['ok', 'okay', 'yes', 'alright', 'fine']):
            return {
                "response": self._get_otp_prompt(language),
                "next_state": self.current_state.value,
                "action": "remind_otp",
                "understood": True
            }
        
        # Not understood - show OTP prompt again
        logger.warning(f"⚠️ Unrecognized OTP response: {message}")
        return {
            "response": self._get_otp_prompt(language),
            "next_state": self.current_state.value,
            "action": "ask_otp",
            "understood": False
        }

    def _get_otp_prompt(self, language: str) -> str:
        """Get OTP prompt message"""
        if language == "hi":
            return f"🔢 **कृपया 6-अंकीय OTP दर्ज करें:**\n\nOTP {self.intent.phone or 'आपके फोन'} पर भेजा गया है।"
        else:
            return f"🔢 **Please enter the 6-digit OTP:**\n\nOTP has been sent to {self.intent.phone or 'your phone'}."

    def _get_otp_resend_message(self, language: str) -> str:
        """Get OTP resend message"""
        if language == "hi":
            return f"🔄 **OTP फिर से भेजा गया है।**\n\nकृपया {self.intent.phone or 'आपके फोन'} पर नया OTP चेक करें।"
        else:
            return f"🔄 **OTP has been resent.**\n\nPlease check for a new OTP on {self.intent.phone or 'your phone'}."
    
    async def _handle_social_media_question(self, message: str, platform: str, language: str) -> Dict[str, Any]:
        """Handle social media questions"""
        answer = self.question_detector.get_social_media_response(platform, language)
        
        # Add reminder based on current state
        reminder = self._get_state_reminder(language)
        response = f"{answer}\n\n{reminder}"
        
        # Update memory
        self.memory.add_message("assistant", response)
        
        # Increment off-topic count
        self.off_topic_count += 1
        
        # Check for permanent chat mode
        if self.off_topic_count >= self.max_off_topic:
            return self._activate_permanent_chat_mode(language)
        
        return {
            "response": response,
            "next_state": self.current_state.value,
            "action": "answer_social_media",
            "off_topic": True,
            "off_topic_count": self.off_topic_count
        }
    
    async def _handle_off_topic_question(self, message: str, language: str) -> Dict[str, Any]:
        """Handle general off-topic questions"""
        # Get answer from knowledge base
        booking_info = self._get_booking_info()
        kb_response = await self.knowledge_base.answer_query(
            message, language, self.current_state.value, booking_info
        )
        
        # Add reminder
        reminder = self._get_state_reminder(language)
        response = f"{kb_response.get('response', '')}\n\n{reminder}"
        
        # Update memory
        self.memory.add_message("assistant", response)
        
        # Increment off-topic count
        self.off_topic_count += 1
        
        # Check for permanent chat mode
        if self.off_topic_count >= self.max_off_topic:
            return self._activate_permanent_chat_mode(language)
        
        return {
            "response": response,
            "next_state": self.current_state.value,
            "action": "answer_question",
            "off_topic": True,
            "off_topic_count": self.off_topic_count
        }
    
    async def _handle_booking_question(self, message: str, language: str) -> Dict[str, Any]:
        """Handle booking-related questions (NOT off-topic)"""
        # Use knowledge base for booking-related questions
        booking_info = self._get_booking_info()
        kb_response = await self.knowledge_base.answer_query(
            message, language, self.current_state.value, booking_info
        )
        
        # Add continuation reminder
        reminder = self._get_state_reminder(language)
        response = f"{kb_response.get('response', '')}\n\n{reminder}"
        
        # Update memory
        self.memory.add_message("assistant", response)
        
        # Reset off-topic count since this is booking-related
        self.off_topic_count = 0
        
        return {
            "response": response,
            "next_state": self.current_state.value,
            "action": "answer_booking_question",
            "off_topic": False,
            "booking_related": True
        }
    
    async def _handle_unknown_state(self, message: str, language: str) -> Dict[str, Any]:
        """Handle unknown state"""
        logger.warning(f"Unknown state: {self.current_state}")
        return {
            "response": get_greeting_message(language),
            "next_state": BookingState.GREETING.value,
            "action": "reset",
            "understood": True
        }
    
    def _get_state_reminder(self, language: str) -> str:
        """Get appropriate reminder for current state"""
        if language == "hi":
            if self.current_state == BookingState.SELECTING_SERVICE:
                return "अब कृपया एक सेवा चुनें।"
            elif self.current_state == BookingState.SELECTING_PACKAGE:
                return f"अब {self.intent.service} के लिए एक पैकेज चुनें।"
            elif self.current_state == BookingState.COLLECTING_DETAILS:
                return "अब अपनी जानकारी दें।"
            elif self.current_state == BookingState.CONFIRMING:
                return "अब 'हां' या 'नहीं' में उत्तर दें।"
            else:
                return "अपनी बुकिंग जारी रखें।"
        else:
            if self.current_state == BookingState.SELECTING_SERVICE:
                return "Now please select a service."
            elif self.current_state == BookingState.SELECTING_PACKAGE:
                return f"Now please select a package for {self.intent.service}."
            elif self.current_state == BookingState.COLLECTING_DETAILS:
                return "Now please provide your details."
            elif self.current_state == BookingState.CONFIRMING:
                return "Now please reply 'yes' or 'no'."
            else:
                return "Continue with your booking."
    
    def _activate_permanent_chat_mode(self, language: str) -> Dict[str, Any]:
        """Activate permanent chat mode"""
        if language == "hi":
            response = "मैंने चैट मोड में स्विच कर दिया है। आप कुछ भी पूछ सकते हैं!"
        else:
            response = "I've switched to chat mode. You can ask me anything!"
        
        self.memory.add_message("assistant", response)
        
        return {
            "response": response,
            "next_state": "CHAT_MODE",
            "action": "activate_chat_mode",
            "permanent_chat": True
        }
    
    def _update_intent_with_fields(self, fields: Dict[str, str]):
        """Update intent with extracted fields"""
        for field, value in fields.items():
            if value and value.strip():
                setattr(self.intent, field, value.strip())
                logger.info(f"✅ Updated {field}: {value}")
    
    # agent/engine/fsm.py (UPDATE THE _get_summary METHOD)

    def _get_summary(self) -> Dict[str, str]:
        """Get booking summary - FIXED field names"""
        summary = {}
        
        # Map internal field names to display names
        field_mapping = {
            "service": "Service",
            "package": "Package",
            "name": "Full Name",
            "phone": "WhatsApp Number",
            "email": "Email",
            "date": "Event Date",
            "address": "Event Location",
            "pincode": "PIN Code",
            "service_country": "Country"
        }
        
        fields = ["service", "package", "name", "phone", "email", 
                "date", "address", "pincode", "service_country"]
        
        for field in fields:
            value = getattr(self.intent, field, None)
            if value:
                display_name = field_mapping.get(field, field.replace('_', ' ').title())
                summary[display_name] = value
        
        return summary
    
    def _get_collected_fields(self) -> Dict[str, str]:
        """Get collected fields"""
        collected = {}
        for field in ["service", "package", "name", "phone", "email", 
                     "date", "address", "pincode", "service_country"]:
            value = getattr(self.intent, field, None)
            if value:
                collected[field] = value
        
        return collected
    
    def _get_booking_info(self) -> Dict[str, Any]:
        """Get booking info for knowledge base"""
        return {
            "service": self.intent.service,
            "package": self.intent.package,
            "collected": self._get_collected_fields(),
            "missing_fields": self.intent.missing_fields()
        }