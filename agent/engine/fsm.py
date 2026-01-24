# agent/engine/fsm.py
"""
Finite State Machine Engine - FIXED with proper state transitions
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
            logger.info(f"🎯 FSM Processing: {state_enum.value} | Message: '{message[:50]}...'")
            
            # Route to appropriate handler
            handlers = {
                BookingState.GREETING: self._handle_greeting,
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
        """Handle greeting state"""
        msg_lower = message.lower().strip()
        
        # Check if user wants to book
        if self._is_booking_intent(msg_lower):
            self.last_shown_list = "services"
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self._get_service_prompt(language),
                "mode": "booking",
                "understood": True
            })
        
        # Check if it's a general question
        if self._is_general_question(msg_lower):
            return (BookingState.GREETING.value, intent, {
                "action": "general_question",
                "message": "",  # Will be handled by knowledge base
                "mode": "chat",
                "understood": False  # Let knowledge base handle
            })
        
        # Default: stay in greeting
        return (BookingState.GREETING.value, intent, {
            "action": "greeting",
            "message": self._get_greeting_message(language),
            "mode": "chat",
            "understood": True
        })
    
    def _handle_service_selection(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle service selection state"""
        msg_lower = message.lower().strip()
        
        # Check if it's a question
        if self._is_question_general(msg_lower):
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
        if self._is_question_general(msg_lower):
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
        """Handle details collection state - FIXED to show collected info and ask for remaining"""
        msg_lower = message.lower().strip()
        
        # Check if it's a question (like "what is your instagram link?")
        if self._is_question_general(msg_lower):
            logger.info(f"ℹ️ Detected question during details: {message[:50]}")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "question_during_details",
                "message": "",  # Will be handled by knowledge base
                "mode": "booking",
                "understood": False  # Let knowledge base handle
            })
        
        # Check for completion intent
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
        
        # Try to extract fields from the message
        extracted = self._extract_all_fields(message, intent, history)
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
                    intent.address = value
                    collected["address"] = intent.address
                    updated = True
                    logger.info(f"✅ Collected address: {intent.address}")
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
        
        # If no fields extracted and it's not a question, check if it's a complaint
        # like "i already gave you my name"
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
        
        # Not understood - show what we have and what we need
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
        
        # All fields collected but not confirmed
        return (BookingState.CONFIRMING.value, intent, {
            "action": "ask_confirmation",
            "message": self._get_confirmation_prompt(intent, language),
            "mode": "booking",
            "understood": True
        })

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
        if self._is_question_general(msg_lower):
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
        if self._is_question_general(msg_lower):
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
        """Check if message is a general question"""
        question_words = ['what', 'which', 'how', 'why', 'when', 'where', 'who', 
                         'tell me', 'show me', 'list', 'can you', 'could you',
                         'what is', 'what are', 'how to', 'how do', 'how can']
        msg_lower = message.lower()
        return any(qw in msg_lower for qw in question_words)
    
    def _is_question_general(self, message: str) -> bool:
        """Check if message is a general question"""
        # First check if it's a single number (likely package selection)
        if re.match(r'^\s*\d+\s*$', message):
            return False
        
        question_words = ['what', 'which', 'how', 'why', 'when', 'where', 'who',
                         'tell me', 'show me', 'list', 'can you', 'could you',
                         'what is', 'what are', 'how to', 'how do', 'how can',
                         'instagram', 'facebook', 'social media', 'contact', 'email',
                         'phone', 'number', 'link', 'website', 'youtube', 'details',
                         'information', 'about', 'price', 'cost', 'charge', 'hi', 'hello']
        msg_lower = message.lower()
        return any(qw in msg_lower for qw in question_words)
    
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
        
        # Extract name (only if not already collected)
        if not intent.name:
            name_data = self.name_extractor.extract(message)
            if name_data and name_data.get("name"):
                extracted["name"] = name_data.get("name")
        
        # Extract phone (only if not already collected)
        if not intent.phone:
            phone_data = self.phone_extractor.extract(message)
            if phone_data:
                extracted["phone"] = phone_data
        
        # Extract email (only if not already collected)
        if not intent.email:
            email_data = self.email_extractor.extract(message)
            if email_data:
                extracted["email"] = email_data.get("email")
        
        # Extract address (only if not already collected)
        if not intent.address:
            address_data = self.address_extractor.extract(message)
            if address_data:
                extracted["address"] = address_data.get("address")
        
        # Extract pincode (only if not already collected)
        if not intent.pincode:
            pincode_data = self.pincode_extractor.extract(message)
            if pincode_data:
                extracted["pincode"] = pincode_data.get("pincode")
        
        # Extract country (only if not already collected)
        if not intent.service_country:
            country_data = self.country_extractor.extract(message)
            if country_data:
                extracted["country"] = country_data.get("country")
        
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