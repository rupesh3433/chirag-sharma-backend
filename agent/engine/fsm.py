# agent/engine/fsm.py
"""
Finite State Machine Engine - FIXED with master question starters
"""

import logging
import re
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime, timedelta

from ..models.intent import BookingIntent
from ..models.state import BookingState
from ..extractors import (
    PhoneExtractor, EmailExtractor, DateExtractor, 
    NameExtractor, AddressExtractor, PincodeExtractor,
    CountryExtractor
)
from ..validators import PhoneValidator, EmailValidator, DateValidator, PincodeValidator
from ..config.services_config import SERVICES, COUNTRIES, COUNTRY_CODES

logger = logging.getLogger(__name__)


class BookingFSM:
    """Core FSM logic for booking flow"""
    
    # Master question starters list (for ALL languages)
    QUESTION_STARTERS = [
        # 1-word starters
        "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
        "list", "show", "tell", "give", "explain", "describe", "compare",
        "define", "clarify", "summarize",

        # 2-word starters
        "what is", "what are", "what does", "what do", "what kind",
        "what type", "how to", "how do", "how can", "how does", "how should",
        "how much", "how many", "how long", "when is", "where is",
        "who is", "who are", "which is", "which are",
        "tell me", "show me", "give me", "explain this", "describe this",
        "list all", "list your", "compare between", "difference between",
        "price of", "cost of", "details of", "information about",

        # 3-word starters
        "what is the", "what are the", "how much does", "how many types",
        "how can i", "how do i", "how does it", "what does it",
        "tell me about", "show me about", "give me details",
        "give me information", "list all services", "list available services",
        "compare the difference", "difference between two",
        "price of the", "cost of the",

        # Polite / conversational starters
        "can you", "could you", "would you", "will you",
        "can you please", "could you please", "would you please",
        "will you please", "can u", "could u",

        # Knowledge / curiosity starters
        "i want to know", "i would like to know",
        "i want information on", "i would like information on",
        "i need information about", "i am looking for information on",
        "i am curious about", "i want details about",
        "i would like details about",

        # Explanation / teaching starters
        "explain to me", "explain it", "explain this to me",
        "describe it", "describe this", "walk me through",
        "help me understand",

        # Availability / offering starters
        "do you have", "do you offer", "do you provide",
        "are you offering", "is there", "are there",
        "is it possible", "are you able to",

        # Pricing / service info starters
        "what is the price", "what is the cost",
        "how much is", "how much are",
        "how much does it cost", "how much do you charge",
        "charges for", "fee for",

        # Soft / indirect starters
        "i was wondering", "i am wondering",
        "just wanted to ask", "just want to ask",
        "need some information", "need some details",
        "looking for information", "looking for details",

        # Command-style info requests
        "tell me the", "show me the", "give me the",
        "say the", "explain the", "describe the",

        # Edge conversational forms
        "can i know", "could i know", "may i know",
        "is it true that", "is this true",
        "what about", "how about"
    ]
    
    # Social media patterns (should trigger off-topic detection)
    SOCIAL_MEDIA_PATTERNS = [
        'instagram', 'facebook', 'twitter', 'youtube', 'linkedin',
        'social media', 'social', 'media', 'follow', 'subscriber', 
        'subscribers', 'channel', 'profile', 'page', 'account',
        'handle', 'username', 'link', 'website', 'web', 'site',
        'online', 'internet', 'net', 'whatsapp channel', 'telegram',
        'tiktok', 'snapchat', 'pinterest'
    ]
    
    # Off-topic patterns (non-booking related)
    OFF_TOPIC_PATTERNS = [
        'hi', 'hello', 'hey', 'good morning', 'good afternoon',
        'good evening', 'how are you', 'how do you do', 'nice to meet you',
        'thank you', 'thanks', 'please', 'sorry', 'excuse me',
        'never mind', 'forget it', 'cancel', 'stop', 'wait',
        'hold on', 'one second', 'one minute', 'just a moment',
        'let me think', 'i think', 'i believe', 'maybe', 'perhaps',
        'could be', 'not sure', 'i don\'t know', 'i forgot',
        'i don\'t remember', 'remind me', 'tell me again'
    ]
    
    # Booking keywords that should override question detection
    BOOKING_KEYWORDS = ["book", "booking", "reserve", "schedule", "appointment"]
    
    def __init__(self):
        """Initialize FSM"""
        self.services = list(SERVICES.keys())
        self.last_shown_list = None
        self.last_shown_service = None
        
        # Initialize extractors
        self.phone_extractor = PhoneExtractor()
        self.email_extractor = EmailExtractor()
        self.date_extractor = DateExtractor()
        self.name_extractor = NameExtractor()
        self.address_extractor = AddressExtractor()
        self.pincode_extractor = PincodeExtractor()
        self.country_extractor = CountryExtractor()
        
        # Initialize validators
        self.phone_validator = PhoneValidator()
        self.email_validator = EmailValidator()
        self.date_validator = DateValidator()
        self.pincode_validator = PincodeValidator()
    
    def process_message(self, message: str, current_state: str, intent: BookingIntent, 
                       language: str = "en", conversation_history: List[Dict] = None) -> Tuple[str, BookingIntent, Dict[str, Any]]:
        """Main FSM processing method"""
        
        try:
            state_enum = BookingState.from_string(current_state)
            logger.info(f"🎯 FSM Processing: {state_enum.value} | Message: '{message[:100]}...'")
            
            # Route to appropriate handler
            handlers = {
                BookingState.GREETING: self._handle_greeting,
                BookingState.INFO_MODE: self._handle_info_mode,
                BookingState.SELECTING_SERVICE: self._handle_service_selection,
                BookingState.SELECTING_PACKAGE: self._handle_package_selection,
                BookingState.COLLECTING_DETAILS: self._handle_details_collection,
                BookingState.CONFIRMING: self._handle_confirmation,
                BookingState.OTP_SENT: self._handle_otp_verification,
            }
            
            handler = handlers.get(state_enum)
            if handler:
                return handler(message, intent, language, conversation_history or [])
            
            # Default fallback
            return (BookingState.GREETING.value, intent, {
                "error": "Invalid state",
                "action": "reset",
                "message": "Let's start over. How can I help you?",
                "understood": True
            })
            
        except Exception as e:
            logger.error(f"FSM processing error: {e}", exc_info=True)
            return (BookingState.GREETING.value, intent, {
                "error": str(e),
                "action": "error",
                "message": "Sorry, I encountered an error. Let's start over.",
                "understood": True
            })
    
    def _handle_greeting(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle greeting state - FIXED to properly switch to info mode"""
        msg_lower = message.lower().strip()
        
        # Check if it's a chat/info request or general conversation
        chat_phrases = [
            'i want to chat', 'just chat', 'talk', 'converse', 'don\'t book',
            'chat mode', 'switch to chat', 'cancel booking', 'stop booking',
            'why are you showing me list', 'dont show me list', 'tell me about',
            'i just want to talk', 'i want to know', 'tell me more',
            'what is', 'how to', 'can you', 'could you'
        ]
        
        # Check for explicit chat/info mode requests
        if any(phrase in msg_lower for phrase in chat_phrases):
            return (BookingState.INFO_MODE.value, intent, {
                "action": "switch_to_info",
                "message": self._get_chat_response(language),
                "mode": "chat",
                "understood": True
            })
        
        # Check if it's a general question (for info mode)
        if self._is_general_question(msg_lower):
            return (BookingState.INFO_MODE.value, intent, {
                "action": "general_question",
                "message": "",  # Will be handled by knowledge base
                "mode": "chat",
                "understood": False  # Let knowledge base handle
            })
        
        # Check if user wants to book
        if self._is_booking_intent(msg_lower):
            self.last_shown_list = "services"
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self._get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        # Check if it's a service listing request (still info mode)
        if 'list' in msg_lower and 'service' in msg_lower:
            return (BookingState.INFO_MODE.value, intent, {
                "action": "list_services",
                "message": self._get_service_prompt(language),
                "mode": "chat",
                "understood": True
            })
        
        # Default: stay in greeting
        return (BookingState.GREETING.value, intent, {
            "action": "greeting",
            "message": self._get_greeting_message(language),
            "mode": "chat",
            "understood": True
        })


    def _get_chat_response(self, language: str) -> str:
        """Get appropriate response for chat mode"""
        if language == "hi":
            return "नमस्ते! मैं चिराग शर्मा का असिस्टेंट हूं। आप मुझसे मेकअप सेवाओं, कीमतों, या बुकिंग के बारे में पूछ सकते हैं। आज मैं आपकी कैसे मदद कर सकता हूं?"
        elif language == "ne":
            return "नमस्ते! म चिराग शर्माको सहायक हुँ। तपाईं मसँग मेकअप सेवाहरू, मूल्य, वा बुकिङको बारेमा सोध्न सक्नुहुन्छ। आज म तपाईंको कसरी मद्दत गर्न सक्छु?"
        else:
            return "Hello! I'm Chirag Sharma's assistant. You can ask me about makeup services, prices, or booking. How can I help you today?"
    

    def _handle_info_mode(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle info mode - user wants information, not booking - FIXED"""
        msg_lower = message.lower().strip()
        
        # Check if user wants to start booking
        if self._is_booking_intent(msg_lower):
            self.last_shown_list = "services"
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self._get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        # Check if it's specifically about booking methods
        if any(phrase in msg_lower for phrase in ['booking method', 'how to book', 'book through', 'book via', 'book using']):
            # This is a specific question about booking methods
            return (BookingState.INFO_MODE.value, intent, {
                "action": "booking_methods_info",
                "message": "",  # Let knowledge base handle
                "mode": "chat",
                "understood": False  # Will be answered by knowledge base
            })
        
        # Check if it's a general question
        if self._is_general_question(msg_lower):
            return (BookingState.INFO_MODE.value, intent, {
                "action": "general_question",
                "message": "",  # Will be handled by knowledge base
                "mode": "chat",
                "understood": False
            })
        
        # Check for exit from info mode (user wants to book)
        if any(phrase in msg_lower for phrase in ['book now', 'start booking', 'i want to book', 'let\'s book', 'proceed with booking']):
            self.last_shown_list = "services"
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self._get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        # Stay in info mode - let knowledge base handle it
        return (BookingState.INFO_MODE.value, intent, {
            "action": "info_conversation",
            "message": "",  # Will be handled by knowledge base
            "mode": "chat",
            "understood": False
        })
    
    def _is_service_question(self, message: str) -> bool:
        """Check if message is asking about services, prices, etc."""
        msg_lower = message.lower()
        
        service_keywords = [
            'price', 'cost', 'charge', 'rate', 'fee',
            'how much', 'what is the price', 'what does it cost',
            'reception', 'senior', 'artist', 'package',
            'list', 'service', 'services', 'offer', 'provide'
        ]
        
        return any(kw in msg_lower for kw in service_keywords)
    
    def _handle_service_selection(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle service selection state"""
        msg_lower = message.lower().strip()
        
        # Check if it's a question
        if self._is_general_question(msg_lower):
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "question_about_service",
                "message": "",  # Will be handled by knowledge base
                "mode": "booking",
                "understood": False
            })
        
        # Check for numeric selection (1-4)
        num_match = re.search(r'\b([1-4])\b', message)
        if num_match:
            idx = int(num_match.group(1)) - 1
            if 0 <= idx < len(self.services):
                service = self.services[idx]
                intent.service = service
                self.last_shown_list = "packages"
                
                logger.info(f"✅ Service selected: {service}")
                return (BookingState.SELECTING_PACKAGE.value, intent, {
                    "action": "service_selected",
                    "message": self._get_package_prompt(service, language),
                    "collected": {"service": service},
                    "mode": "booking",
                    "understood": True
                })
        
        # Check for service keywords
        service = self._extract_service_selection(message)
        if service:
            intent.service = service
            self.last_shown_list = "packages"
            
            logger.info(f"✅ Service selected via keywords: {service}")
            return (BookingState.SELECTING_PACKAGE.value, intent, {
                "action": "service_selected",
                "message": self._get_package_prompt(service, language),
                "collected": {"service": service},
                "mode": "booking",
                "understood": True
            })
        
        # Not understood - show services again
        logger.warning(f"⚠️ Could not extract service from: {message}")
        return (BookingState.SELECTING_SERVICE.value, intent, {
            "action": "retry_service",
            "message": self._get_service_prompt(language),
            "mode": "booking",
            "understood": False
        })
    
    def _handle_package_selection(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle package selection state"""
        if not intent.service:
            # No service selected - go back
            logger.warning("⚠️ No service selected, going back to service selection")
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self._get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        msg_lower = message.lower().strip()
        
        # Check if it's a question
        if self._is_general_question(msg_lower):
            return (BookingState.SELECTING_PACKAGE.value, intent, {
                "action": "question_about_package",
                "message": "",  # Will be handled by knowledge base
                "mode": "booking",
                "understood": False
            })
        
        # Get packages for the selected service
        if intent.service not in SERVICES:
            logger.error(f"❌ Service not found in config: {intent.service}")
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self._get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        packages = list(SERVICES[intent.service]["packages"].keys())
        
        # Check for numeric selection
        num_match = re.search(r'\b(\d+)\b', message)
        if num_match:
            idx = int(num_match.group(1)) - 1
            if 0 <= idx < len(packages):
                package = packages[idx]
                intent.package = package
                self.last_shown_list = None
                
                logger.info(f"✅ Package selected: {package} for service: {intent.service}")
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "package_selected",
                    "message": self._get_details_prompt(intent, language),
                    "collected": {"package": package},
                    "mode": "booking",
                    "understood": True
                })
            else:
                # Invalid number for this service
                logger.warning(f"⚠️ Invalid package number {idx+1} for service {intent.service}")
        
        # Check for package keywords
        package = self._extract_package_selection(message, intent.service)
        if package:
            intent.package = package
            self.last_shown_list = None
            
            logger.info(f"✅ Package selected via keywords: {package}")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "package_selected",
                "message": self._get_details_prompt(intent, language),
                "collected": {"package": package},
                "mode": "booking",
                "understood": True
            })
        
        # Check if user provided name or other details (they might be trying to skip)
        # Extract name to see if they're providing details
        name_data = self.name_extractor.extract(message)
        if name_data and name_data.get("name"):
            # User provided name instead of package - still ask for package
            logger.warning(f"⚠️ User provided name instead of package selection: {message}")
        
        # Not understood - show packages again
        return (BookingState.SELECTING_PACKAGE.value, intent, {
            "action": "retry_package",
            "message": self._get_package_prompt(intent.service, language),
            "mode": "booking",
            "understood": False
        })




    def _handle_details_collection(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle details collection state - FIXED to check off-topic FIRST"""
        msg_lower = message.lower().strip()
        
        # Step 1: Check for completion intent
        if self._is_completion_intent(msg_lower):
            logger.info(f"ℹ️ User wants to complete: {message}")
            if intent.is_complete():
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "ask_confirmation",
                    "message": self._get_confirmation_prompt(intent, language),
                    "mode": "booking",
                    "understood": True
                })
            else:
                missing = intent.missing_fields()
                logger.info(f"ℹ️ Completion intent with missing fields: {missing}")
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "ask_details",
                    "message": self._get_collected_summary_prompt(intent, missing, language),
                    "missing": missing,
                    "mode": "booking",
                    "understood": True
                })
        
        # Step 2: Check for off-topic questions BEFORE extracting fields
        if self._is_off_topic_question(msg_lower):
            logger.info(f"❓ Detected off-topic question during details collection: {message[:50]}")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "off_topic_question",
                "message": "",  # Will be handled by knowledge base
                "mode": "booking",
                "understood": False  # Let orchestrator handle
            })
        
        # Step 3: Check if it's a booking-related question
        if self._is_general_question(msg_lower):
            # Check if it's specifically about the booking details
            booking_detail_keywords = ['name', 'phone', 'email', 'date', 
                                      'location', 'address', 'pincode', 'country']
            has_booking_detail = any(kw in msg_lower for kw in booking_detail_keywords)
            
            if has_booking_detail:
                # It's a question about booking details - handle it
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "question_about_details",
                    "message": "",  # Will be handled by knowledge base
                    "mode": "booking",
                    "understood": False
                })
            else:
                # It's a general question during details collection
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "general_question_during_details",
                    "message": "",  # Will be handled by knowledge base
                    "mode": "booking",
                    "understood": False
                })
        
        # Step 4: Now try to extract fields (only if not a question)
        extracted = self._extract_all_fields_safe(message, intent, history)
        logger.info(f"ℹ️ Extracted fields from message: {extracted}")
        
        if extracted:
            # Update intent with extracted fields
            updated = False
            collected = {}
            
            for field_name, value in extracted.items():
                if field_name == "phone" and value and not intent.phone:
                    intent.phone = value.get("full_phone") if isinstance(value, dict) else value
                    collected["phone"] = intent.phone
                    updated = True
                    logger.info(f"✅ Collected phone: {intent.phone}")
                elif field_name == "email" and value and not intent.email:
                    intent.email = value
                    collected["email"] = intent.email
                    updated = True
                    logger.info(f"✅ Collected email: {intent.email}")
                elif field_name == "date" and value and not intent.date:
                    intent.date = value
                    collected["date"] = intent.date
                    updated = True
                    logger.info(f"✅ Collected date: {intent.date}")
                elif field_name == "name" and value and not intent.name:
                    intent.name = value
                    collected["name"] = intent.name
                    updated = True
                    logger.info(f"✅ Collected name: {intent.name}")
                elif field_name == "address" and value and not intent.address:
                    # Validate address before accepting
                    if self._is_valid_address(value):
                        intent.address = value
                        collected["address"] = intent.address
                        updated = True
                        logger.info(f"✅ Collected address: {intent.address}")
                    else:
                        logger.warning(f"⚠️ Invalid address detected: {value}")
                elif field_name == "pincode" and value and not intent.pincode:
                    intent.pincode = value
                    collected["pincode"] = intent.pincode
                    updated = True
                    logger.info(f"✅ Collected pincode: {intent.pincode}")
                elif field_name == "country" and value and not intent.service_country:
                    intent.service_country = value
                    collected["service_country"] = intent.service_country
                    updated = True
                    logger.info(f"✅ Collected country: {intent.service_country}")
            
            if updated:
                # Check if all fields are complete
                if intent.is_complete():
                    logger.info(f"✅ All details collected, moving to confirmation")
                    return (BookingState.CONFIRMING.value, intent, {
                        "action": "ask_confirmation",
                        "message": self._get_confirmation_prompt(intent, language),
                        "collected": collected,
                        "mode": "booking",
                        "understood": True
                    })
                
                # Still missing fields - show summary and ask for remaining
                missing = intent.missing_fields()
                logger.info(f"ℹ️ Updated intent, still missing: {missing}")
                
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "ask_details",
                    "message": self._get_collected_summary_prompt(intent, missing, language),
                    "collected": collected,
                    "missing": missing,
                    "mode": "booking",
                    "understood": True
                })
        
        # Step 5: If user says they already provided info
        if any(phrase in msg_lower for phrase in ['already gave', 'already told', 'i gave', 'i told', 'i provided']):
            missing = intent.missing_fields()
            logger.info(f"ℹ️ User says they already provided info. Missing: {missing}")
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "clarify_details",
                "message": self._get_collected_summary_prompt(intent, missing, language),
                "missing": missing,
                "mode": "booking",
                "understood": True
            })
        
        # Step 6: Not understood - show what we have and what we need
        missing = intent.missing_fields()
        if missing:
            logger.info(f"ℹ️ Not understood, showing collected summary. Missing: {missing}")
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": self._get_collected_summary_prompt(intent, missing, language),
                "missing": missing,
                "mode": "booking",
                "understood": False
            })
        
        # Step 7: All fields collected but not confirmed
        return (BookingState.CONFIRMING.value, intent, {
            "action": "ask_confirmation",
            "message": self._get_confirmation_prompt(intent, language),
            "mode": "booking",
            "understood": True
        })
    

    def _extract_all_fields_safe(self, message: str, intent: BookingIntent, history: List = None) -> Dict[str, Any]:
        """Extract fields safely - IMPROVED with better field separation"""
        extracted = {}
        
        # First, extract non-address fields
        extracted_non_address = self._extract_non_address_fields(message, intent)
        extracted.update(extracted_non_address)
        
        # Now extract address from the cleaned message
        if not intent.address:
            # Clean message for address extraction
            cleaned_for_address = self._clean_message_for_address_extraction(message, extracted_non_address)
            
            address_data = self.address_extractor.extract(cleaned_for_address)
            if address_data and address_data.get("address"):
                # Validate the extracted address
                if self._is_valid_address(address_data.get("address")):
                    extracted["address"] = address_data.get("address")
                    logger.info(f"✅ Found address: {address_data.get('address')}")
                else:
                    logger.warning(f"⚠️ Invalid address detected: {address_data.get('address')}")
        
        logger.info(f"📦 Extracted fields: {extracted}")
        return extracted

    def _extract_non_address_fields(self, message: str, intent: BookingIntent) -> Dict[str, Any]:
        """Extract all fields except address"""
        extracted = {}
        
        # Extract pincode
        if not intent.pincode:
            pincode_data = self.pincode_extractor.extract(message)
            if pincode_data:
                extracted["pincode"] = pincode_data.get("pincode")
                logger.info(f"✅ Found pincode: {pincode_data.get('pincode')}")
        
        # Extract date
        if not intent.date:
            date_data = self.date_extractor.extract(message)
            if date_data:
                extracted["date"] = date_data.get("date")
                logger.info(f"✅ Found date: {date_data.get('date')}")
        
        # Extract name
        if not intent.name:
            name_data = self.name_extractor.extract(message)
            if name_data and name_data.get("name"):
                extracted["name"] = name_data.get("name")
                logger.info(f"✅ Found name: {name_data.get('name')}")
        
        # Extract phone
        if not intent.phone:
            phone_data = self.phone_extractor.extract(message)
            if phone_data:
                extracted["phone"] = phone_data
                logger.info(f"✅ Found phone: {phone_data}")
        
        # Extract email
        if not intent.email:
            email_data = self.email_extractor.extract(message)
            if email_data:
                extracted["email"] = email_data.get("email")
                logger.info(f"✅ Found email: {email_data.get('email')}")
        
        # Extract country
        if not intent.service_country:
            country_data = self.country_extractor.extract(message)
            if country_data:
                extracted["country"] = country_data.get("country")
                logger.info(f"✅ Found country: {country_data.get('country')}")
        
        return extracted

    def _clean_message_for_address_extraction(self, message: str, extracted_fields: Dict) -> str:
        """Clean message by removing already-extracted fields"""
        cleaned = message
        
        # Remove pincode if found
        if "pincode" in extracted_fields:
            pincode = extracted_fields["pincode"]
            cleaned = re.sub(rf'\b{re.escape(str(pincode))}\b', ' ', cleaned)
        
        # Remove date if found - handle various date formats
        if "date" in extracted_fields:
            date_str = str(extracted_fields["date"])
            
            # Handle different date formats
            date_patterns = [
                # YYYY-MM-DD
                rf'{re.escape(date_str[:4])}[-/]{re.escape(date_str[5:7])}[-/]{re.escape(date_str[8:10])}',
                # Month DD, YYYY variations
                rf'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{{1,2}}[,\s]+{re.escape(date_str[:4])}',
                rf'{re.escape(date_str[5:7])}/\d{{1,2}}/{re.escape(date_str[:4])}'
            ]
            
            for pattern in date_patterns:
                cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
        
        # Remove phone if found
        if "phone" in extracted_fields:
            phone = extracted_fields["phone"]
            if isinstance(phone, dict):
                phone_num = phone.get("full_phone", "")
            else:
                phone_num = str(phone)
            
            # Remove phone patterns
            phone_num_digits = re.sub(r'\D', '', phone_num)
            if phone_num_digits:
                # Remove with country code
                if phone_num.startswith('+'):
                    cleaned = re.sub(rf'\b{re.escape(phone_num)}\b', ' ', cleaned)
                # Remove without country code (last 10 digits)
                if len(phone_num_digits) >= 10:
                    last_10 = phone_num_digits[-10:]
                    cleaned = re.sub(rf'\b{re.escape(last_10)}\b', ' ', cleaned)
        
        # Remove email if found
        if "email" in extracted_fields:
            email = extracted_fields["email"]
            cleaned = re.sub(rf'\b{re.escape(email)}\b', ' ', cleaned)
        
        # Remove name if found
        if "name" in extracted_fields:
            name = extracted_fields["name"]
            # Split name into parts and remove each
            name_parts = name.split()
            for part in name_parts:
                if len(part) > 2:  # Only remove significant parts
                    cleaned = re.sub(rf'\b{re.escape(part)}\b', ' ', cleaned, flags=re.IGNORECASE)
        
        # Remove country if found
        if "country" in extracted_fields:
            country = extracted_fields["country"]
            cleaned = re.sub(rf'\b{re.escape(country)}\b', ' ', cleaned, flags=re.IGNORECASE)
        
        # Clean up
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r',\s*,', ',', cleaned)
        
        return cleaned
    
    def _is_likely_address(self, message: str) -> bool:
        """Check if message is likely an address (not a question) - IMPROVED"""
        msg_lower = message.lower().strip()
        
        # Check for question indicators
        for starter in self.QUESTION_STARTERS:
            if msg_lower.startswith(starter):
                return False
        
        # Check for social media patterns
        for pattern in self.SOCIAL_MEDIA_PATTERNS:
            if pattern in msg_lower:
                return False
        
        # Check for off-topic patterns
        for pattern in self.OFF_TOPIC_PATTERNS:
            if pattern in msg_lower:
                return False
        
        # Known city names that are likely addresses
        city_names = [

            # =======================
            # 🇮🇳 INDIA (50 cities)
            # =======================
            "delhi", "new delhi", "mumbai", "bangalore", "bengaluru", "chennai",
            "kolkata", "hyderabad", "pune", "ahmedabad", "jaipur", "lucknow",
            "kanpur", "nagpur", "indore", "thane", "bhopal", "visakhapatnam",
            "patna", "vadodara", "ghaziabad", "ludhiana", "agra", "nashik",
            "faridabad", "meerut", "rajkot", "kalyan", "vasai", "varanasi",
            "srinagar", "aurangabad", "dhanbad", "amritsar", "allahabad",
            "prayagraj", "howrah", "gwalior", "jabalpur", "coimbatore",
            "vijayawada", "madurai", "trichy", "salem", "tiruppur",
            "erode", "kochi", "trivandrum", "thrissur",

            # =======================
            # 🇳🇵 NEPAL (50 cities)
            # =======================
            "kathmandu", "lalitpur", "patan", "bhaktapur", "kirtipur",
            "pokhara", "bharatpur", "biratnagar", "morang", "birgunj", "hetauda",
            "janakpur", "dharan", "itahari", "inaruwa", "damak",
            "birtamod", "mechinagar", "butwal", "bhairahawa", "siddharthanagar",
            "tansen", "palpa", "nepalgunj", "kohalpur", "dang",
            "ghorahi", "tulsipur", "surkhet", "dailekh", "dhangadhi",
            "mahendranagar", "attariya", "dadeldhura", "jumla", "dolpa",
            "banepa", "dhulikhel", "panauti", "chitwan", "ratnanagar",
            "sauraha", "illam", "phidim", "taplejung", "baglung",
            "myagdi", "besishahar", "lamjung", "syangja",

            # =======================
            # 🇵🇰 PAKISTAN
            # =======================
            "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad",
            "multan", "gujranwala", "sialkot", "bahawalpur", "sukkur",
            "larkana", "hyderabad pakistan", "quetta", "peshawar", "mardan",
            "abbottabad", "mansehra", "swat", "mingora", "kohat",
            "dera ghazi khan", "dera ismail khan", "rahim yar khan",
            "sheikhupura", "kasur", "okara", "sahiwal",

            # =======================
            # 🇧🇩 BANGLADESH
            # =======================
            "dhaka", "chittagong", "chattogram", "khulna", "rajshahi",
            "sylhet", "barisal", "rangpur", "mymensingh", "comilla",
            "cumilla", "gazipur", "narayanganj", "tangail", "narsingdi",
            "bogura", "bogra", "pabna", "jessore", "jashore",
            "kushtia", "faridpur", "gopalganj", "madaripur",
            "shariatpur", "bhola", "noakhali", "feni", "cox's bazar",

            # =======================
            # 🇦🇪 DUBAI / UAE (Dubai-centric)
            # =======================
            "dubai", "deira", "bur dubai", "karama", "satwa",
            "jumeirah", "jumeirah beach residence", "jbr", "marina",
            "dubai marina", "business bay", "downtown dubai",
            "al barsha", "al quoz", "al nahda", "al qasimia",
            "mirdif", "muhaisnah", "international city",
            "discovery gardens", "jebel ali", "dubai south",
            "motor city", "sports city", "silicon oasis",
            "ras al khor", "al rigga", "al garhoud"
        ]

        
        # Check if it contains a city name
        has_city = any(city in msg_lower for city in city_names)
        
        # Check for address-like patterns
        address_indicators = [
            # Street types
            'street', 'st.', 'st', 'road', 'rd.', 'rd', 'lane', 'ln.',
            'avenue', 'ave.', 'ave', 'boulevard', 'blvd.', 'blvd',
            'drive', 'dr.', 'dr', 'circle', 'cir.', 'court', 'ct.',
            # Building terms
            'house', 'flat', 'apartment', 'apt.', 'apt', 'building', 'bldg.',
            'floor', 'fl.', 'room', 'rm.', 'suite', 'ste.', 'unit',
            # Location terms
            'colony', 'sector', 'area', 'locality', 'village', 'town',
            'city', 'district', 'state', 'county', 'province', 'region',
            # Indian specific
            'nagar', 'marg', 'path', 'gali', 'chowk', 'ward', 'mohalla',
            # Number patterns
            'no.', 'number', '#', 'plot', 'phase', 'extension'
        ]
        
        # Must contain at least ONE address indicator OR a city name
        has_address_indicator = any(ind in msg_lower for ind in address_indicators)
        
        # Should be reasonably long
        word_count = len(msg_lower.split())
        
        return (has_city or has_address_indicator) and word_count >= 1

    

    def _is_valid_address(self, address: str) -> bool:
        """Validate address string - improved to accept cities"""
        if not address or len(address) < 3:
            return False
        
        addr_lower = address.lower()
        
        # Check for question patterns (should not be in address)
        for starter in self.QUESTION_STARTERS:
            if addr_lower.startswith(starter):
                return False
        
        # Check for social media patterns
        for pattern in self.SOCIAL_MEDIA_PATTERNS:
            if pattern in addr_lower:
                return False
        
        # Check for valid address components
        address_components = [
            # Street types
            'street', 'road', 'lane', 'avenue', 'boulevard', 'drive', 'circle',
            # Building terms
            'house', 'flat', 'apartment', 'building', 'floor', 'room', 'suite',
            # Location terms
            'colony', 'sector', 'area', 'locality', 'village', 'town',
            'city', 'district', 'state', 'county', 'province', 'region',
            # Number patterns
            'no.', 'number', '#', 'plot', 'phase', 'extension'
        ]
        
        city_names = [

            # =======================
            # 🇮🇳 INDIA (50 cities)
            # =======================
            "delhi", "new delhi", "mumbai", "bangalore", "bengaluru", "chennai",
            "kolkata", "hyderabad", "pune", "ahmedabad", "jaipur", "lucknow",
            "kanpur", "nagpur", "indore", "thane", "bhopal", "visakhapatnam",
            "patna", "vadodara", "ghaziabad", "ludhiana", "agra", "nashik",
            "faridabad", "meerut", "rajkot", "kalyan", "vasai", "varanasi",
            "srinagar", "aurangabad", "dhanbad", "amritsar", "allahabad",
            "prayagraj", "howrah", "gwalior", "jabalpur", "coimbatore",
            "vijayawada", "madurai", "trichy", "salem", "tiruppur",
            "erode", "kochi", "trivandrum", "thrissur",

            # =======================
            # 🇳🇵 NEPAL (50 cities)
            # =======================
            "kathmandu", "lalitpur", "patan", "bhaktapur", "kirtipur",
            "pokhara", "bharatpur", "biratnagar", "morang", "birgunj", "hetauda",
            "janakpur", "dharan", "itahari", "inaruwa", "damak",
            "birtamod", "mechinagar", "butwal", "bhairahawa", "siddharthanagar",
            "tansen", "palpa", "nepalgunj", "kohalpur", "dang",
            "ghorahi", "tulsipur", "surkhet", "dailekh", "dhangadhi",
            "mahendranagar", "attariya", "dadeldhura", "jumla", "dolpa",
            "banepa", "dhulikhel", "panauti", "chitwan", "ratnanagar",
            "sauraha", "illam", "phidim", "taplejung", "baglung",
            "myagdi", "besishahar", "lamjung", "syangja",

            # =======================
            # 🇵🇰 PAKISTAN
            # =======================
            "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad",
            "multan", "gujranwala", "sialkot", "bahawalpur", "sukkur",
            "larkana", "hyderabad pakistan", "quetta", "peshawar", "mardan",
            "abbottabad", "mansehra", "swat", "mingora", "kohat",
            "dera ghazi khan", "dera ismail khan", "rahim yar khan",
            "sheikhupura", "kasur", "okara", "sahiwal",

            # =======================
            # 🇧🇩 BANGLADESH
            # =======================
            "dhaka", "chittagong", "chattogram", "khulna", "rajshahi",
            "sylhet", "barisal", "rangpur", "mymensingh", "comilla",
            "cumilla", "gazipur", "narayanganj", "tangail", "narsingdi",
            "bogura", "bogra", "pabna", "jessore", "jashore",
            "kushtia", "faridpur", "gopalganj", "madaripur",
            "shariatpur", "bhola", "noakhali", "feni", "cox's bazar",

            # =======================
            # 🇦🇪 DUBAI / UAE (Dubai-centric)
            # =======================
            "dubai", "deira", "bur dubai", "karama", "satwa",
            "jumeirah", "jumeirah beach residence", "jbr", "marina",
            "dubai marina", "business bay", "downtown dubai",
            "al barsha", "al quoz", "al nahda", "al qasimia",
            "mirdif", "muhaisnah", "international city",
            "discovery gardens", "jebel ali", "dubai south",
            "motor city", "sports city", "silicon oasis",
            "ras al khor", "al rigga", "al garhoud"
        ]
        
        # Check if it's a known city
        is_city = any(city in addr_lower for city in city_names)
        
        # Check for address components
        has_component = any(comp in addr_lower for comp in address_components)
        
        # Check word count
        word_count = len(address.split())
        
        # Valid if:
        # 1. It's a known city (even single word like "Delhi"), OR
        # 2. It has address components and is at least 2 words
        return (is_city and word_count >= 1) or (has_component and word_count >= 2)

    def _get_collected_summary_prompt(self, intent: BookingIntent, missing_fields: List[str], language: str) -> str:
        """Get prompt showing collected info and asking for missing fields"""
        
        # Check if date needs year
        date_info = intent.metadata.get('date_info', {}) if hasattr(intent, 'metadata') and intent.metadata else {}
        needs_year = date_info.get('needs_year', False)
        date_original = date_info.get('original', '')
        
        # Get what we've collected
        collected_summary = intent.get_summary()
        
        # Field display names
        field_display = {
            "en": {
                "name": "Full Name",
                "phone": "WhatsApp Number",
                "email": "Email",
                "date": "Event Date",
                "address": "Event Location",
                "pincode": "PIN Code",
                "service_country": "Country"
            },
            "hi": {
                "name": "पूरा नाम",
                "phone": "व्हाट्सएप नंबर",
                "email": "ईमेल",
                "date": "इवेंट तारीख",
                "address": "इवेंट स्थान",
                "pincode": "पिन कोड",
                "service_country": "देश"
            },
            "ne": {
                "name": "पूरा नाम",
                "phone": "व्हाट्सएप नम्बर",
                "email": "इमेल",
                "date": "कार्यक्रम मिति",
                "address": "कार्यक्रम स्थान",
                "pincode": "पिन कोड",
                "service_country": "देश"
            },
            "mr": {
                "name": "पूर्ण नाव",
                "phone": "व्हाट्सएप नंबर",
                "email": "ईमेल",
                "date": "कार्यक्रम तारीख",
                "address": "कार्यक्रम स्थान",
                "pincode": "पिन कोड",
                "service_country": "देश"
            }
        }
        
        lang_display = field_display.get(language, field_display["en"])
        
        if language == "hi":
            prompt = "📋 **आपकी जानकारी:**\n\n"
        elif language == "ne":
            prompt = "📋 **तपाईंको जानकारी:**\n\n"
        elif language == "mr":
            prompt = "📋 **तुमची माहिती:**\n\n"
        else:
            prompt = "📋 **Your Information:**\n\n"
        
        # Show collected fields
        has_collected = False
        for field, value in collected_summary.items():
            if value:  # Only show if we have a value
                display_name = lang_display.get(field.lower().replace(" ", "_"), field)
                prompt += f"✅ **{display_name}:** {value}\n"
                has_collected = True
        
        if has_collected:
            prompt += "\n"
        
        # Special handling for missing year
        if needs_year and date_original:
            if language == "hi":
                prompt += f"📅 **आपने तारीख दी: '{date_original}' लेकिन साल नहीं दिया।**\n"
                prompt += "**कृपया साल दें (जैसे 2025, 2026):**"
            elif language == "ne":
                prompt += f"📅 **तपाईंले मिति दिनुभयो: '{date_original}' तर वर्ष दिनुभएन।**\n"
                prompt += "**कृपया वर्ष दिनुहोस् (जस्तै 2025, 2026):**"
            elif language == "mr":
                prompt += f"📅 **तुम्ही तारीख दिली: '{date_original}' पण वर्ष दिले नाही.**\n"
                prompt += "**कृपया वर्ष द्या (उदा. 2025, 2026):**"
            else:
                prompt += f"📅 **You provided date: '{date_original}' but not the year.**\n"
                prompt += "**Please provide the year (e.g., 2025, 2026):**"
            
            return prompt
        
        # Show missing fields
        if missing_fields:
            missing_display = [lang_display.get(field, field) for field in missing_fields]
            
            if language == "hi":
                prompt += "📝 **कृपया दें:**\n"
            elif language == "ne":
                prompt += "📝 **कृपया दिनुहोस्:**\n"
            elif language == "mr":
                prompt += "📝 **कृपया द्या:**\n"
            else:
                prompt += "📝 **Please provide:**\n"
            
            for field in missing_display:
                prompt += f"• {field}\n"
            
            # Add format hints for specific fields
            if "phone" in missing_fields:
                if language == "hi":
                    prompt += "\n💡 **व्हाट्सएप नंबर:** देश कोड के साथ (+919876543210)"
                elif language == "ne":
                    prompt += "\n💡 **व्हाट्सएप नम्बर:** देश कोड संग (+9779876543210)"
                elif language == "mr":
                    prompt += "\n💡 **व्हाट्सएप नंबर:** देश कोडसह (+919876543210)"
                else:
                    prompt += "\n💡 **WhatsApp Number:** with country code (+919876543210)"
        
        return prompt
    
    def _handle_confirmation(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle confirmation state"""
        msg_lower = message.lower().strip()
        
        # Check if it's a question
        if self._is_general_question(msg_lower):
            return (BookingState.CONFIRMING.value, intent, {
                "action": "question_during_confirmation",
                "message": "",
                "mode": "booking",
                "understood": False
            })
        
        # Check for confirmation
        if any(word in msg_lower for word in ['yes', 'confirm', 'correct', 'proceed', 'ok', 'yeah', 'yep', 'हां', 'हो']):
            return (BookingState.OTP_SENT.value, intent, {
                "action": "send_otp",
                "mode": "booking",
                "understood": True
            })
        
        # Check for rejection/change
        if any(word in msg_lower for word in ['no', 'cancel', 'wrong', 'change', 'edit', 'नहीं', 'होइन']):
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": "What would you like to change? Please provide the corrected information.",
                "mode": "booking",
                "understood": True
            })
        
        # Not understood
        return (BookingState.CONFIRMING.value, intent, {
            "action": "retry_confirmation",
            "message": "Please reply 'yes' to confirm or 'no' to make changes.",
            "mode": "booking",
            "understood": False
        })
    
    def _handle_otp_verification(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle OTP verification state"""
        msg_lower = message.lower().strip()
        
        # Check if it's a question
        if self._is_general_question(msg_lower):
            return (BookingState.OTP_SENT.value, intent, {
                "action": "question_during_otp",
                "message": "",
                "mode": "booking",
                "understood": False
            })
        
        # Check for OTP
        otp_match = re.search(r'\b(\d{6})\b', message)
        if otp_match:
            return (BookingState.OTP_SENT.value, intent, {
                "action": "verify_otp",
                "otp": otp_match.group(1),
                "mode": "booking",
                "understood": True
            })
        
        # Check for resend request
        if any(word in msg_lower for word in ['resend', 'send again', 'missed', "didn't get", 'not received']):
            return (BookingState.OTP_SENT.value, intent, {
                "action": "resend_otp",
                "mode": "booking",
                "understood": True
            })
        
        # Not understood
        return (BookingState.OTP_SENT.value, intent, {
            "action": "ask_otp",
            "message": "Please enter the 6-digit OTP sent to your WhatsApp.",
            "mode": "booking",
            "understood": False
        })
    
    # Helper methods (keep existing ones but fix the issues)
    def _is_booking_intent(self, message: str) -> bool:
        """Check if message indicates booking intent"""
        booking_keywords = ['book', 'booking', 'reserve', 'schedule', 'appointment',
                           'i want to book', 'want to book', 'book service', 'i want your', 
                           'your services', 'your service', 'best services']
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in booking_keywords)
    
    def _is_general_question(self, message: str) -> bool:
        """Check if message is a general question using master list - FIXED"""
        msg_lower = message.lower().strip()
        
        # Check for question mark
        if '?' in message:
            return True
        
        # Check if it starts with any question starter
        for starter in self.QUESTION_STARTERS:
            if msg_lower.startswith(starter):
                # Safety filter: check if it contains booking keywords
                # If it's about booking, it's NOT a general question (it's booking-related)
                if any(b in msg_lower for b in self.BOOKING_KEYWORDS):
                    return False
                return True
        
        # Check for social media patterns
        for pattern in self.SOCIAL_MEDIA_PATTERNS:
            if pattern in msg_lower:
                # If it's asking about social media, it's a general question
                return True
        
        # Check for off-topic patterns
        for pattern in self.OFF_TOPIC_PATTERNS:
            if pattern in msg_lower and len(msg_lower.split()) <= 5:
                return True
        
        return False


    def _is_off_topic_question(self, message: str) -> bool:
        """Check if message is off-topic (not related to booking details) - FIXED"""
        msg_lower = message.lower().strip()
        
        # Check for social media patterns
        for pattern in self.SOCIAL_MEDIA_PATTERNS:
            if pattern in msg_lower:
                return True
        
        # Check if it's a question starter AND doesn't contain booking detail keywords
        booking_detail_keywords = [
            'name', 'phone', 'number', 'email', 'mail',
            'date', 'day', 'month', 'year', 'time',
            'address', 'location', 'place', 'venue',
            'pincode', 'zipcode', 'postal', 'code',
            'country', 'city', 'state', 'district',
            'event', 'function', 'ceremony', 'wedding',
            'my ', 'i ', 'me ', 'mine '  # Personal pronouns
        ]
        
        # Check if it's a question
        is_question = False
        for starter in self.QUESTION_STARTERS:
            if msg_lower.startswith(starter):
                is_question = True
                break
        
        if is_question:
            # Check if it contains booking detail keywords
            has_booking_detail = any(kw in msg_lower for kw in booking_detail_keywords)
            
            # If it's a question but doesn't have booking details, it's off-topic
            if not has_booking_detail:
                return True
        
        # Check for specific off-topic patterns
        off_topic_patterns = [
            'instagram', 'facebook', 'youtube', 'channel',
            'follow', 'subscribe', 'social media',
            'contact', 'reach', 'get in touch',
            'website', 'online', 'web',
            'about you', 'about your', 'who are you',
            'what do you do', 'where are you',
            'experience', 'portfolio', 'gallery',
            'rating', 'review', 'feedback', 'testimonial'
        ]
        
        for pattern in off_topic_patterns:
            if pattern in msg_lower:
                return True
        
        return False
    
    def _is_completion_intent(self, message: str) -> bool:
        """Check if user wants to complete details"""
        completion_keywords = ['done', 'finish', 'complete', 'proceed', 'confirm', 
                              'go ahead', 'all set', 'ready', 'submit']
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in completion_keywords)
    
    def _extract_service_selection(self, message: str) -> Optional[str]:
        """Extract service from message"""
        msg_lower = message.lower()
        
        service_patterns = {
            "Bridal Makeup Services": ['bridal', 'bride', 'wedding', 'marriage'],
            "Party Makeup Services": ['party', 'function', 'celebration'],
            "Engagement & Pre-Wedding Makeup": ['engagement', 'pre-wedding', 'sangeet'],
            "Henna (Mehendi) Services": ['henna', 'mehendi', 'mehndi', 'mehandi']
        }
        
        for service, keywords in service_patterns.items():
            for keyword in keywords:
                if keyword in msg_lower:
                    return service
        
        return None
    
    def _extract_package_selection(self, message: str, service: str) -> Optional[str]:
        """Extract package from message for given service"""
        if service not in SERVICES:
            return None
        
        msg_lower = message.lower()
        packages = list(SERVICES[service]["packages"].keys())
        
        # First check exact package names
        for package in packages:
            package_lower = package.lower()
            if package_lower in msg_lower:
                return package
        
        # Check for keywords
        package_keywords = {
            "Chirag's Signature Bridal Makeup": ['signature', 'chirag', 'premium'],
            "Luxury Bridal Makeup (HD / Brush)": ['luxury', 'hd', 'brush', 'high definition'],
            "Reception / Engagement / Cocktail Makeup": ['reception', 'cocktail', 'engagement'],
            "Chirag Sharma": ['chirag', 'artist'],
            "Senior Artist": ['senior'],
            "Signature Package": ['signature'],
            "Luxury Package": ['luxury', 'premium'],
            "Basic Package": ['basic', 'simple', 'cheapest'],
            "Henna by Chirag Sharma": ['chirag', 'premium', 'signature'],
            "Henna by Senior Artist": ['senior']
        }
        
        for package, keywords in package_keywords.items():
            if package in packages:
                for keyword in keywords:
                    if keyword in msg_lower:
                        return package
        
        return None
    
    def _extract_all_fields(self, message: str, intent: BookingIntent, history: List = None) -> Dict[str, Any]:
        """Extract all possible fields from message with year handling"""
        extracted = {}
        
        # Initialize metadata if not exists
        if not hasattr(intent, 'metadata') or intent.metadata is None:
            intent.metadata = {}
        
        # DEBUG: Log what we're trying to extract
        logger.info(f"🔍 Extracting fields from: {message}")
        
        # Extract pincode FIRST (before other fields might interfere)
        if not intent.pincode:
            logger.info(f"🔍 Looking for pincode in: {message}")
            pincode_data = self.pincode_extractor.extract(message)
            if pincode_data:
                extracted["pincode"] = pincode_data.get("pincode")
                logger.info(f"✅ Found pincode: {pincode_data.get('pincode')}")
            else:
                logger.warning(f"❌ No pincode extracted from: {message}")
        
        # Extract date (only if not already collected)
        if not intent.date:
            date_data = self.date_extractor.extract(message)
            if date_data:
                extracted["date"] = date_data.get("date")
                
                # Store date metadata for year handling
                intent.metadata['date_info'] = {
                    'needs_year': date_data.get('needs_year', False),
                    'assumed_year': date_data.get('assumed_year'),
                    'method': date_data.get('method', 'unknown'),
                    'original': date_data.get('original', ''),
                    'confidence': date_data.get('confidence', 'medium')
                }
                logger.info(f"✅ Found date: {date_data.get('date')}")
        
        # Extract name (only if not already collected)
        if not intent.name:
            name_data = self.name_extractor.extract(message)
            if name_data and name_data.get("name"):
                extracted["name"] = name_data.get("name")
                logger.info(f"✅ Found name: {name_data.get('name')}")
        
        # Extract phone (only if not already collected)
        if not intent.phone:
            phone_data = self.phone_extractor.extract(message)
            if phone_data:
                extracted["phone"] = phone_data
                logger.info(f"✅ Found phone: {phone_data}")
        
        # Extract email (only if not already collected)
        if not intent.email:
            email_data = self.email_extractor.extract(message)
            if email_data:
                extracted["email"] = email_data.get("email")
                logger.info(f"✅ Found email: {email_data.get('email')}")
        
        # Extract address (only if not already collected)
        if not intent.address:
            address_data = self.address_extractor.extract(message)
            if address_data:
                extracted["address"] = address_data.get("address")
                logger.info(f"✅ Found address: {address_data.get('address')}")
        
        # Extract country (only if not already collected)
        if not intent.service_country:
            country_data = self.country_extractor.extract(message)
            if country_data:
                extracted["country"] = country_data.get("country")
                logger.info(f"✅ Found country: {country_data.get('country')}")
        
        logger.info(f"📦 Final extracted fields: {extracted}")
        return extracted
    
    def _extract_year_from_message(self, message: str) -> Optional[int]:
        """Extract year from message (e.g., 2025, 2026)"""
        year_match = re.search(r'\b(20[2-9][0-9]|2100)\b', message)
        if year_match:
            try:
                year = int(year_match.group(1))
                # Validate year is reasonable (2023-2100)
                current_year = datetime.now().year
                if current_year - 1 <= year <= current_year + 10:
                    return year
            except (ValueError, TypeError):
                pass
        return None

    
    def _handle_year_response(self, message: str, intent: BookingIntent, language: str) -> Tuple[str, BookingIntent, Dict]:
        """Handle when user provides year after partial date"""
        year = self._extract_year_from_message(message)
        
        if year:
            # Check if we have a date that needs year
            date_info = intent.metadata.get('date_info', {})
            
            if date_info.get('needs_year', False) and intent.date:
                try:
                    # Update the date with correct year
                    from datetime import datetime
                    old_date = datetime.strptime(intent.date, '%Y-%m-%d')
                    new_date = old_date.replace(year=year)
                    intent.date = new_date.strftime('%Y-%m-%d')
                    
                    # Update metadata
                    intent.metadata['date_info']['needs_year'] = False
                    intent.metadata['date_info']['user_provided_year'] = year
                    intent.metadata['date_info']['assumed_year'] = year
                    
                    # Show updated summary
                    missing = intent.missing_fields()
                    
                    return (BookingState.COLLECTING_DETAILS.value, intent, {
                        "action": "year_provided",
                        "message": f"✅ Updated year to {year}. {self._get_collected_summary_prompt(intent, missing, language)}",
                        "mode": "booking",
                        "understood": True
                    })
                except Exception as e:
                    logger.error(f"Error updating year: {e}")
        
        # If no valid year found, ask for it
        date_original = intent.metadata.get('date_info', {}).get('original', 'the date')
        
        if language == "hi":
            prompt = f"📅 **आपने तारीख दी: '{date_original}' लेकिन साल नहीं दिया। कृपया साल दें (जैसे 2025, 2026):**"
        elif language == "ne":
            prompt = f"📅 **तपाईंले मिति दिनुभयो: '{date_original}' तर वर्ष दिनुभएन। कृपया वर्ष दिनुहोस् (जस्तै 2025, 2026):**"
        elif language == "mr":
            prompt = f"📅 **तुम्ही तारीख दिली: '{date_original}' पण वर्ष दिले नाही. कृपया वर्ष द्या (उदा. 2025, 2026):**"
        else:
            prompt = f"📅 **You provided date: '{date_original}' but not the year. Please provide the year (e.g., 2025, 2026):**"
        
        return (BookingState.COLLECTING_DETAILS.value, intent, {
            "action": "ask_year",
            "message": prompt,
            "mode": "booking",
            "understood": False
        })

    # Prompt methods
    def _get_greeting_message(self, language: str) -> str:
        """Get greeting message"""
        if language == "hi":
            return "नमस्ते! मैं चिराग शर्मा का असिस्टेंट हूं। आपकी बुकिंग में कैसे मदद कर सकता हूं?"
        elif language == "ne":
            return "नमस्ते! म चिराग शर्माको सहायक हुँ। तपाईंको बुकिङमा कसरी मद्दत गर्न सक्छु?"
        elif language == "mr":
            return "नमस्कार! मी चिराग शर्मा यांचा सहाय्यक आहे. तुमच्या बुकिंगमध्ये मी कशी मदत करू शकतो?"
        else:
            return "Hello! I'm Chirag Sharma's assistant. How can I help you with your booking?"
    
    def _get_service_prompt(self, language: str) -> str:
        """Get service selection prompt"""
        if language == "hi":
            return """🎯 **उपलब्ध सेवाएं:**

1. **ब्राइडल मेकअप सेवाएं** - चिराग शर्मा द्वारा प्रीमियम ब्राइडल मेकअप
2. **पार्टी मेकअप सेवाएं** - पार्टियों और विशेष अवसरों के लिए मेकअप
3. **एंगेजमेंट और प्री-वेडिंग मेकअप** - एंगेजमेंट फंक्शन के लिए मेकअप
4. **मेंहदी सेवाएं** - ब्राइडल और विशेष अवसरों के लिए मेंहदी सेवाएं

**कृपया एक नंबर (1-4) चुनें या सेवा का नाम लिखें।**"""
        elif language == "ne":
            return """🎯 **उपलब्ध सेवाहरू:**

1. **ब्राइडल मेकअप सेवाहरू** - चिराग शर्मा द्वारा प्रीमियम ब्राइडल मेकअप
2. **पार्टी मेकअप सेवाहरू** - पार्टी र विशेष अवसरहरूको लागि मेकअप
3. **इन्गेजमेन्ट र प्री-वेडिंग मेकअप** - इन्गेजमेन्ट समारोहहरूको लागि मेकअप
4. **हेन्ना सेवाहरू** - ब्राइडल र विशेष अवसरहरूको लागि हेन्ना सेवाहरू

**कृपया नम्बर (1-4) छनोट गर्नुहोस् वा सेवाको नाम लेख्नुहोस्।**"""
        elif language == "mr":
            return """🎯 **उपलब्ध सेवा:**

1. **ब्राइडल मेकअप सेवा** - चिराग शर्मा यांच्याकडून प्रीमियम ब्राइडल मेकअप
2. **पार्टी मेकअप सेवा** - पार्टी आणि विशेष प्रसंगांसाठी मेकअप
3. **एंगेजमेंट आणि प्री-वेडिंग मेकअप** - एंगेजमेंट फंक्शनसाठी मेकअप
4. **हेन्ना सेवा** - ब्राइडल आणि विशेष प्रसंगांसाठी हेन्ना सेवा

**कृपया क्रमांक (1-4) निवडा किंवा सेवेचे नाव लिहा.**"""
        else:
            return """🎯 **Available Services:**

1. **Bridal Makeup Services** - Premium bridal makeup by Chirag Sharma
2. **Party Makeup Services** - Makeup for parties and special occasions
3. **Engagement & Pre-Wedding Makeup** - Makeup for engagement functions
4. **Henna (Mehendi) Services** - Henna services for bridal and special occasions

**Please choose a number (1-4) or type the service name.**"""
    
    def _get_package_prompt(self, service: str, language: str) -> str:
        """Get package selection prompt - FIXED to show correct packages"""
        if service not in SERVICES:
            logger.error(f"❌ Service not found: {service}")
            return f"Sorry, service '{service}' not found. Please choose from available services."
        
        packages = SERVICES[service]["packages"]
        
        if language == "hi":
            prompt = f"📦 **{service} के पैकेज:**\n\n"
            for idx, (pkg_name, price) in enumerate(packages.items(), 1):
                prompt += f"{idx}. **{pkg_name}** - {price}\n"
            prompt += f"\n**कृपया एक नंबर (1-{len(packages)}) चुनें या पैकेज का नाम लिखें।**"
            return prompt
        elif language == "ne":
            prompt = f"📦 **{service} को प्याकेजहरू:**\n\n"
            for idx, (pkg_name, price) in enumerate(packages.items(), 1):
                prompt += f"{idx}. **{pkg_name}** - {price}\n"
            prompt += f"\n**कृपया नम्बर (1-{len(packages)}) छनोट गर्नुहोस् वा प्याकेजको नाम लेख्नुहोस्।**"
            return prompt
        elif language == "mr":
            prompt = f"📦 **{service} चे पॅकेज:**\n\n"
            for idx, (pkg_name, price) in enumerate(packages.items(), 1):
                prompt += f"{idx}. **{pkg_name}** - {price}\n"
            prompt += f"\n**कृपया क्रमांक (1-{len(packages)}) निवडा किंवा पॅकेजचे नाव लिहा.**"
            return prompt
        else:
            prompt = f"📦 **Packages for {service}:**\n\n"
            for idx, (pkg_name, price) in enumerate(packages.items(), 1):
                prompt += f"{idx}. **{pkg_name}** - {price}\n"
            prompt += f"\n**Please choose a number (1-{len(packages)}) or type the package name.**"
            return prompt
    
    def _get_details_prompt(self, intent: BookingIntent, language: str) -> str:
        """Get details collection prompt - ASK FOR ALL DETAILS AT ONCE"""
        if language == "hi":
            return """📋 **कृपया अपना विवरण दें:**

आप एक बार में सभी विवरण दे सकते हैं या एक-एक करके:

• **पूरा नाम:**
• **व्हाट्सएप नंबर** (देश कोड के साथ, जैसे +919876543210):
• **ईमेल:**
• **इवेंट तारीख** (जैसे 25 मार्च 2025):
• **इवेंट स्थान:**
• **पिन कोड:**
• **देश** (भारत/नेपाल/पाकिस्तान/बांग्लादेश/दुबई):

**उदाहरण:** "रमेश कुमार, +919876543210, ramesh@email.com, 15 अप्रैल 2025, दिल्ली, 110001, भारत"

आपका पूरा नाम क्या है?"""
        elif language == "ne":
            return """📋 **कृपया आफ्नो विवरण दिनुहोस्:**

तपाईं एकै पटक सबै विवरण दिन सक्नुहुन्छ वा एक-एक गरेर:

• **पूरा नाम:**
• **व्हाट्सएप नम्बर** (देश कोड सहित, जस्तै +9779876543210):
• **इमेल:**
• **कार्यक्रम मिति** (जस्तै 25 मार्च 2025):
• **कार्यक्रम स्थान:**
• **पिन कोड:**
• **देश** (भारत/नेपाल/पाकिस्तान/बंगलादेश/दुबई):

**उदाहरण:** "रमेश कुमार, +9779876543210, ramesh@email.com, 15 अप्रैल 2025, काठमाडौं, 44600, नेपाल"

तपाईंको पूरा नाम के हो?"""
        elif language == "mr":
            return """📋 **कृपया तुमचे तपशील द्या:**

तुम्ही एकाच वेळी सर्व तपशील देऊ शकता किंवा एक-एक करून:

• **पूर्ण नाव:**
• **व्हाट्सएप नंबर** (देश कोडसह, उदा. +919876543210):
• **ईमेल:**
• **कार्यक्रम तारीख** (उदा. 25 मार्च 2025):
• **कार्यक्रम स्थान:**
• **पिन कोड:**
• **देश** (भारत/नेपाळ/पाकिस्तान/बांग्लादेश/दुबई):

**उदाहरण:** "रमेश कुमार, +919876543210, ramesh@email.com, 15 एप्रिल 2025, मुंबई, 400001, भारत"

तुमचे पूर्ण नाव काय आहे?"""
        else:
            return """📋 **Please provide your details:**

You can provide all details at once or one by one:

• **Full Name:**
• **WhatsApp Number** (with country code, e.g., +919876543210):
• **Email:**
• **Event Date** (e.g., March 25, 2025):
• **Event Location:**
• **PIN Code:**
• **Country** (India/Nepal/Pakistan/Bangladesh/Dubai):

**Example:** "Ramesh Kumar, +919876543210, ramesh@email.com, April 15, 2025, Delhi, 110001, India"

What is your full name?"""
    
    def _get_missing_fields_prompt(self, missing_fields: List[str], language: str) -> str:
        """Get prompt for missing fields"""
        if not missing_fields:
            return "All details collected!"
        
        # Map field names to display names
        field_names = {
            "en": {
                "name": "full name",
                "phone": "phone number with country code",
                "email": "email address",
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
            if language == "hi":
                return f"📋 **कृपया दें:** {display_fields[0]}"
            elif language == "ne":
                return f"📋 **कृपया दिनुहोस्:** {display_fields[0]}"
            elif language == "mr":
                return f"📋 **कृपया द्या:** {display_fields[0]}"
            else:
                return f"📋 **Please provide:** {display_fields[0]}"
        else:
            if language == "hi":
                return f"📋 **कृपया दें:** {', '.join(display_fields)}"
            elif language == "ne":
                return f"📋 **कृपया दिनुहोस्:** {', '.join(display_fields)}"
            elif language == "mr":
                return f"📋 **कृपया द्या:** {', '.join(display_fields)}"
            else:
                return f"📋 **Please provide:** {', '.join(display_fields)}"
    
    def _get_confirmation_prompt(self, intent: BookingIntent, language: str) -> str:
        """Get confirmation prompt"""
        summary = intent.get_summary()
        
        if language == "hi":
            prompt = "🎯 **कृपया अपनी बुकिंग की पुष्टि करें:**\n\n"
            for field, value in summary.items():
                prompt += f"• **{field}:** {value}\n"
            prompt += "\n**क्या सब कुछ सही है?** ('हां' या 'नहीं')"
            return prompt
        elif language == "ne":
            prompt = "🎯 **कृपया आफ्नो बुकिङ पुष्टि गर्नुहोस्:**\n\n"
            for field, value in summary.items():
                prompt += f"• **{field}:** {value}\n"
            prompt += "\n**के सबै ठीक छ?** ('हो' वा 'होइन')"
            return prompt
        elif language == "mr":
            prompt = "🎯 **कृपया तुमची बुकिंग पुष्टी करा:**\n\n"
            for field, value in summary.items():
                prompt += f"• **{field}:** {value}\n"
            prompt += "\n**सर्व काही बरोबर आहे का?** ('हो' किंवा 'नाही')"
            return prompt
        else:
            prompt = "🎯 **Please confirm your booking:**\n\n"
            for field, value in summary.items():
                prompt += f"• **{field}:** {value}\n"
            prompt += "\n**Is everything correct?** (Reply 'yes' or 'no')"
            return prompt