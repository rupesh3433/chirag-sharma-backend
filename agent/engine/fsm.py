"""
Finite State Machine Engine - ULTIMATE OPTIMIZED VERSION
Integrates with actual FieldExtractor and maintains all existing functionality
"""
import logging
import re
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime

from ..models.intent import BookingIntent
from ..models.state import BookingState
from ..config.services_config import SERVICES

from .engine_config import QUESTION_STARTERS
from .message_validators import MessageValidators
from .message_extractors import MessageExtractors
from .field_extractors import FieldExtractors
from .prompt_generators import PromptGenerators
from .address_validator import AddressValidator

# Import validators for additional validation
from ..validators.phone_validator import PhoneValidator
from ..validators.email_validator import EmailValidator
from ..validators.date_validator import DateValidator
from ..validators.pincode_validator import PincodeValidator

logger = logging.getLogger(__name__)


class BookingFSM:
    """
    ULTIMATE OPTIMIZED FSM
    - Uses actual FieldExtractor with ALL advanced methods
    - Maintains backward compatibility
    - Preserves knowledge base integration
    """
    
    def __init__(self):
        """Initialize FSM with all utility classes"""
        self.services = list(SERVICES.keys())
        self.last_shown_list = None
        self.last_shown_service = None
        
        # Initialize utility classes
        self.validators = MessageValidators()
        self.extractors = MessageExtractors()
        self.field_extractors = FieldExtractors()  # Uses actual FieldExtractor
        self.prompts = PromptGenerators()
        self.address_validator = AddressValidator()
        
        # ✨ Initialize dedicated validators for additional validation
        self.phone_validator = PhoneValidator()
        self.email_validator = EmailValidator()
        self.date_validator = DateValidator()
        self.pincode_validator = PincodeValidator()
        
        logger.info("🚀 ULTIMATE Optimized BookingFSM initialized")
    
    def process_message(self, message: str, current_state: str, intent: BookingIntent, 
                       language: str = "en", conversation_history: List[Dict] = None) -> Tuple[str, BookingIntent, Dict[str, Any]]:
        """Main FSM processing method - OPTIMIZED"""
        try:
            state_enum = BookingState.from_string(current_state)
            logger.info(f"🎯 FSM Processing: {state_enum.value} | Message: '{message[:100]}...'")
            
            # Special handling for year response if needed
            if state_enum == BookingState.COLLECTING_DETAILS:
                date_info = intent.metadata.get('date_info', {}) if hasattr(intent, 'metadata') and intent.metadata else {}
                if date_info.get('needs_year', False):
                    return self._handle_year_response(message, intent, language)
            
            # Route to appropriate handler
            handlers = {
                BookingState.GREETING: self._handle_greeting,
                BookingState.INFO_MODE: self._handle_info_mode,
                BookingState.SELECTING_SERVICE: self._handle_service_selection,
                BookingState.SELECTING_PACKAGE: self._handle_package_selection,
                BookingState.COLLECTING_DETAILS: self._handle_details_collection_ultimate,
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
        """Handle greeting state"""
        msg_lower = message.lower().strip()
        
        # Check for chat/info mode requests
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
        
        # Check if it's a general question (for info mode)
        if self.validators.is_general_question(msg_lower):
            return (BookingState.INFO_MODE.value, intent, {
                "action": "general_question",
                "message": "",  # Knowledge base handles
                "mode": "chat",
                "understood": False
            })
        
        # Check if user wants to book
        if self.validators.is_booking_intent(msg_lower):
            self.last_shown_list = "services"
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self.prompts.get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        # Default: stay in greeting
        return (BookingState.GREETING.value, intent, {
            "action": "greeting",
            "message": self.prompts.get_greeting_message(language),
            "mode": "chat",
            "understood": True
        })
    
    def _handle_info_mode(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle info mode - user wants information, not booking"""
        msg_lower = message.lower().strip()
        
        # Check if user wants to start booking
        if self.validators.is_booking_intent(msg_lower):
            self.last_shown_list = "services"
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self.prompts.get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        # Check if it's a general question - let knowledge base handle
        if self.validators.is_general_question(msg_lower):
            return (BookingState.INFO_MODE.value, intent, {
                "action": "general_question",
                "message": "",  # Knowledge base handles
                "mode": "chat",
                "understood": False
            })
        
        # Stay in info mode - let knowledge base handle it
        return (BookingState.INFO_MODE.value, intent, {
            "action": "info_conversation",
            "message": "",  # Knowledge base handles
            "mode": "chat",
            "understood": False
        })
    
    def _handle_service_selection(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle service selection state"""
        msg_lower = message.lower().strip()
        
        # Check if it's a question - let knowledge base handle
        if self.validators.is_general_question(msg_lower):
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "question_about_service",
                "message": "",  # Knowledge base handles
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
        
        # Not understood - show services again
        logger.warning(f"⚠️ Could not extract service from: {message}")
        return (BookingState.SELECTING_SERVICE.value, intent, {
            "action": "retry_service",
            "message": self.prompts.get_service_prompt(language),
            "mode": "booking",
            "understood": False
        })
    
    def _handle_package_selection(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle package selection state"""
        if not intent.service:
            logger.warning("⚠️ No service selected, going back to service selection")
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self.prompts.get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        msg_lower = message.lower().strip()
        
        # Check if it's a question - let knowledge base handle
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
            
            logger.info(f"✅ Package selected via keywords: {package}")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "package_selected",
                "message": self.prompts.get_details_prompt(intent, language),
                "collected": {"package": package},
                "mode": "booking",
                "understood": True
            })
        
        # Not understood - show packages again
        return (BookingState.SELECTING_PACKAGE.value, intent, {
            "action": "retry_package",
            "message": self.prompts.get_package_prompt(intent.service, language),
            "mode": "booking",
            "understood": False
        })
    
    def _handle_details_collection_ultimate(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """
        ✨ ULTIMATE details collection using FieldExtractor
        Maintains ALL existing logic while leveraging enhanced extraction
        """
        msg_lower = message.lower().strip()
        
        # ========================
        # PHASE 1: Check for cancellation
        # ========================
        if any(word in msg_lower for word in ['cancel', 'stop', 'quit', 'exit', 'abort', 'nevermind']):
            intent.reset()
            logger.info("✅ User cancelled booking")
            return (BookingState.GREETING.value, intent, {
                "action": "cancelled",
                "message": "✅ Booking cancelled. How else can I help?",
                "mode": "chat",
                "understood": True
            })
        
        # ========================
        # PHASE 2: Check if we're in email selection mode
        # ========================
        if hasattr(intent, 'metadata') and 'email_options' in intent.metadata:
            email_options = intent.metadata['email_options']
            if email_options.get('waiting_for_selection', False):
                logger.info(f"📧 Processing email selection response: {message}")
                return self._handle_email_selection(message, intent, email_options, language)
        
        # ========================
        # PHASE 3: Check for completion intent
        # ========================
        if self.validators.is_completion_intent(msg_lower):
            logger.info(f"ℹ️ User wants to complete: {message}")
            if intent.is_complete():
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "ask_confirmation",
                    "message": self.prompts.get_confirmation_prompt(intent, language),
                    "mode": "booking",
                    "understood": True
                })
            else:
                missing = intent.missing_fields()
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "ask_details",
                    "message": self._get_enhanced_summary_prompt(intent, missing, language),
                    "missing": missing,
                    "mode": "booking",
                    "understood": True
                })
        
        # ========================
        # PHASE 4: Check if it's clearly a question
        # ========================
        if self._is_clear_question_enhanced(msg_lower, message):
            logger.info(f"❓ Detected clear question: {message[:50]}")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "off_topic_question",
                "message": "",  # Knowledge base handles
                "mode": "booking",
                "understood": False
            })
        
        # ========================
        # ✨ PHASE 5: Use FieldExtractor with comprehensive extraction
        # ========================
        logger.info("🚀 Using FieldExtractor for comprehensive extraction")
        
        # Build enhanced context
        enhanced_context = {
            'conversation_history': history,
            'language': language,
            'service': intent.service,
            'package': intent.package
        }
        
        # Use FieldExtractor.extract() method
        extraction_result = self.field_extractors.extract(
            message, 
            intent, 
            enhanced_context
        )
        
        extracted_fields = extraction_result.get('extracted', {})
        extraction_details = extraction_result.get('details', {})
        inferred_fields = extraction_result.get('inferred', {})
        cross_validated = extraction_result.get('cross_validated', {})
        warnings = extraction_result.get('warnings', [])
        suggestions = extraction_result.get('suggestions', [])
        
        logger.info(f"✅ FieldExtractor Results:")
        logger.info(f"   - Extracted: {list(extracted_fields.keys())}")
        logger.info(f"   - Inferred: {list(inferred_fields.keys())}")
        logger.info(f"   - Confidence: {extraction_result.get('confidence')}")
        logger.info(f"   - Status: {extraction_result.get('status')}")
        
        # ========================
        # PHASE 6: Check for email options
        # ========================
        if "email_options" in extracted_fields:
            emails = extracted_fields["email_options"]
            intent.metadata['email_options'] = {
                'emails': emails,
                'waiting_for_selection': True,
                'original_message': message[:100]
            }
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "email_selection",
                "message": self.prompts.get_email_selection_prompt(emails, language),
                "mode": "booking",
                "understood": False
            })
        
        # ========================
        # PHASE 7: Process extracted fields with enhanced validation
        # ========================
        collected = {}
        updated = False
        validation_errors = []
        
        for field_name, value in extracted_fields.items():
            
            # Validate and update based on field type
            if field_name == "phone" and value:
                result = self._process_phone_field(intent, value, collected, cross_validated, extraction_details.get('phone', {}))
                updated = updated or result['updated']
                if result.get('error'):
                    validation_errors.append(result['error'])
                    
            elif field_name == "email" and value:
                result = self._process_email_field(intent, value, collected, cross_validated, extraction_details.get('email', {}))
                updated = updated or result['updated']
                if result.get('error'):
                    validation_errors.append(result['error'])
                    
            elif field_name == "date" and value:
                result = self._process_date_field(intent, value, collected, extraction_details.get('date', {}))
                updated = updated or result['updated']
                if result.get('error'):
                    validation_errors.append(result['error'])
                    
            elif field_name == "name" and value:
                intent.name = value
                collected["name"] = value
                updated = True
                logger.info(f"✅ Collected name: {value}")
                
            elif field_name == "address" and value:
                if self.address_validator.is_valid_address(value):
                    intent.address = value
                    collected["address"] = value
                    updated = True
                    logger.info(f"✅ Collected address: {value}")
                else:
                    logger.warning(f"⚠️ Invalid address: {value}")
                    
            elif field_name == "pincode" and value:
                country = intent.service_country or extracted_fields.get('country') or 'India'
                pincode_validation = self.pincode_validator.validate(value, country)
                
                if pincode_validation['valid']:
                    intent.pincode = value
                    collected["pincode"] = value
                    updated = True
                    logger.info(f"✅ Collected pincode: {value}")
                else:
                    validation_errors.append(f"Pincode: {pincode_validation.get('error')}")
                    
            elif field_name == "country" and value:
                intent.service_country = value
                collected["service_country"] = value
                updated = True
                logger.info(f"✅ Collected country: {value}")
        
        # Log warnings from cross-validation
        for warning in warnings:
            logger.warning(f"⚠️ {warning}")
        
        # ========================
        # PHASE 8: Handle updates
        # ========================
        if updated:
            # Check completion
            if intent.is_complete():
                logger.info(f"✅ All details collected")
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "ask_confirmation",
                    "message": self.prompts.get_confirmation_prompt(intent, language),
                    "collected": collected,
                    "mode": "booking",
                    "understood": True
                })
            
            # Still missing fields
            missing = intent.missing_fields()
            logger.info(f"ℹ️ Still missing: {missing}")
            
            response_message = self._get_enhanced_summary_prompt(intent, missing, language)
            
            # Add validation errors if any
            if validation_errors:
                error_msg = "\n\n⚠️ **Please note:**\n" + "\n".join([f"• {err}" for err in validation_errors])
                response_message += error_msg
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": response_message,
                "collected": collected,
                "missing": missing,
                "mode": "booking",
                "understood": True,
                "extraction_confidence": extraction_result.get('confidence'),
                "validation_errors": validation_errors,
                "suggestions": suggestions
            })
        
        # ========================
        # PHASE 9: User says they already provided info
        # ========================
        if any(phrase in msg_lower for phrase in ['already gave', 'already told', 'i gave', 'i told', 'i provided']):
            missing = intent.missing_fields()
            logger.info(f"ℹ️ User says already provided. Missing: {missing}")
            
            if not missing:
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "ask_confirmation",
                    "message": self.prompts.get_confirmation_prompt(intent, language),
                    "mode": "booking",
                    "understood": True
                })
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "clarify_details",
                "message": self._get_enhanced_summary_prompt(intent, missing, language),
                "missing": missing,
                "mode": "booking",
                "understood": True
            })
        
        # ========================
        # PHASE 10: Not understood - show summary
        # ========================
        missing = intent.missing_fields()
        if missing:
            logger.info(f"ℹ️ Not understood. Missing: {missing}")
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": self._get_enhanced_summary_prompt(intent, missing, language),
                "missing": missing,
                "mode": "booking",
                "understood": False,
                "extraction_status": extraction_result.get('status')
            })
        
        # All fields collected
        return (BookingState.CONFIRMING.value, intent, {
            "action": "ask_confirmation",
            "message": self.prompts.get_confirmation_prompt(intent, language),
            "mode": "booking",
            "understood": True
        })
    
    def _process_phone_field(
        self,
        intent: BookingIntent,
        phone_data: Any,
        collected: Dict,
        cross_validated: Dict,
        metadata: Dict
    ) -> Dict:
        """Process and validate phone field
        - STORE: compact E.164 (+918149992239)
        - DISPLAY: formatted (+91 81499 92239)
        """
        try:
            # -----------------------------
            # 1. Extract compact phone
            # -----------------------------
            if isinstance(phone_data, dict):
                # ALWAYS prefer full_phone (compact)
                phone_compact = phone_data.get("full_phone") or phone_data.get("phone", "")
                phone_display = phone_data.get("formatted") or phone_compact
            else:
                phone_compact = str(phone_data)
                phone_display = phone_compact

            if not phone_compact:
                return {'updated': False, 'error': 'Phone number missing'}

            # -----------------------------
            # 2. Validate compact phone
            # -----------------------------
            validation = self.phone_validator.validate_with_country_code(phone_compact)

            if not validation.get("valid"):
                error_msg = validation.get("error", "Invalid phone")
                logger.warning(f"⚠️ Phone validation failed: {error_msg}")
                return {'updated': False, 'error': f"Phone: {error_msg}"}

            # -----------------------------
            # 3. STORE compact (E.164)
            # -----------------------------
            intent.phone = phone_compact  # ✅ CRITICAL FIX

            # -----------------------------
            # 4. DISPLAY formatted
            # -----------------------------
            collected["phone"] = phone_display

            # -----------------------------
            # 5. Set country from validation
            # -----------------------------
            country = validation.get("country")
            if country:
                intent.phone_country = country

                if not intent.service_country:
                    intent.service_country = country
                    collected["service_country"] = country
                    logger.info(f"✅ Auto-set country from phone: {country}")

            logger.info(f"✅ Collected phone (display): {phone_display}")
            logger.info(f"📦 Stored phone (compact): {intent.phone}")

            return {'updated': True, 'error': None}

        except Exception as e:
            logger.error(f"❌ Phone processing error: {e}", exc_info=True)
            return {'updated': False, 'error': 'Phone validation failed'}

    
    def _process_email_field(self, intent: BookingIntent, email: str, 
                            collected: Dict, cross_validated: Dict, metadata: Dict) -> Dict:
        """Process and validate email field"""
        try:
            validation = self.email_validator.validate(email)
            
            if validation['valid']:
                intent.email = email.lower()
                collected["email"] = email.lower()
                logger.info(f"✅ Collected email: {email}")
                
                if validation.get('warning'):
                    logger.warning(f"⚠️ Email warning: {validation['warning']}")
                
                return {'updated': True, 'error': None}
            else:
                error_msg = validation.get('error', 'Invalid email')
                logger.warning(f"⚠️ Email validation failed: {error_msg}")
                return {'updated': False, 'error': f"Email: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ Email processing error: {e}")
            return {'updated': False, 'error': 'Email validation failed'}
    
    def _process_date_field(self, intent: BookingIntent, date: str, 
                           collected: Dict, metadata: Dict) -> Dict:
        """Process and validate date field"""
        try:
            validation = self.date_validator.validate(date)
            
            if validation['valid']:
                intent.date = date
                collected["date"] = date
                
                # Store metadata if needs year
                if metadata.get('needs_year'):
                    if not hasattr(intent, 'metadata'):
                        intent.metadata = {}
                    intent.metadata['date_info'] = metadata
                
                logger.info(f"✅ Collected date: {date}")
                
                if validation.get('warning'):
                    logger.warning(f"⚠️ Date warning: {validation['warning']}")
                
                return {'updated': True, 'error': None}
            else:
                error_msg = validation.get('error', 'Invalid date')
                logger.warning(f"⚠️ Date validation failed: {error_msg}")
                return {'updated': False, 'error': f"Date: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ Date processing error: {e}")
            return {'updated': False, 'error': 'Date validation failed'}
    
    def _handle_email_selection(self, message: str, intent: BookingIntent, 
                               email_options: Dict, language: str) -> Tuple[str, BookingIntent, Dict]:
        """Handle email selection from multiple options"""
        emails = email_options.get('emails', [])
        
        # Check for numeric selection
        num_match = re.search(r'\b([1-9])\b', message)
        if num_match:
            idx = int(num_match.group(1)) - 1
            if 0 <= idx < len(emails):
                intent.email = emails[idx]
                intent.metadata.pop('email_options', None)
                logger.info(f"✅ Email selected: {emails[idx]}")
                
                if intent.is_complete():
                    return (BookingState.CONFIRMING.value, intent, {
                        "action": "ask_confirmation",
                        "message": self.prompts.get_confirmation_prompt(intent, language),
                        "mode": "booking",
                        "understood": True
                    })
                
                missing = intent.missing_fields()
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "ask_details",
                    "message": self._get_enhanced_summary_prompt(intent, missing, language),
                    "missing": missing,
                    "mode": "booking",
                    "understood": True
                })
        
        # Check for direct email
        email_pattern = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
        email_match = re.search(email_pattern, message, re.IGNORECASE)
        
        if email_match:
            intent.email = email_match.group(0).lower()
            intent.metadata.pop('email_options', None)
            logger.info(f"✅ Email selected directly: {intent.email}")
            
            if intent.is_complete():
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "ask_confirmation",
                    "message": self.prompts.get_confirmation_prompt(intent, language),
                    "mode": "booking",
                    "understood": True
                })
            
            missing = intent.missing_fields()
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": self._get_enhanced_summary_prompt(intent, missing, language),
                "missing": missing,
                "mode": "booking",
                "understood": True
            })
        
        # Not understood
        return (BookingState.COLLECTING_DETAILS.value, intent, {
            "action": "email_selection",
            "message": self.prompts.get_email_selection_prompt(emails, language),
            "mode": "booking",
            "understood": False
        })
    
    def _is_clear_question_enhanced(self, msg_lower: str, original_message: str) -> bool:
        """Strict question detection to avoid false positives"""
        # Very clear question starters
        clear_question_starters = [
            'what is', 'how to', 'can you', 'could you', 'would you',
            'do you', 'are you', 'is there', 'are there', 'when is',
            'where is', 'who is', 'why is', 'how much', 'how many'
        ]
        
        # Check for question mark but exclude simple patterns
        if '?' in original_message:
            clean_text = original_message.replace('?', '').strip()
            words = clean_text.split()
            
            # Exclude simple patterns (dates, names)
            if len(words) == 1:
                return False
            elif len(words) == 2 and any(word.isdigit() for word in words):
                return False
            
            return True
        
        # Check for clear question starters
        for starter in clear_question_starters:
            if msg_lower.startswith(starter):
                return True
        
        return False
    
    def _get_enhanced_summary_prompt(self, intent: BookingIntent, missing_fields: List[str], language: str) -> str:
        """Enhanced prompt showing collected info and asking for missing fields"""
        # Check for email options first
        if hasattr(intent, 'metadata') and 'email_options' in intent.metadata:
            emails = intent.metadata['email_options']['emails']
            return self.prompts.get_email_selection_prompt(emails, language)
        
        # Use the prompt generator
        return self.prompts.get_collected_summary_prompt(intent, missing_fields, language)
    
    def _handle_confirmation(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle confirmation state"""
        msg_lower = message.lower().strip()
        
        # Check if it's a question - let knowledge base handle
        if self.validators.is_general_question(msg_lower):
            return (BookingState.CONFIRMING.value, intent, {
                "action": "question_during_confirmation",
                "message": "",  # Knowledge base handles
                "mode": "booking",
                "understood": False
            })
        
        # Check for confirmation
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
        
        # Check for rejection/change
        if self.validators.is_rejection(msg_lower):
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "change_details",
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
        
        # Check if it's a question - let knowledge base handle
        if self.validators.is_general_question(msg_lower):
            return (BookingState.OTP_SENT.value, intent, {
                "action": "question_during_otp",
                "message": "",  # Knowledge base handles
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
    
    def _handle_year_response(self, message: str, intent: BookingIntent, language: str) -> Tuple[str, BookingIntent, Dict]:
        """Handle when user provides year after partial date"""
        year = self.extractors.extract_year_from_message(message)
        
        if year:
            date_info = intent.metadata.get('date_info', {}) if hasattr(intent, 'metadata') and intent.metadata else {}
            
            if date_info.get('needs_year', False) and intent.date:
                try:
                    old_date = datetime.strptime(intent.date, '%Y-%m-%d')
                    new_date = old_date.replace(year=year)
                    intent.date = new_date.strftime('%Y-%m-%d')
                    
                    # Update metadata
                    intent.metadata['date_info']['needs_year'] = False
                    intent.metadata['date_info']['user_provided_year'] = year
                    
                    missing = intent.missing_fields()
                    
                    return (BookingState.COLLECTING_DETAILS.value, intent, {
                        "action": "year_provided",
                        "message": f"✅ Updated year to {year}. {self._get_enhanced_summary_prompt(intent, missing, language)}",
                        "mode": "booking",
                        "understood": True
                    })
                except Exception as e:
                    logger.error(f"Error updating year: {e}")
        
        # Ask for year again
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