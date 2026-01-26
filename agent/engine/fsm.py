"""
Finite State Machine Engine - HIGHLY MODULAR VERSION
Main file only contains routing logic
"""
import logging
from typing import Tuple, Dict, Any, List

from ..models.intent import BookingIntent
from ..models.state import BookingState
from ..config.services_config import SERVICES

# Import all modular components
from .field_processors import FieldProcessors
from .message_generators import MessageGenerators
from .special_handlers import SpecialHandlers
from .sequential_processor import SequentialProcessor
from .details_collector import DetailsCollector

# Import existing utilities
from .message_validators import MessageValidators
from .message_extractors import MessageExtractors
from .field_extractors import FieldExtractors
from .prompt_generators import PromptGenerators
from .address_validator import AddressValidator

logger = logging.getLogger(__name__)

class BookingFSM:
    """
    HIGHLY MODULAR FSM
    - Main file only does routing
    - All logic moved to specialized classes
    """
    
    def __init__(self):
        """Initialize FSM with all modular components."""
        self.services = list(SERVICES.keys())
        self.last_shown_list = None
        self.last_shown_service = None
        
        # Initialize core utilities
        self.validators = MessageValidators()
        self.extractors = MessageExtractors()
        self.field_extractors = FieldExtractors()
        self.prompts = PromptGenerators()
        self.address_validator = AddressValidator()
        
        # Initialize modular components
        self.field_processors = FieldProcessors(self.address_validator)
        self.message_generators = MessageGenerators(self.prompts)
        self.special_handlers = SpecialHandlers(self.extractors, self.prompts)
        self.sequential_processor = SequentialProcessor(self.message_generators)
        
        # Initialize details collector (orchestrates everything)
        self.details_collector = DetailsCollector(
            field_processors=self.field_processors,
            message_generators=self.message_generators,
            special_handlers=self.special_handlers,
            sequential_processor=self.sequential_processor,
            validators=self.validators,
            field_extractors=self.field_extractors,
            prompts=self.prompts,
            address_validator=self.address_validator
        )
        
        logger.info("🚀 Highly Modular BookingFSM initialized")
    
    def process_message(
        self,
        message: str,
        current_state: str,
        intent: BookingIntent,
        language: str = "en",
        conversation_history: List[Dict] = None
    ) -> Tuple[str, BookingIntent, Dict[str, Any]]:
        """Main FSM processing - ONLY ROUTING LOGIC"""
        try:
            state_enum = BookingState.from_string(current_state)
            logger.info(f"🎯 FSM Processing: {state_enum.value} | Message: '{message[:100]}...'")
            
            # Special handling for year response
            if state_enum == BookingState.COLLECTING_DETAILS:
                date_info = intent.metadata.get('date_info', {}) if hasattr(intent, 'metadata') and intent.metadata else {}
                if date_info.get('needs_year', False):
                    return self.special_handlers.handle_year_response(message, intent, language)
            
            # Route to appropriate handler
            return self._route_to_handler(state_enum, message, intent, language, conversation_history)
            
        except Exception as e:
            logger.error(f"FSM processing error: {e}", exc_info=True)
            return self._handle_error(intent, e)
    
    def _route_to_handler(
        self,
        state_enum: BookingState,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Tuple[str, BookingIntent, Dict]:
        """Route to appropriate state handler."""
        handlers = {
            BookingState.GREETING: self._handle_greeting,
            BookingState.INFO_MODE: self._handle_info_mode,
            BookingState.SELECTING_SERVICE: self._handle_service_selection,
            BookingState.SELECTING_PACKAGE: self._handle_package_selection,
            BookingState.COLLECTING_DETAILS: self.details_collector.collect_details,
            BookingState.CONFIRMING: self._handle_confirmation,
            BookingState.OTP_SENT: self._handle_otp_verification,
        }
        
        handler = handlers.get(state_enum)
        if handler:
            return handler(message, intent, language, history or [])
        
        # Default fallback
        return self._handle_invalid_state(intent)
    
    def _handle_greeting(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle greeting state."""
        msg_lower = message.lower().strip()
        
        # Check for chat/info mode
        chat_phrases = [
            'i want to chat', 'just chat', 'talk', 'converse', 'don\'t book',
            'chat mode', 'switch to chat', 'cancel booking', 'stop booking',
            'why are you showing me list', 'dont show me list', 'tell me about',
            'i just want to talk', 'i want to know', 'tell me more'
        ]
        
        if any(phrase in msg_lower for phrase in chat_phrases):
            return (BookingState.INFO_MODE.value, intent, {
                "action": "switch_to_info",
                "message": self.prompts.get_chat_response(language),
                "mode": "chat",
                "understood": True
            })
        
        # General question
        if self.validators.is_general_question(msg_lower):
            return (BookingState.INFO_MODE.value, intent, {
                "action": "general_question",
                "message": "",  # Knowledge base handles
                "mode": "chat",
                "understood": False
            })
        
        # Booking intent
        if self.validators.is_booking_intent(msg_lower):
            self.last_shown_list = "services"
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self.prompts.get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        # Default greeting
        return (BookingState.GREETING.value, intent, {
            "action": "greeting",
            "message": self.prompts.get_greeting_message(language),
            "mode": "chat",
            "understood": True
        })
    
    def _handle_info_mode(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle info mode."""
        msg_lower = message.lower().strip()
        
        if self.validators.is_booking_intent(msg_lower):
            self.last_shown_list = "services"
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self.prompts.get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        if self.validators.is_general_question(msg_lower):
            return (BookingState.INFO_MODE.value, intent, {
                "action": "general_question",
                "message": "",  # Knowledge base handles
                "mode": "chat",
                "understood": False
            })
        
        return (BookingState.INFO_MODE.value, intent, {
            "action": "info_conversation",
            "message": "",  # Knowledge base handles
            "mode": "chat",
            "understood": False
        })
    
    def _handle_service_selection(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle service selection."""
        msg_lower = message.lower().strip()
        
        if self.validators.is_general_question(msg_lower):
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "question_about_service",
                "message": "",  # Knowledge base handles
                "mode": "booking",
                "understood": False
            })
        
        # Check for numeric selection (1-4)
        import re
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
                    "message": self.prompts.get_package_prompt(service, language),
                    "collected": {"service": service},
                    "mode": "booking",
                    "understood": True
                })
        
        # Check for service keywords
        service = self.extractors.extract_service_selection(message)
        if service:
            intent.service = service
            self.last_shown_list = "packages"
            
            logger.info(f"✅ Service selected via keywords: {service}")
            return (BookingState.SELECTING_PACKAGE.value, intent, {
                "action": "service_selected",
                "message": self.prompts.get_package_prompt(service, language),
                "collected": {"service": service},
                "mode": "booking",
                "understood": True
            })
        
        # Not understood
        logger.warning(f"⚠️ Could not extract service from: {message}")
        return (BookingState.SELECTING_SERVICE.value, intent, {
            "action": "retry_service",
            "message": self.prompts.get_service_prompt(language),
            "mode": "booking",
            "understood": False
        })
    
    def _handle_package_selection(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle package selection."""
        if not intent.service:
            logger.warning("⚠️ No service selected, going back to service selection")
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self.prompts.get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        msg_lower = message.lower().strip()
        
        if self.validators.is_general_question(msg_lower):
            return (BookingState.SELECTING_PACKAGE.value, intent, {
                "action": "question_about_package",
                "message": "",  # Knowledge base handles
                "mode": "booking",
                "understood": False
            })
        
        # Get packages for the selected service
        if intent.service not in SERVICES:
            logger.error(f"❌ Service not found in config: {intent.service}")
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self.prompts.get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        packages = list(SERVICES[intent.service]["packages"].keys())
        
        # Check for numeric selection
        import re
        num_match = re.search(r'\b(\d+)\b', message)
        if num_match:
            idx = int(num_match.group(1)) - 1
            if 0 <= idx < len(packages):
                package = packages[idx]
                intent.package = package
                self.last_shown_list = None
                
                # CRITICAL FIX: Initialize sequential mode when entering details collection
                if not hasattr(intent, 'metadata') or intent.metadata is None:
                    intent.metadata = {}
                intent.metadata['_asking_mode'] = 'sequential'
                logger.info("🔄 Sequential mode initialized for details collection")
                
                logger.info(f"✅ Package selected: {package} for service: {intent.service}")
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "package_selected",
                    "message": self.prompts.get_details_prompt(intent, language),
                    "collected": {"package": package},
                    "mode": "booking",
                    "understood": True
                })
        
        # Check for package keywords
        package = self.extractors.extract_package_selection(message, intent.service)
        if package:
            intent.package = package
            self.last_shown_list = None
            
            # CRITICAL FIX: Initialize sequential mode when entering details collection
            if not hasattr(intent, 'metadata') or intent.metadata is None:
                intent.metadata = {}
            intent.metadata['_asking_mode'] = 'sequential'
            logger.info("🔄 Sequential mode initialized for details collection")
            
            logger.info(f"✅ Package selected via keywords: {package}")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "package_selected",
                "message": self.prompts.get_details_prompt(intent, language),
                "collected": {"package": package},
                "mode": "booking",
                "understood": True
            })
        
        # Not understood
        return (BookingState.SELECTING_PACKAGE.value, intent, {
            "action": "retry_package",
            "message": self.prompts.get_package_prompt(intent.service, language),
            "mode": "booking",
            "understood": False
        })
    
    def _handle_confirmation(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle confirmation state."""
        msg_lower = message.lower().strip()
        
        if self.validators.is_general_question(msg_lower):
            return (BookingState.CONFIRMING.value, intent, {
                "action": "question_during_confirmation",
                "message": "",  # Knowledge base handles
                "mode": "booking",
                "understood": False
            })
        
        if self.validators.is_confirmation(msg_lower):
            # Format phone for display
            phone_display = ""
            if intent.phone:
                if isinstance(intent.phone, dict):
                    phone_display = intent.phone.get('formatted', intent.phone.get('full_phone', str(intent.phone)))
                else:
                    phone_display = str(intent.phone)
            
            return (BookingState.OTP_SENT.value, intent, {
                "action": "send_otp",
                "booking_summary": {
                    "service": intent.service,
                    "package": intent.package,
                    "name": intent.name,
                    "email": intent.email,
                    "phone": phone_display,
                    "date": intent.date,
                    "address": intent.address,
                    "pincode": intent.pincode,
                    "country": intent.service_country
                },
                "mode": "booking",
                "understood": True
            })
        
        if self.validators.is_rejection(msg_lower):
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "change_details",
                "message": "What would you like to change? Please provide the corrected information.",
                "mode": "booking",
                "understood": True
            })
        
        return (BookingState.CONFIRMING.value, intent, {
            "action": "retry_confirmation",
            "message": "Please reply 'yes' to confirm or 'no' to make changes.",
            "mode": "booking",
            "understood": False
        })
    
    def _handle_otp_verification(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle OTP verification state."""
        msg_lower = message.lower().strip()
        
        if self.validators.is_general_question(msg_lower):
            return (BookingState.OTP_SENT.value, intent, {
                "action": "question_during_otp",
                "message": "",  # Knowledge base handles
                "mode": "booking",
                "understood": False
            })
        
        # Check for OTP
        import re
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
        
        return (BookingState.OTP_SENT.value, intent, {
            "action": "ask_otp",
            "message": "Please enter the 6-digit OTP sent to your WhatsApp.",
            "mode": "booking",
            "understood": False
        })
    
    def _handle_invalid_state(self, intent: BookingIntent) -> Tuple[str, BookingIntent, Dict]:
        """Handle invalid state."""
        return (BookingState.GREETING.value, intent, {
            "error": "Invalid state",
            "action": "reset",
            "message": "Let's start over. How can I help you?",
            "understood": True
        })
    
    def _handle_error(self, intent: BookingIntent, error: Exception) -> Tuple[str, BookingIntent, Dict]:
        """Handle errors."""
        logger.error(f"FSM processing error: {error}", exc_info=True)
        return (BookingState.GREETING.value, intent, {
            "error": str(error),
            "action": "error",
            "message": "Sorry, I encountered an error. Let's start over.",
            "understood": True
        })