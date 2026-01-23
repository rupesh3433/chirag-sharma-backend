"""
FSM Engine - STRICT Master System Prompt Compliance
All behavioral rules from prompt implemented
"""

from enum import Enum
from typing import Optional, Dict, Any, Tuple, List
import re
from datetime import datetime, timedelta
import logging

from agent_models import BookingIntent
from agent_prompts import SERVICES

logger = logging.getLogger(__name__)

class BookingState(Enum):
    """FSM States"""
    GREETING = "greeting"
    INFO_MODE = "info_mode"
    SELECTING_SERVICE = "selecting_service"
    SELECTING_PACKAGE = "selecting_package"
    COLLECTING_DETAILS = "collecting_details"  # SINGLE STATE for all personal details
    CONFIRMING = "confirming"
    OTP_SENT = "otp_sent"
    COMPLETED = "completed"

class BookingFSM:
    """FSM following ALL Master System Prompt rules"""
    
    def __init__(self):
        self.services = list(SERVICES.keys())
        self.last_shown_list = None
        self.last_shown_service = None
    
    def process_message(self, message: str, current_state: str, intent: BookingIntent, 
                       language: str = "en", conversation_history: List[Dict] = None) -> Tuple[str, BookingIntent, Dict[str, Any]]:
        """Process with STRICT prompt compliance"""
        
        msg_clean = message.strip()
        state_enum = BookingState(current_state)
        
        logger.info(f"🎯 FSM: {state_enum.value} | List: {self.last_shown_list} | '{msg_clean[:50]}'")
        
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
            return handler(msg_clean, intent, language, conversation_history or [])
        
        return (BookingState.GREETING.value, intent, {"error": "Invalid state"})
    
    def _handle_greeting(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """RULE: Info mode vs Booking mode distinction - IMPROVED"""
        
        # FIRST: Check if this is a booking initiation
        if self._is_booking_intent(message, history):
            # Show services immediately with prices
            self.last_shown_list = "services"
            self.last_shown_service = None
            
            # Get service prompt WITH PRICES
            service_prompt = self._get_service_prompt_with_prices(language)
            
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": service_prompt,
                "mode": "booking",
                "chat_mode": "agent"  # FORCE agent mode
            })
        
        # SECOND: Check if it's an info query
        if self._is_info_query(message):
            return (BookingState.INFO_MODE.value, intent, {
                "action": "provide_info", 
                "query": message, 
                "message": None,
                "mode": "info"
            })
        
        # Default: stay in greeting for general chat
        return (BookingState.GREETING.value, intent, {
            "action": "general_chat", 
            "message": None,
            "mode": "chat"
        })
    

    def _get_service_prompt_with_prices(self, language: str) -> str:
        """Service prompt WITH PRICES - using your existing SERVICES"""
        
        if language == "en":
            prompt = "🎯 **BOOKING MODE ACTIVATED**\n\n"
            prompt += "I'll help you book makeup services!\n\n"
            prompt += "**Please choose which service you'd like to book:**\n\n"
            
            # Use your existing SERVICES dictionary
            for i, (service_name, service_data) in enumerate(SERVICES.items(), 1):
                packages = service_data.get("packages", {})
                description = service_data.get("description", "")
                
                # Get price range from packages
                price_range = ""
                if packages:
                    # Get all package prices
                    price_values = []
                    for pkg_name, price_str in packages.items():
                        # Extract numeric price from string like "₹99,999"
                        price_match = re.search(r'₹([\d,]+)', price_str)
                        if price_match:
                            price_num = int(price_match.group(1).replace(',', ''))
                            price_values.append(price_num)
                    
                    if price_values:
                        min_price = min(price_values)
                        max_price = max(price_values)
                        if min_price == max_price:
                            price_range = f"₹{min_price:,}"
                        else:
                            price_range = f"₹{min_price:,} - ₹{max_price:,}"
                
                prompt += f"{i}. **{service_name}**\n"
                if price_range:
                    prompt += f"   Price range: {price_range}\n"
                if description:
                    prompt += f"   {description}\n"
                prompt += "\n"
            
            prompt += "**Type the number (1-4) or name of the service you want to book!**\n"
            prompt += "Example: '1' or 'Bridal Makeup Services'"
            
            return prompt
        
        # For other languages, use the simple prompt for now
        return self._get_service_prompt(language)


    def _handle_info_mode(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """RULE: Info mode - answer with soft CTA"""
        
        if self._is_booking_intent(message, history):
            service = self._extract_service_contextual(message, history)
            
            if service:
                intent.service = service
                self.last_shown_service = service
                self.last_shown_list = "packages"
                
                return (BookingState.SELECTING_PACKAGE.value, intent, {
                    "action": "ask_package",
                    "message": self._get_package_prompt(service, language),
                    "collected": {"Service": service},
                    "mode": "booking"
                })
            else:
                self.last_shown_list = "services"
                return (BookingState.SELECTING_SERVICE.value, intent, {
                    "action": "ask_service",
                    "message": self._get_service_prompt(language),
                    "mode": "booking"
                })
        
        # Stay in info mode
        return (BookingState.INFO_MODE.value, intent, {
            "action": "provide_info", 
            "query": message, 
            "message": None,
            "mode": "info"
        })
    
    def _handle_service_selection(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """RULE: Context-aware numeric selection"""
        
        # Check if user is referring to last shown list
        service = self._extract_service_contextual(message, history)
        
        if service:
            intent.service = service
            self.last_shown_service = service
            self.last_shown_list = "packages"
            
            return (BookingState.SELECTING_PACKAGE.value, intent, {
                "action": "ask_package",
                "message": self._get_package_prompt(service, language),
                "collected": {"Service": service},
                "mode": "booking"
            })
        
        # Check if user says "I already gave this" or similar
        if self._is_already_given_response(message):
            # Check history for service
            service_from_history = self._check_history_for_field("service", history)
            if service_from_history:
                intent.service = service_from_history
                self.last_shown_service = service_from_history
                self.last_shown_list = "packages"
                
                return (BookingState.SELECTING_PACKAGE.value, intent, {
                    "action": "ask_package",
                    "message": f"✅ Found it! You mentioned {service_from_history}.\n\n{self._get_package_prompt(service_from_history, language)}",
                    "collected": {"Service": service_from_history},
                    "mode": "booking"
                })
        
        # Invalid selection
        return (BookingState.SELECTING_SERVICE.value, intent, {
            "action": "retry",
            "message": f"❌ Please select from the list:\n{self._get_service_prompt(language)}",
            "mode": "booking"
        })
    
    def _handle_package_selection(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """RULE: NEVER ask 'Which service?' again"""
        
        # CRITICAL: If somehow service is missing, restart service selection
        if not intent.service:
            self.last_shown_list = "services"
            return (BookingState.SELECTING_SERVICE.value, intent, {
                "action": "ask_service",
                "message": self._get_service_prompt(language),
                "mode": "booking"
            })
        
        package = self._extract_package(message, intent.service, self.last_shown_list)
        
        if package:
            intent.package = package
            self.last_shown_list = None
            
            # Move to DETAILS collection (single state for all personal data)
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": self._get_details_prompt(intent, language),
                "collected": {"Package": package},
                "mode": "booking"
            })
        
        # Check if user says "I already gave this" or similar
        if self._is_already_given_response(message):
            # Check history for package
            package_from_history = self._check_history_for_field("package", history)
            if package_from_history:
                intent.package = package_from_history
                self.last_shown_list = None
                
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "ask_details",
                    "message": f"✅ Found it! You mentioned {package_from_history}.\n\n{self._get_details_prompt(intent, language)}",
                    "collected": {"Package": package_from_history},
                    "mode": "booking"
                })
        
        # Invalid package selection
        return (BookingState.SELECTING_PACKAGE.value, intent, {
            "action": "retry",
            "message": f"❌ Please select from:\n{self._get_package_prompt(intent.service, language)}",
            "mode": "booking"
        })
    
    def _handle_details_collection(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """SINGLE STATE for collecting ALL personal details - IMPROVED for frustrated users"""
        
        # FIRST: Check if user is frustrated about date/any field
        msg_lower = message.lower()
        
        # Quick frustration check
        frustration_words = ['again', 'seriously', 'ugh', 'come on', 'really', 'annoying', 
                            'frustrating', 'ridiculous', 'whats wrong', "what's wrong", 
                            'hello?', 'hey', 'are you there', 'anyone', 'this is crazy',
                            'unbelievable', 'omg', 'oh my god', 'god', 'jeez', 'jesus',
                            'what the hell', 'what the fuck', 'wtf', 'damn', 'dammit']
        
        is_frustrated = any(word in msg_lower for word in frustration_words)
        
        if is_frustrated:
            logger.warning(f"😠 User seems frustrated: '{message}'")
            
            # Try to recover ALL missing fields from history
            all_recovered = {}
            
            # Check for date specifically first (most common frustration)
            date_recovered, found_date = self._handle_already_provided_date(message, intent, history)
            if date_recovered and found_date:
                intent.date = found_date
                all_recovered["Date"] = found_date
                logger.info(f"🔄 Recovered date from frustration: {found_date}")
            
            # Check history for other missing fields too
            missing_fields = intent.missing_fields()
            if missing_fields and len(missing_fields) > 0:
                for field in missing_fields[:3]:  # Check first 3 missing fields
                    # Map field names
                    field_map = {
                        "your name": "name",
                        "email address": "email", 
                        "phone number with country code": "phone",
                        "service address": "address",
                        "PIN/postal code": "pincode",
                        "preferred date": "date"
                    }
                    
                    actual_field = field_map.get(field)
                    if actual_field:
                        value = self._check_history_for_field(actual_field, history)
                        if value:
                            if actual_field == "name" and not intent.name:
                                intent.name = value
                                all_recovered["Name"] = value
                            elif actual_field == "email" and not intent.email:
                                intent.email = value
                                all_recovered["Email"] = value
                            elif actual_field == "phone" and not self._is_phone_valid(intent.phone):
                                intent.phone = value
                                all_recovered["Phone"] = value
                            elif actual_field == "address" and not intent.address:
                                intent.address = value
                                all_recovered["Address"] = value[:50] + "..." if len(value) > 50 else value
                            elif actual_field == "pincode" and not intent.pincode:
                                intent.pincode = value
                                all_recovered["PIN Code"] = value
                            elif actual_field == "date" and not intent.date and not date_recovered:
                                intent.date = value
                                all_recovered["Date"] = value
            
            # If we recovered anything, acknowledge it
            if all_recovered:
                # Build acknowledgment message
                ack_parts = ["✅ I understand you're frustrated! Let me check what I found..."]
                for field, value in all_recovered.items():
                    ack_parts.append(f"• {field}: {value}")
                
                # Check if all fields are now complete
                if intent.is_complete():
                    return (BookingState.CONFIRMING.value, intent, {
                        "action": "confirm",
                        "message": f"{' '.join(ack_parts)}\n\n🎯 Perfect! I have everything now.\n\n{self._get_confirmation_prompt(intent, language)}",
                        "collected": all_recovered,
                        "mode": "booking"
                    })
                else:
                    missing = intent.missing_fields()
                    missing = self._reorder_missing_fields(missing)
                    
                    # Create a more empathetic prompt
                    if len(missing) == 1:
                        prompt = f"I just need one more thing:\n• {missing[0]}"
                    elif len(missing) <= 3:
                        prompt = f"I still need:\n{chr(10).join(f'• {field}' for field in missing)}"
                    else:
                        prompt = f"I need a few more details to complete your booking."
                    
                    return (BookingState.COLLECTING_DETAILS.value, intent, {
                        "action": "ask_details",
                        "message": f"{' '.join(ack_parts)}\n\n{prompt}\n\n💡 **Tip:** You can provide everything at once to save time!",
                        "collected": all_recovered,
                        "missing": missing,
                        "mode": "booking"
                    })
        
        # Check if user says "I already provided date" or similar
        already_provided, found_date = self._handle_already_provided_date(message, intent, history)
        if already_provided and found_date:
            logger.info(f"🔄 Setting date from recovery: {found_date}")
            intent.date = found_date
            
            # Check if all fields are now complete
            if intent.is_complete():
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "confirm",
                    "message": self._get_confirmation_prompt(intent, language),
                    "collected": {"Date (recovered)": found_date},
                    "mode": "booking"
                })
            else:
                # Still missing other fields
                missing = intent.missing_fields()
                missing = self._reorder_missing_fields(missing)
                prompt = self._get_missing_fields_prompt(intent, language, {"Date": found_date}, missing)
                
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "ask_details",
                    "message": f"✅ Found your date: {found_date}\n\n{prompt}",
                    "collected": {"Date": found_date},
                    "missing": missing,
                    "mode": "booking"
                })
        
        # Check if user says "I already gave this" for any field
        if self._is_already_given_response(message):
            logger.info("🔍 User says they already provided information")
            
            # Check history for all missing fields
            recovered_fields = self._recover_fields_from_history(intent, history)
            if recovered_fields:
                logger.info(f"🔄 Recovered fields from history: {list(recovered_fields.keys())}")
                
                # Update intent with recovered fields
                for field, value in recovered_fields.items():
                    if field == "name" and not intent.name:
                        intent.name = value
                    elif field == "phone" and not self._is_phone_valid(intent.phone):
                        intent.phone = value.get("phone") if isinstance(value, dict) else value
                        if isinstance(value, dict) and "country" in value:
                            intent.phone_country = value["country"]
                    elif field == "email" and not intent.email:
                        intent.email = value
                    elif field == "date" and not intent.date:
                        intent.date = value
                    elif field == "address" and not intent.address:
                        intent.address = value
                    elif field == "pincode" and not intent.pincode:
                        intent.pincode = value
                
                # Create acknowledgment
                ack_fields = {}
                for field, value in recovered_fields.items():
                    if isinstance(value, dict) and "phone" in value:
                        ack_fields["Phone"] = value["phone"]
                    elif field == "name":
                        ack_fields["Name"] = value
                    elif field == "email":
                        ack_fields["Email"] = value
                    elif field == "date":
                        ack_fields["Date"] = value
                    elif field == "address":
                        ack_fields["Address"] = value[:50] + "..." if len(value) > 50 else value
                    elif field == "pincode":
                        ack_fields["PIN Code"] = value
                
                # Re-check if all fields are complete
                if intent.is_complete():
                    ack_message = "✅ Found all your information in our conversation!"
                    for field, value in ack_fields.items():
                        ack_message += f"\n• {field}: {value}"
                    
                    return (BookingState.CONFIRMING.value, intent, {
                        "action": "confirm",
                        "message": f"{ack_message}\n\n{self._get_confirmation_prompt(intent, language)}",
                        "collected": ack_fields,
                        "mode": "booking"
                    })
        
        # Extract ALL fields from the message
        extracted_fields = self._extract_all_fields(message, intent, history)
        
        # Special handling: If date was extracted but not marked in extracted_fields
        if intent.date and "Date" not in extracted_fields:
            extracted_fields["Date"] = intent.date
        
        # Check if all required fields are now complete
        if intent.is_complete():
            # All fields collected, move to confirmation
            return (BookingState.CONFIRMING.value, intent, {
                "action": "confirm",
                "message": self._get_confirmation_prompt(intent, language),
                "collected": extracted_fields,
                "mode": "booking"
            })
        
        # Still missing fields
        missing = intent.missing_fields()
        
        # Debug: Log what's missing
        logger.info(f"🔍 Missing fields: {missing}")
        logger.info(f"🔍 Extracted fields: {extracted_fields}")
        logger.info(f"🔍 Intent date: {intent.date}")
        
        # Reorder missing fields: address before pincode
        missing = self._reorder_missing_fields(missing)
        
        # Special case: If date is missing but we have it in intent (extraction issue)
        if "preferred date" in missing and intent.date:
            # Date exists in intent but system thinks it's missing
            missing.remove("preferred date")
            if "Date" not in extracted_fields:
                extracted_fields["Date"] = intent.date
        
        # Special case: If user provides multiple details but some are still missing
        if extracted_fields and len(extracted_fields) >= 2 and missing:
            # User provided multiple things but not everything
            ack_parts = ["✅ Great! I've got:"]
            for field, value in extracted_fields.items():
                ack_parts.append(f"• {field}: {value}")
            
            if len(missing) == 1:
                prompt = f"\nI just need one more thing:\n• {missing[0]}"
            else:
                prompt = f"\nI still need:\n{chr(10).join(f'• {field}' for field in missing)}"
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": "\n".join(ack_parts) + prompt + "\n\n💡 You can provide everything at once!",
                "collected": extracted_fields,
                "missing": missing,
                "mode": "booking"
            })
        
        # Build prompt asking for missing fields
        prompt = self._get_missing_fields_prompt(intent, language, extracted_fields, missing)
        
        return (BookingState.COLLECTING_DETAILS.value, intent, {
            "action": "ask_details",
            "message": prompt,
            "collected": extracted_fields,
            "missing": missing,
            "mode": "booking"
        })
    
    def _handle_confirmation(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle confirmation"""
        
        msg_lower = message.lower()
        
        # Check if we need to infer country first
        if not intent.service_country:
            country = self._extract_country(message)
            if country:
                intent.service_country = country
                extracted = {"Country": country}
                
                # Now confirm everything
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "confirm",
                    "message": self._get_confirmation_prompt(intent, language),
                    "collected": extracted,
                    "mode": "booking"
                })
            else:
                # Still need country
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "ask_country",
                    "message": "🌍 Please specify: India, Nepal, Pakistan, Bangladesh, or Dubai?",
                    "mode": "booking"
                })
        
        # User confirms
        if any(word in msg_lower for word in ['yes', 'confirm', 'correct', 'proceed', 'ok', 'yeah', 'yep', 'book', '✅']):
            return (BookingState.OTP_SENT.value, intent, {
                "action": "send_otp", 
                "message": None,
                "mode": "booking"
            })
        
        # User wants to cancel/change
        if any(word in msg_lower for word in ['no', 'cancel', 'wrong', 'incorrect', 'change', 'restart']):
            # Reset and start over
            new_intent = BookingIntent()
            self.last_shown_list = "services"
            self.last_shown_service = None
            
            return (BookingState.SELECTING_SERVICE.value, new_intent, {
                "action": "restart",
                "message": "🔄 No problem! Let's start over.\n\nWhich service?\n\n1. Bridal Makeup\n2. Party Makeup\n3. Engagement & Pre-Wedding\n4. Henna/Mehendi",
                "mode": "booking"
            })
        
        # Check if user is asking about date ambiguity
        date_response = self._check_date_ambiguity_response(message, intent.date)
        if date_response:
            return (BookingState.CONFIRMING.value, intent, {
                "action": "retry",
                "message": date_response,
                "mode": "booking"
            })
        
        # Invalid response
        return (BookingState.CONFIRMING.value, intent, {
            "action": "retry",
            "message": "Please reply 'yes' to confirm or 'no' to restart.",
            "mode": "booking"
        })
    
    def _handle_otp_verification(self, message: str, intent: BookingIntent, language: str, history: List) -> Tuple[str, BookingIntent, Dict]:
        """Handle OTP"""
        
        otp = self._extract_otp(message)
        
        if otp:
            return (BookingState.OTP_SENT.value, intent, {
                "action": "verify_otp", 
                "otp": otp, 
                "message": None,
                "mode": "booking"
            })
        
        return (BookingState.OTP_SENT.value, intent, {
            "action": "retry", 
            "message": "❌ Please enter the 6-digit OTP.",
            "mode": "booking"
        })
    
    # ========== EXTRACTION METHODS ==========
    
    def _extract_all_fields(self, message: str, intent: BookingIntent, history: List = None) -> Dict[str, str]:
        """Extract ALL possible fields from a single message - ENHANCED"""
        extracted = {}
        
        # Clean the message first
        clean_msg = message.strip()
        logger.info(f"📝 Extracting fields from message (length: {len(clean_msg)}): '{clean_msg[:100]}'")
        
        # Store original message for recovery if needed
        original_message = clean_msg
        
        # ====== FIELD EXTRACTION WITH PRIORITY ======
        
        # 1. Extract email FIRST (most specific pattern)
        if not intent.email:
            email = self._extract_email(clean_msg)
            if email:
                intent.email = email
                extracted["Email"] = email
                # Remove email from message to avoid interference with other extractions
                clean_msg = clean_msg.replace(email, " ")
                logger.info(f"✅ Extracted email: {email}")
            else:
                logger.info(f"❌ Failed to extract email")
        
        # 2. Extract phone (WITH COUNTRY CODE - STRICT)
        if not self._is_phone_valid(intent.phone):
            phone_data = self._extract_phone_strict(clean_msg)
            if phone_data:
                intent.phone = phone_data['full_phone']
                intent.phone_country = phone_data['country']
                extracted["Phone"] = phone_data['full_phone']
                if phone_data['country']:
                    extracted["Phone Country"] = phone_data['country']
                
                # Remove phone from message to avoid interference
                clean_msg = clean_msg.replace(phone_data['full_phone'], " ")
                logger.info(f"✅ Extracted phone: {phone_data['full_phone']}")
            else:
                logger.info(f"❌ Failed to extract phone")
        
        # 3. Extract date (before name/address to avoid confusion)
        if not intent.date:
            date = self._extract_date(clean_msg)
            if date:
                intent.date = date
                extracted["Date"] = date
                logger.info(f"✅ Extracted date: {date}")
                
                # Remove common date patterns from message
                date_patterns_to_remove = [
                    r'\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4}',
                    r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:\s*,\s*\d{4})?',
                    r'\d{4}-\d{1,2}-\d{1,2}',
                    r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}'
                ]
                
                for pattern in date_patterns_to_remove:
                    clean_msg = re.sub(pattern, " ", clean_msg, flags=re.IGNORECASE)
            else:
                logger.info(f"❌ Failed to extract date")
        
        # 4. Extract pincode (simple pattern, extract before address)
        if not intent.pincode:
            pincode = self._extract_pincode(clean_msg)
            if pincode:
                intent.pincode = pincode
                extracted["PIN Code"] = pincode
                logger.info(f"✅ Extracted PIN: {pincode}")
                
                # Remove pincode from message
                clean_msg = re.sub(r'\b' + re.escape(pincode) + r'\b', " ", clean_msg)
        
        # 5. Extract name (after removing other identifiable info)
        if not intent.name:
            name = self._extract_name(clean_msg)
            if name:
                intent.name = name
                extracted["Name"] = name
                logger.info(f"✅ Extracted name: {name}")
                
                # Remove name from message (be careful with common names)
                name_words = name.split()
                if len(name_words) >= 2:
                    # Remove full name
                    clean_msg = clean_msg.replace(name, " ")
                else:
                    # Remove single name word if it's not too common
                    common_names = ['john', 'jane', 'david', 'mary', 'robert', 'lisa']
                    if name.lower() not in common_names:
                        clean_msg = re.sub(r'\b' + re.escape(name) + r'\b', " ", clean_msg, flags=re.IGNORECASE)
            else:
                logger.info(f"❌ Failed to extract name")
        
        # 6. Extract address (after removing other fields)
        if not intent.address:
            address = self._extract_address(clean_msg)
            if address:
                intent.address = address
                # Truncate for display but store full
                display_addr = address[:50] + "..." if len(address) > 50 else address
                extracted["Address"] = display_addr
                logger.info(f"✅ Extracted address: {display_addr}")
            else:
                logger.info(f"❌ Failed to extract address")
        
        # 7. Handle country inference (do this last)
        if not intent.service_country:
            # First priority: phone country
            if intent.phone_country:
                intent.service_country = intent.phone_country
                extracted["Country"] = intent.service_country
                logger.info(f"✅ Country from phone: {intent.service_country}")
            
            # Second priority: infer from address/pincode
            elif intent.address or intent.pincode:
                country = self._infer_country_from_location(intent.address, intent.pincode)
                if country:
                    intent.service_country = country
                    extracted["Country"] = country
                    logger.info(f"✅ Country inferred from location: {country}")
            
            # Third priority: extract from message if not already done
            else:
                country = self._extract_country(original_message)
                if country:
                    intent.service_country = country
                    extracted["Country"] = country
                    logger.info(f"✅ Country extracted from message: {country}")
        
        # 8. Special handling for Indian addresses
        if intent.address and "india" in intent.address.lower() and not intent.service_country:
            intent.service_country = "India"
            extracted["Country"] = "India"
            logger.info("✅ Set country to India based on address content")
        
        # 9. Check for date ambiguity
        if intent.date and self._is_date_ambiguous(original_message):
            extracted["Date Note"] = "Please confirm date"
            logger.info("⚠️ Date might be ambiguous")
        
        # 10. Extract any remaining details from original message
        remaining_fields = self._extract_remaining_details(original_message, intent)
        if remaining_fields:
            extracted.update(remaining_fields)
            logger.info(f"📋 Extracted additional fields: {list(remaining_fields.keys())}")
        
        # Log summary
        logger.info(f"📊 Extraction summary: {list(extracted.keys())}")
        logger.info(f"📊 Intent state - Name: {intent.name}, Email: {intent.email}, Phone: {intent.phone}, Date: {intent.date}")
        
        return extracted


    def _extract_remaining_details(self, message: str, intent: BookingIntent) -> Dict[str, str]:
        """Extract any remaining fields that might have been missed"""
        remaining = {}
        
        # Check for service type if not already set
        if not intent.service:
            service = self._extract_service_contextual(message, [])
            if service:
                intent.service = service
                remaining["Service"] = service
        
        # Check for package if not already set
        if intent.service and not intent.package:
            package = self._extract_package(message, intent.service, None)
            if package:
                intent.package = package
                remaining["Package"] = package
        
        # Look for any additional phone numbers
        if not self._is_phone_valid(intent.phone):
            # Try alternative phone patterns
            alt_patterns = [
                r'(?:phone|mobile|whatsapp)[:\s]*([+\d][\d\s\-\(\)]{8,})',
                r'(\+\d{1,3}[\s\-]?\d{5,})',
                r'(\d{10})'
            ]
            
            for pattern in alt_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    phone_candidate = match.group(1).strip()
                    # Validate it
                    if len(re.sub(r'\D', '', phone_candidate)) >= 10:
                        intent.phone = phone_candidate
                        remaining["Phone (alt)"] = phone_candidate
                        break
        
        # Look for additional date mentions
        if not intent.date:
            # Try different date formats
            date_formats_to_try = [
                r'\b(\d{1,2}/\d{1,2}/\d{4})\b',
                r'\b(\d{1,2}-\d{1,2}-\d{4})\b',
                r'\b(\d{4}/\d{1,2}/\d{1,2})\b',
                r'\b(\d{1,2}\s+(?:of\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})\b',
                r'\b((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?\s*,\s*\d{4})\b'
            ]
            
            for pattern in date_formats_to_try:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    date_str = match.group(1)
                    # Try to parse it
                    try:
                        from datetime import datetime
                        # Try different formats
                        for fmt in ['%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y', '%Y-%m-%d']:
                            try:
                                date_obj = datetime.strptime(date_str, fmt)
                                intent.date = date_obj.strftime("%Y-%m-%d")
                                remaining["Date (alt)"] = intent.date
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass
        
        return remaining
    
    def _is_phone_valid(self, phone: Optional[str]) -> bool:
        """Check if phone is valid (has country code and proper length) - FIXED"""
        if not phone:
            return False
        
        # Remove all non-digit characters except +
        clean_phone = phone.strip()
        
        # Must start with +
        if not clean_phone.startswith('+'):
            return False
        
        # Extract digits after +
        digits = re.sub(r'\D', '', clean_phone[1:])  # Remove + first
        
        # Check length: total digits should be at least 10 (including country code)
        # Country codes are 1-3 digits, so total should be 11-13 digits
        total_digits = len(digits)
        
        if total_digits < 10:
            # Phone too short
            return False
        
        # Check if it looks like a valid international number
        # Pattern: +[country code 1-3 digits][phone number 7-15 digits]
        if total_digits > 15:
            # Phone too long
            return False
        
        # Valid country codes (common for your target regions)
        valid_country_codes = ['91', '977', '92', '880', '971', '1']
        
        # Check first 1-3 digits for country code
        for i in range(1, 4):
            if i <= len(digits):
                country_code = digits[:i]
                if country_code in valid_country_codes:
                    # Check remaining digits length
                    remaining = total_digits - len(country_code)
                    if 7 <= remaining <= 12:  # Most countries have 7-12 digit local numbers
                        return True
        
        # If we get here, check generic pattern
        return 10 <= total_digits <= 14
    
    def _is_already_given_response(self, message: str) -> bool:
        """Check if user says they already provided information"""
        msg_lower = message.lower()
        already_phrases = [
            "i already gave", "i already provided", "i already told",
            "i said already", "already gave", "already provided",
            "i gave you", "i told you", "you already have",
            "it's already there", "check the history", "look back"
        ]
        return any(phrase in msg_lower for phrase in already_phrases)
    
    def _check_history_for_field(self, field: str, history: List[Dict]) -> Optional[str]:
        """Check conversation history for previously provided field"""
        if not history:
            return None
        
        # Map fields to extraction methods
        field_extractors = {
            "service": self._extract_service_from_text,
            "package": self._extract_package_from_text,
            "name": self._extract_name,
            "phone": lambda msg: (self._extract_phone_strict(msg) or {}).get('full_phone'),
            "email": self._extract_email,
            "date": self._extract_date,
            "address": self._extract_address,
            "pincode": self._extract_pincode,
            "country": self._extract_country,
        }
        
        extractor = field_extractors.get(field)
        if not extractor:
            return None
        
        # Check last 10 user messages in reverse order
        for msg in reversed(history[-10:]):
            if msg["role"] == "user":
                value = extractor(msg["content"])
                if value:
                    return value
        
        return None
    
    def _recover_fields_from_history(self, intent: BookingIntent, history: List[Dict]) -> Dict[str, Any]:
        """Recover missing fields from conversation history"""
        if not history:
            return {}
        
        recovered = {}
        missing = intent.missing_fields()
        
        # Map readable missing fields to actual field names
        field_map = {
            "service type": "service",
            "package choice": "package",
            "your name": "name",
            "email address": "email",
            "phone number with country code": "phone",
            "service country": "service_country",
            "service address": "address",
            "PIN/postal code": "pincode",
            "preferred date": "date"
        }
        
        for readable_field in missing:
            field_name = field_map.get(readable_field)
            if field_name:
                value = self._check_history_for_field(field_name, history)
                if value:
                    recovered[field_name] = value
        
        return recovered
    
    def _reorder_missing_fields(self, missing_fields: List[str]) -> List[str]:
        """Reorder fields to follow master prompt priority: address before pincode"""
        if not missing_fields:
            return missing_fields
        
        # Reorder: address should come before pincode
        if "service address" in missing_fields and "PIN/postal code" in missing_fields:
            address_idx = missing_fields.index("service address")
            pincode_idx = missing_fields.index("PIN/postal code")
            if pincode_idx < address_idx:
                # Swap to ask address first
                missing_fields[pincode_idx], missing_fields[address_idx] = missing_fields[address_idx], missing_fields[pincode_idx]
        
        return missing_fields
    
    def _is_date_ambiguous(self, message: str) -> bool:
        """Check if date extraction might be ambiguous"""
        msg_lower = message.lower()
        
        ambiguous_patterns = [
            r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2})\b',  # DD/MM/YY or MM/DD/YY (ambiguous)
            r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})\b',  # "Feb 5" (no year)
            r'\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b',  # "5 Feb" (no year)
            r'\bnext\s+(week|month|year)\b',  # Relative without specific date
            r'\bthis\s+(week|month|year)\b',  # Relative without specific date
        ]
        
        return any(re.search(pattern, msg_lower) for pattern in ambiguous_patterns)
    
    def _check_date_ambiguity_response(self, message: str, current_date: Optional[str]) -> Optional[str]:
        """Handle date ambiguity confirmation"""
        msg_lower = message.lower()
        
        if not current_date:
            return None
        
        # Try to parse the date for display
        try:
            date_obj = datetime.strptime(current_date, "%Y-%m-%d")
            display_date = date_obj.strftime("%d %b %Y")
        except:
            display_date = current_date
        
        # Check for confirmation patterns
        confirm_patterns = [
            r'yes.*confirm.*date',
            r'date.*correct',
            r'is.*on.*' + re.escape(display_date.lower()),
            r'confirm.*' + re.escape(str(date_obj.day)) + r'.*' + re.escape(date_obj.strftime("%b").lower())
        ]
        
        deny_patterns = [
            r'no.*date',
            r'wrong.*date',
            r'not.*correct.*date',
            r'different.*date'
        ]
        
        if any(re.search(pattern, msg_lower) for pattern in confirm_patterns):
            return None  # Date confirmed, no response needed
        
        if any(re.search(pattern, msg_lower) for pattern in deny_patterns):
            return f"❌ Please provide the correct date (e.g., 5 Feb 2026):"
        
        return None
    
    def _is_info_query(self, message: str) -> bool:
        """Detect info mode"""
        msg_lower = message.lower()
        
        info_keywords = ["list", "show", "tell me", "what are", "what is", "which", 
                        "how much", "cost", "price", "info", "information", "about", 
                        "details", "available", "offer", "explain", "describe"]
        
        booking_keywords = ["book", "booking", "i want to book", "reserve", 
                           "schedule", "appointment", "proceed", "confirm", "choose"]
        
        has_info = any(kw in msg_lower for kw in info_keywords)
        has_booking = any(bk in msg_lower for bk in booking_keywords)
        
        # It's an info query if it has info keywords but NO booking intent
        return has_info and not has_booking
    
    def _is_booking_intent(self, message: str, history: List = None) -> bool:
        """Detect booking mode - FIXED VERSION"""
        msg_lower = message.lower().strip()
        
        # STRONG booking signals (explicit intent) - EXPANDED LIST
        strong_signals = [
            "book", "booking", "i want to book", "want to book", "book this",
            "book it", "proceed with booking", "confirm booking", "make booking",
            "schedule", "reserve", "appointment", "i'll book", "let's book",
            "go for", "go with", "choose", "select", "pick", "get", "proceed",
            "confirm", "go ahead", "take", "i'd like to book", "i'd like to make",
            "book for", "book a", "book an", "make a booking", "make reservation",
            "i want to make", "i need to book", "looking to book", "interested in booking",
            "can you book", "could you book", "help me book", "want to reserve",
            "book makeup", "book makeup service", "book makeup services",
            "book makeup appointment", "book a makeup", "book a makeup session",
            "book bridal", "book party", "book engagement", "book henna",
            "for makeup services"  # NEW: This will catch "for makeup services"
        ]
        
        # Check if ANY strong signal is in the message
        if any(signal in msg_lower for signal in strong_signals):
            return True
        
        # Also check for "for makeup services" pattern specifically
        if "for makeup services" in msg_lower or "for makeup service" in msg_lower:
            return True
        
        # Numeric selection when we last showed a list
        if self.last_shown_list and re.match(r'^[1-4]$', msg_lower):
            return True
        
        # Check for event details pattern (date + location)
        date_pattern = r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4})\b'
        location_pattern = r'\b(in|at|near|around|from)\s+(pune|mumbai|delhi|bangalore|chennai|kolkata|hyderabad|ahmedabad|jaipur|lucknow|indore|kathmandu|pokhara|karachi|lahore|dhaka|dubai|maharashtra|karnataka|tamil\s+nadu|uttar\s+pradesh)\b'
        
        has_date = re.search(date_pattern, msg_lower, re.IGNORECASE)
        has_location = re.search(location_pattern, msg_lower, re.IGNORECASE)
        
        if has_date and has_location:
            return True
        
        # "I want/need [service]" without "to know/information/details"
        if ("i want" in msg_lower or "i need" in msg_lower or "interested in" in msg_lower) and \
        not any(x in msg_lower for x in ["know", "information", "details", "about", "learn"]):
            return True
        
        # Contains multiple personal details (name, phone, email, etc.)
        detail_patterns = [
            r'name[:\s]', r'phone[:\s]', r'email[:\s]', r'\+\d{1,3}', 
            r'@\w+\.\w+', r'\d{5,6}', r'address[:\s]'
        ]
        detail_count = sum(1 for pattern in detail_patterns if re.search(pattern, msg_lower, re.IGNORECASE))
        
        return detail_count >= 2


    
    def _extract_service_contextual(self, message: str, history: List) -> Optional[str]:
        """Context-aware service extraction"""
        msg_lower = message.lower().strip()
        
        # 1. Check numeric selection based on last shown list
        if self.last_shown_list == "services":
            num_match = re.search(r'\b([1-4])\b', msg_lower)
            if num_match:
                idx = int(num_match.group(1)) - 1
                if 0 <= idx < len(self.services):
                    return self.services[idx]
        
        # 2. Check text patterns
        service_patterns = {
            "Bridal Makeup Services": [r'\bbridal\b', r'\bbride\b', r'\bwedding\b', r'\bmarriage\b'],
            "Party Makeup Services": [r'\bparty\b', r'\bfunction\b', r'\bcelebration\b'],
            "Engagement & Pre-Wedding Makeup": [r'\bengagement\b', r'\bpre[\s-]?wedding\b', r'\bsangeet\b'],
            "Henna (Mehendi) Services": [r'\bhenna\b', r'\bmehendi\b', r'\bmehndi\b']
        }
        
        for service, patterns in service_patterns.items():
            for pattern in patterns:
                if re.search(pattern, msg_lower):
                    return service
        
        return None
    
    def _extract_service_from_text(self, text: str) -> Optional[str]:
        """Extract service from text (for history checking)"""
        return self._extract_service_contextual(text, [])
    
    def _extract_package(self, message: str, service: str, last_shown_list: str) -> Optional[str]:
        """Context-aware package extraction"""
        if not service or service not in SERVICES:
            return None
        
        msg_lower = message.lower().strip()
        packages = list(SERVICES[service]["packages"].keys())
        
        # Check numeric selection if we last showed packages
        if last_shown_list == "packages":
            num_match = re.search(r'\b([1-3])\b', msg_lower)
            if num_match:
                idx = int(num_match.group(1)) - 1
                if 0 <= idx < len(packages):
                    return packages[idx]
        
        # Check text patterns with context
        for pkg in packages:
            pkg_lower = pkg.lower()
            # Check for explicit package selection
            if any(phrase in msg_lower for phrase in [
                f"choose {pkg_lower}", f"select {pkg_lower}", 
                f"go with {pkg_lower}", f"want {pkg_lower}",
                f"take {pkg_lower}", f"option.*{pkg_lower}"
            ]):
                return pkg
            
            # Check for key terms in package name
            key_terms = pkg_lower.split()
            for term in key_terms:
                if len(term) > 3 and term in msg_lower and any(word in msg_lower for word in ["package", "option", "choose", "select"]):
                    return pkg
        
        return None
    
    def _extract_package_from_text(self, text: str) -> Optional[str]:
        """Extract package from text (for history checking)"""
        # Try to match against all services
        for service in SERVICES.keys():
            packages = list(SERVICES[service]["packages"].keys())
            for pkg in packages:
                pkg_lower = pkg.lower()
                text_lower = text.lower()
                
                # Check if package name appears in text
                if pkg_lower in text_lower:
                    return pkg
                
                # Check for key terms
                key_terms = pkg_lower.split()
                for term in key_terms:
                    if len(term) > 3 and term in text_lower:
                        return pkg
        return None
    
    def _extract_name(self, message: str) -> Optional[str]:
        """Extract name"""
        msg = message.strip()
        
        # Remove common prefixes
        prefixes = ["my name is", "i am", "i'm", "name:", "this is", "call me", "name is"]
        for prefix in prefixes:
            if msg.lower().startswith(prefix):
                msg = msg[len(prefix):].strip()
                break
        
        # Look for name patterns
        name_match = re.search(r'([A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){0,2})', msg)
        if name_match:
            name = name_match.group(1).strip()
            if 2 <= len(name) <= 30:
                return ' '.join(word.capitalize() for word in name.split())
        
        return None
    
    def _extract_phone_strict(self, message: str) -> Optional[Dict]:
        """STRICT: Only accept with country code - IMPROVED"""
        
        # Pattern for Indian numbers specifically (+91 followed by 10 digits)
        indian_patterns = [
            r'\+91[\s\-\.]?(\d{10})',  # +91 9876543210 or +91-9876543210
            r'\+91(\d{10})',  # +919876543210
            r'\+91\s*(\d{5})\s*(\d{5})',  # +91 98765 43210
        ]
        
        for pattern in indian_patterns:
            matches = list(re.finditer(pattern, message))
            for match in matches:
                if pattern == r'\+91\s*(\d{5})\s*(\d{5})':
                    # Two groups of 5 digits
                    digits = match.group(1) + match.group(2)
                else:
                    digits = match.group(1)
                
                if len(digits) == 10:
                    return {
                        'full_phone': f"+91{digits}",
                        'phone': digits,
                        'country': "India",
                        'code': '91'
                    }
        
        # Pattern for other countries
        patterns = [
            r'\+(\d{1,3})[\s\-\.]?(\d{6,})',  # Standard format
            r'\+(\d{1,3})(\d{6,})',  # No separator
        ]
        
        for pattern in patterns:
            matches = list(re.finditer(pattern, message))
            for match in matches:
                code, number = match.groups()
                
                # Clean number (keep only digits)
                number = re.sub(r'\D', '', number)
                
                # Map country codes
                code_map = {
                    '91': 'India', '977': 'Nepal', '92': 'Pakistan', 
                    '880': 'Bangladesh', '971': 'Dubai', '1': 'USA'
                }
                
                country = code_map.get(code)
                if country:
                    # Validate number length based on country
                    min_length = {
                        'India': 10, 'Nepal': 7, 'Pakistan': 10,
                        'Bangladesh': 10, 'Dubai': 9, 'USA': 10
                    }.get(country, 7)
                    
                    if len(number) >= min_length:
                        return {
                            'full_phone': f"+{code}{number}",
                            'phone': number,
                            'country': country,
                            'code': code
                        }
        
        # Try to find just digits that might be a phone (last resort)
        digit_match = re.search(r'\b(\d{10,15})\b', message)
        if digit_match:
            number = digit_match.group(1)
            if 10 <= len(number) <= 15:
                # Default to India for long Indian-looking numbers
                if len(number) == 10:
                    return {
                        'full_phone': f"+91{number}",
                        'phone': number,
                        'country': None,  # Unknown, will ask
                        'code': '91'
                    }
        
        return None
    
    def _extract_email(self, message: str) -> Optional[str]:
        """Extract email - IMPROVED with better pattern matching"""
        
        # Debug logging
        from agent_fsm import logger  # Import logger if not already imported
        
        logger.info(f"🔍 Extracting email from: '{message[:100]}'")
        
        # Look for email patterns
        email_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Standard email
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\.[A-Z|a-z]{2,}\b',  # Multi-part TLDs
        ]
        
        for pattern in email_patterns:
            matches = list(re.finditer(pattern, message))
            for match in matches:
                email = match.group(0).strip()
                logger.info(f"🔍 Found email candidate: {email}")
                
                # Basic validation
                if len(email) >= 6 and '@' in email and '.' in email:
                    logger.info(f"✅ Valid email extracted: {email}")
                    return email
        
        # Also check for emails that might be at end of string or have punctuation
        simple_pattern = r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})[,\s.]'
        match = re.search(simple_pattern, message)
        if match:
            email = match.group(1).strip()
            logger.info(f"🔍 Found email with punctuation: {email}")
            if len(email) >= 6:
                logger.info(f"✅ Valid email extracted: {email}")
                return email
        
        logger.info("❌ No email found")
        return None
    
    def _extract_date(self, message: str) -> Optional[str]:
        """Extract date - FIXED for invalid dates like 30 feb"""
        msg_lower = message.lower().strip()
        
        # Clean message
        clean_msg = message
        clean_msg = re.sub(r'\S+@\S+\.\S+', '', clean_msg)  # Remove email
        clean_msg = re.sub(r'\+\d[\d\s\-]+', '', clean_msg)  # Remove phone
        clean_msg = re.sub(r'\b\d{10,}\b', '', clean_msg)  # Remove long numbers
        clean_lower = clean_msg.lower()
        
        # Relative dates
        if 'today' in clean_lower:
            return datetime.utcnow().strftime("%Y-%m-%d")
        if 'tomorrow' in clean_lower:
            return (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        if 'after 10 days' in clean_lower or 'in 10 days' in clean_lower:
            return (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")
        
        # Month names
        month_map = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 
            'mar': 3, 'march': 3, 'apr': 4, 'april': 4, 
            'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7, 
            'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 
            'dec': 12, 'december': 12
        }
        
        # Pattern 1: "30th feb 2026" or "30 feb 2026" 
        for month_name, month_num in month_map.items():
            pattern = rf'(\d{{1,2}})(?:st|nd|rd|th)?\s+{month_name}\s*(\d{{4}})?'
            match = re.search(pattern, clean_lower)
            if match:
                try:
                    day = int(match.group(1))
                    year = int(match.group(2)) if match.group(2) else datetime.utcnow().year
                    
                    # IMPORTANT FIX: Don't validate day-month validity here
                    # Just store whatever user provides
                    try:
                        # Try to create the date
                        date_obj = datetime(year, month_num, day)
                        return date_obj.strftime("%Y-%m-%d")
                    except ValueError:
                        # If invalid (like Feb 30), still accept it but with validation
                        # Use last valid day of month
                        import calendar
                        last_day = calendar.monthrange(year, month_num)[1]
                        corrected_day = min(day, last_day)
                        logger.warning(f"⚠️ Invalid date {day} {month_name} {year}, corrected to {corrected_day}")
                        date_obj = datetime(year, month_num, corrected_day)
                        return date_obj.strftime("%Y-%m-%d")
                except (ValueError, AttributeError):
                    continue
        
        # Pattern 2: "feb 30 2026"
        for month_name, month_num in month_map.items():
            pattern = rf'{month_name}\s+(\d{{1,2}})(?:\s*,\s*|\s+)(\d{{4}})'
            match = re.search(pattern, clean_lower)
            if match:
                try:
                    day = int(match.group(1))
                    year = int(match.group(2))
                    
                    try:
                        date_obj = datetime(year, month_num, day)
                        return date_obj.strftime("%Y-%m-%d")
                    except ValueError:
                        import calendar
                        last_day = calendar.monthrange(year, month_num)[1]
                        corrected_day = min(day, last_day)
                        logger.warning(f"⚠️ Invalid date {month_name} {day} {year}, corrected to {corrected_day}")
                        date_obj = datetime(year, month_num, corrected_day)
                        return date_obj.strftime("%Y-%m-%d")
                except (ValueError, AttributeError):
                    continue
        
        # Pattern 3: YYYY-MM-DD
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', message)
        if match:
            try:
                year, month, day = map(int, match.groups())
                return datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                pass
        
        # Pattern 4: DD/MM/YYYY or MM/DD/YYYY
        match = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})', message)
        if match:
            try:
                day, month, year = map(int, match.groups())
                return datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                try:
                    month, day, year = map(int, match.groups())
                    return datetime(year, month, day).strftime("%Y-%m-%d")
                except ValueError:
                    pass
        
        # Pattern 5: Just month and day without year
        for month_name, month_num in month_map.items():
            pattern = rf'\b{month_name}\s+(\d{{1,2}})\b'
            match = re.search(pattern, clean_lower)
            if match:
                try:
                    day = int(match.group(1))
                    current_date = datetime.utcnow()
                    year = current_date.year
                    
                    # If this month has passed, use next year
                    if month_num < current_date.month or (month_num == current_date.month and day < current_date.day):
                        year = current_date.year + 1
                    
                    try:
                        date_obj = datetime(year, month_num, day)
                        return date_obj.strftime("%Y-%m-%d")
                    except ValueError:
                        import calendar
                        last_day = calendar.monthrange(year, month_num)[1]
                        corrected_day = min(day, last_day)
                        logger.warning(f"⚠️ Invalid date {month_name} {day}, corrected to {corrected_day}")
                        date_obj = datetime(year, month_num, corrected_day)
                        return date_obj.strftime("%Y-%m-%d")
                except (ValueError, AttributeError):
                    continue
        
        # Pattern 6: "30 feb" (without year)
        for month_name, month_num in month_map.items():
            pattern = rf'(\d{{1,2}})\s+{month_name}\b'
            match = re.search(pattern, clean_lower)
            if match:
                try:
                    day = int(match.group(1))
                    current_date = datetime.utcnow()
                    year = current_date.year
                    
                    if month_num < current_date.month or (month_num == current_date.month and day < current_date.day):
                        year = current_date.year + 1
                    
                    try:
                        date_obj = datetime(year, month_num, day)
                        return date_obj.strftime("%Y-%m-%d")
                    except ValueError:
                        import calendar
                        last_day = calendar.monthrange(year, month_num)[1]
                        corrected_day = min(day, last_day)
                        logger.warning(f"⚠️ Invalid date {day} {month_name}, corrected to {corrected_day}")
                        date_obj = datetime(year, month_num, corrected_day)
                        return date_obj.strftime("%Y-%m-%d")
                except (ValueError, AttributeError):
                    continue
        
        return None
    
    def _extract_address(self, message: str) -> Optional[str]:
        """Extract address - IMPROVED to exclude dates and personal info"""
        original_msg = message.strip()
        
        if not original_msg or len(original_msg) < 10:
            return None
        
        # STEP 1: Clean the message by removing common non-address elements
        clean_msg = original_msg
        
        # Remove email addresses
        clean_msg = re.sub(r'\S+@\S+\.\S+', '', clean_msg)
        
        # Remove phone numbers (with +91, +977, etc.)
        clean_msg = re.sub(r'\+\d[\d\s\-\.]+', '', clean_msg)
        
        # Remove standalone 10+ digit numbers (phone numbers without +)
        clean_msg = re.sub(r'\b\d{10,}\b', '', clean_msg)
        
        # Remove PIN codes (5-6 digits)
        clean_msg = re.sub(r'\b\d{5,6}\b', '', clean_msg)
        
        # Remove common name patterns (Title Case words at beginning)
        # This handles "Rupesh Poudel," type patterns
        name_match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)[,\s]*', clean_msg)
        if name_match:
            clean_msg = clean_msg[len(name_match.group(0)):]
        
        # Remove dates (comprehensive patterns)
        date_patterns = [
            # "25th feb 2026", "25th february 2026"
            r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4}\b',
            # "feb 25 2026", "february 25 2026"
            r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:\s*,\s*\d{4})?\b',
            # YYYY-MM-DD
            r'\b\d{4}-\d{1,2}-\d{1,2}\b',
            # DD/MM/YYYY or MM/DD/YYYY
            r'\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}\b',
            # "25 feb", "feb 25"
            r'\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b',
            r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b',
            # Relative dates
            r'\b(?:today|tomorrow|yesterday|next\s+\w+|this\s+\w+)\b'
        ]
        
        for pattern in date_patterns:
            clean_msg = re.sub(pattern, '', clean_msg, flags=re.IGNORECASE)
        
        # Remove extra commas and spaces
        clean_msg = re.sub(r'\s+', ' ', clean_msg)
        clean_msg = re.sub(r',\s*,', ',', clean_msg)
        clean_msg = clean_msg.strip(' ,')
        
        # STEP 2: Check if what remains looks like an address
        if len(clean_msg) < 10:
            return None
        
        # Address indicators (keywords that suggest it's an address)
        address_indicators = [
            'street', 'st.', 'road', 'rd.', 'lane', 'ln.', 'avenue', 'ave.', 
            'boulevard', 'blvd.', 'drive', 'dr.', 'circle', 'cir.', 'court', 'ct.',
            'house', 'flat', 'apartment', 'apt.', 'building', 'bldg.', 'floor', 'fl.',
            'room', 'rm.', 'suite', 'ste.', 'unit', 'block', 'blk.',
            'colony', 'sector', 'area', 'locality', 'village', 'town', 'city',
            'district', 'state', 'county', 'province', 'region',
            'near', 'beside', 'opposite', 'behind', 'in front of', 'at', 'by',
            'no.', 'number', '#', 'plot', 'ward', 'mohalla', 'chowk', 'nagar'
        ]
        
        # Location/city names (common in addresses)
        location_names = [
            'mumbai', 'delhi', 'bangalore', 'hyderabad', 'ahmedabad', 'chennai',
            'kolkata', 'surat', 'pune', 'jaipur', 'lucknow', 'kanpur', 'nagpur',
            'indore', 'thane', 'bhopal', 'visakhapatnam', 'patna', 'vadodara',
            'kathmandu', 'pokhara', 'biratnagar', 'lalitpur', 'bhaktapur',
            'karachi', 'lahore', 'islamabad', 'rawalpindi',
            'dhaka', 'chittagong', 'khulna',
            'dubai', 'abu dhabi', 'sharjah'
        ]
        
        clean_lower = clean_msg.lower()
        
        # Check address indicators
        has_indicator = any(ind in clean_lower for ind in address_indicators)
        
        # Check location names
        has_location = any(loc in clean_lower for loc in location_names)
        
        # Check for address-like patterns
        # Pattern: Number followed by text (e.g., "123 Main St")
        has_number_text = bool(re.search(r'\b\d+\s+[A-Za-z]', clean_msg))
        
        # Pattern: Contains both letters and numbers
        has_letters = any(c.isalpha() for c in clean_msg)
        has_numbers = any(c.isdigit() for c in clean_msg)
        has_mixed = has_letters and has_numbers
        
        # STEP 3: Determine if it's an address
        is_address = False
        
        # Rule 1: Has address indicator + reasonable length
        if has_indicator and len(clean_msg) >= 10:
            is_address = True
        
        # Rule 2: Has location name + some additional text
        elif has_location and len(clean_msg) >= 15:
            is_address = True
        
        # Rule 3: Number+text pattern + reasonable length
        elif has_number_text and len(clean_msg) >= 10:
            is_address = True
        
        # Rule 4: Mixed letters/numbers + no obvious non-address patterns
        elif has_mixed and len(clean_msg) >= 15:
            # Check it's not just random text
            # Avoid things that are too short or look like codes
            if not clean_msg.isdigit() and not re.match(r'^[A-Z]{2,}\d+$', clean_msg):
                is_address = True
        
        if is_address:
            # Final cleanup
            address = clean_msg.strip()
            
            # Remove trailing punctuation
            address = re.sub(r'[,\s\.]+$', '', address)
            
            # Ensure it starts with something meaningful
            if len(address) >= 10:
                # Truncate if too long, but keep important parts
                if len(address) > 200:
                    # Try to keep the beginning which usually has house/street info
                    address = address[:200]
                    # Don't cut in middle of word if possible
                    last_space = address.rfind(' ')
                    if last_space > 150:
                        address = address[:last_space]
                
                return address
        
        return None

    def _handle_already_provided_date(self, message: str, intent: BookingIntent, history: List) -> Tuple[bool, Optional[str]]:
        """Check if user says they already provided date - IMPROVED for frustrated users"""
        msg_lower = message.lower()
        
        # Check for ANY sign of user frustration about date
        # This includes both explicit mentions and general frustration
        frustration_indicators = [
            # Explicit mentions of already providing date
            "already provided", "already gave", "already told", "already said",
            "i already gave", "i already told", "i already said", "i already provided",
            "i told you", "i said already", "i gave you", "i mentioned",
            "you already have", "you have it", "it's there", "check history",
            "look back", "see previous", "i provided", "i shared",
            
            # Frustration about not being understood
            "why aren't you understanding", "not understanding", "don't understand",
            "can't understand", "why don't you understand", "not getting it",
            "you're not getting", "you don't understand", "you're not understanding",
            
            # General frustration phrases
            "again?", "seriously?", "really?", "come on", "ugh", "oh my god",
            "for god's sake", "for goodness sake", "are you kidding", "you kidding",
            "this is ridiculous", "ridiculous", "annoying", "frustrating",
            "what's wrong", "what is wrong", "what's the problem", "problem",
            "error", "bug", "glitch", "not working", "broken",
            
            # Date-specific frustration
            "i gave the date", "date is there", "date already", "provided date",
            "date provided", "told you the date", "said the date", "date mentioned",
            "check the date", "date is", "it's in there",
            
            # Short angry responses
            "i did", "i have", "yes", "obviously", "of course", "clearly"
        ]
        
        # Also check if message contains date-related words
        date_keywords = ['date', 'day', 'when', 'time', 'schedule', 'feb', 'jan', 'mar', 
                        'april', 'may', 'jun', 'july', 'aug', 'sep', 'oct', 'nov', 'dec']
        
        # Check if there's ANY frustration indicator OR date keywords
        has_frustration = any(indicator in msg_lower for indicator in frustration_indicators)
        mentions_date = any(keyword in msg_lower for keyword in date_keywords)
        
        # Also check for very short messages (often signs of frustration)
        is_short_angry = len(message.strip()) < 20 and any(word in msg_lower for word in 
                                                        ['yes', 'no', 'did', 'have', 'gave', 'told'])
        
        if has_frustration or (mentions_date and is_short_angry):
            
            logger.warning(f"😠 User seems frustrated about date: '{message}'")
            
            # First, check if date is actually in the current frustrated message
            date_in_current = self._extract_date(message)
            if date_in_current:
                logger.info(f"✅ Found date in current frustrated message: {date_in_current}")
                return True, date_in_current
            
            # Check the conversation history for ANY date
            if history:
                logger.info(f"🔍 Searching history for date in {len(history)} messages")
                
                # Look in ALL user messages, not just recent ones
                all_dates_found = []
                for i, msg in enumerate(history):
                    if msg["role"] == "user":
                        content = msg["content"]
                        date_in_msg = self._extract_date(content)
                        if date_in_msg:
                            all_dates_found.append((i, content, date_in_msg))
                            content_preview = content[:50].replace('\n', ' ')
                            logger.info(f"📅 Found date at position {i}: '{content_preview}' -> {date_in_msg}")
                
                if all_dates_found:
                    # Sort by position (most recent first)
                    all_dates_found.sort(reverse=True)
                    
                    # Try to find the most likely date
                    for pos, content, date_found in all_dates_found:
                        # Check if this message looks like it contains user details
                        has_details = any(word in content.lower() for word in 
                                        ['name', 'phone', 'email', 'address', 'pincode', 'pin'])
                        
                        if has_details:
                            logger.info(f"🎯 Most likely date from detailed message: {date_found}")
                            return True, date_found
                    
                    # If no detailed message found, use the most recent date
                    most_recent_date = all_dates_found[0][2]
                    logger.info(f"📅 Using most recent date found: {most_recent_date}")
                    return True, most_recent_date
            
            # If we still can't find a date, check if intent already has one
            if intent.date:
                logger.info(f"✅ Intent already has date: {intent.date}")
                return True, intent.date
            
            # Last resort: check if we can extract date from the context
            # Sometimes users say "I said 30th feb" in their frustration
            date_patterns = [
                r'i (?:said|told|gave|provided) (?:you )?(?:the )?(?:date )?(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4})',
                r'date (?:is|was) (\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4})',
                r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4}) (?:is|was) (?:the|my) date'
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, msg_lower)
                if match:
                    date_str = match.group(1)
                    extracted_date = self._extract_date(date_str)
                    if extracted_date:
                        logger.info(f"🔍 Extracted date from frustration pattern: {extracted_date}")
                        return True, extracted_date
        
        return False, None
    
    def _extract_pincode(self, message: str) -> Optional[str]:
        """Extract PIN code (5-6 digits)"""
        # Look for standalone 5-6 digit numbers
        matches = re.finditer(r'\b(\d{5,6})\b', message)
        
        for match in matches:
            pin = match.group(1)
            idx = match.start()
            
            # Check context - not part of phone number or date
            before = message[max(0, idx-1):idx]
            after = message[idx+len(pin):idx+len(pin)+1]
            
            # Not surrounded by other digits
            if not (before.isdigit() or after.isdigit()):
                # Not likely part of phone (phone would have 10+ digits)
                if len(pin) in [5, 6]:
                    return pin
        
        return None
    
    def _extract_country(self, message: str) -> Optional[str]:
        """Extract country name"""
        msg_lower = message.lower()
        
        countries = {
            'India': [r'\bindia\b', r'\bindian\b', r'\bdelhi\b', r'\bmumbai\b', r'\bbangalore\b'],
            'Nepal': [r'\bnepal\b', r'\bnepali\b', r'\bkathmandu\b', r'\bpokhara\b'],
            'Pakistan': [r'\bpakistan\b', r'\bkarachi\b', r'\blahore\b'],
            'Bangladesh': [r'\bbangladesh\b', r'\bdhaka\b'],
            'Dubai': [r'\bdubai\b', r'\buae\b', r'\bunited arab emirates\b']
        }
        
        for country, patterns in countries.items():
            for pattern in patterns:
                if re.search(pattern, msg_lower):
                    return country
        
        return None
    
    def _extract_otp(self, message: str) -> Optional[str]:
        """Extract 6-digit OTP"""
        match = re.search(r'\b(\d{6})\b', message)
        return match.group(1) if match else None
    
    def _infer_country_from_location(self, address: Optional[str], pincode: Optional[str]) -> Optional[str]:
        """Smart country inference from address and pincode"""
        
        if not address and not pincode:
            return None
        
        address_lower = (address or "").lower()
        
        # Check pincode patterns first
        if pincode:
            # Indian pincodes: 6 digits starting with 1-8
            if len(pincode) == 6 and pincode[0] in '12345678':
                return "India"
            
            # Nepali pincodes: 5 digits
            if len(pincode) == 5:
                return "Nepal"
        
        # Check address text
        country_indicators = {
            "India": ['india', 'delhi', 'mumbai', 'bangalore', 'chennai', 'kolkata', 
                     'pune', 'hyderabad', 'ahmedabad', 'jaipur', 'lucknow', 'indore'],
            "Nepal": ['nepal', 'kathmandu', 'pokhara', 'bhaktapur', 'lalitpur'],
            "Pakistan": ['pakistan', 'karachi', 'lahore', 'islamabad', 'rawalpindi'],
            "Bangladesh": ['bangladesh', 'dhaka', 'chittagong', 'khulna'],
            "Dubai": ['dubai', 'uae', 'abu dhabi', 'sharjah', 'emirates']
        }
        
        for country, indicators in country_indicators.items():
            for indicator in indicators:
                if indicator in address_lower:
                    return country
        
        return None
    
    # ========== PROMPT GENERATION METHODS ==========
    
    def _get_service_prompt(self, language: str) -> str:
        """Service prompt"""
        prompts = {
            "en": "🎯 **Available Services:**\n\n1. Bridal Makeup Services\n2. Party Makeup Services\n3. Engagement & Pre-Wedding Makeup\n4. Henna (Mehendi) Services\n\nPlease choose a number or name:",
            "ne": "🎯 **उपलब्ध सेवाहरू:**\n\n1. ब्राइडल मेकअप सेवाहरू\n2. पार्टी मेकअप सेवाहरू\n3. इन्गेजमेन्ट र प्री-वेडिंग मेकअप\n4. हेन्ना (मेहेन्दी) सेवाहरू\n\nकृपया नम्बर वा नाम छनोट गर्नुहोस्:",
            "hi": "🎯 **उपलब्ध सेवाएं:**\n\n1. ब्राइडल मेकअप सेवाएं\n2. पार्टी मेकअप सेवाएं\n3. एंगेजमेंट और प्री-वेडिंग मेकअप\n4. मेंहदी सेवाएं\n\nकृपया नंबर या नाम चुनें:",
            "mr": "🎯 **उपलब्ध सेवा:**\n\n1. ब्राइडल मेकअप सेवा\n2. पार्टी मेकअप सेवा\n3. इंगेजमेंट आणि प्री-वेडिंग मेकअप\n4. मेंदी सेवा\n\nकृपया क्रमांक किंवा नाव निवडा:"
        }
        return prompts.get(language, prompts["en"])
    
    def _get_package_prompt(self, service: str, language: str) -> str:
        """Package prompt"""
        if service not in SERVICES:
            return "Choose package:"
        
        packages = SERVICES[service]["packages"]
        result = f"📦 **Packages for {service}:**\n\n"
        
        for idx, (pkg, price) in enumerate(packages.items(), 1):
            # Shorten long package names
            short_name = pkg.split("(")[0].strip() if "(" in pkg else pkg
            result += f"{idx}. {short_name} - {price}\n"
        
        result += "\nPlease choose a number or name:"
        
        return result.strip()
    
    def _get_details_prompt(self, intent: BookingIntent, language: str) -> str:
        """Prompt for collecting personal details"""
        
        templates = {
            "en": """✅ Perfect! Now I need a few details for your booking:

**You can provide all at once to save time!**
Example: "Name: John Doe, Phone: +91-9876543210, Email: john@email.com, Date: 5 Feb 2026, Address: 123 Main St Mumbai"

**Required Information:**
• Your full name
• WhatsApp number WITH country code (e.g., +91, +977)
• Email address
• Event date
• Event address
• PIN/postal code

What would you like to share first?""",
            
            "ne": """✅ राम्रो! अब तपाईंको बुकिङको लागि केही विवरण चाहिन्छ:

**समय बचाउन सबै एकैपटक दिन सक्नुहुन्छ!**
उदाहरण: "नाम: जोन डो, फोन: +९७७-९८५१२३४५६७, इमेल: john@email.com, मिति: ५ फेब्रुअरी २०२६, ठेगाना: १२३ मुख्य सडक काठमाडौं"

**आवश्यक जानकारी:**
• तपाईंको पुरा नाम
• देश कोड सहित व्हाट्सएप नम्बर (जस्तै, +९१, +९७७)
• इमेल ठेगाना
• कार्यक्रम मिति
• कार्यक्रम ठेगाना
• पिन/डाक कोड

के साझा गर्न चाहनुहुन्छ?""",
            
            "hi": """✅ बढ़िया! अब आपकी बुकिंग के लिए कुछ विवरण चाहिए:

**समय बचाने के लिए सब एक साथ दे सकते हैं!**
उदाहरण: "नाम: जॉन डो, फोन: +९१-९८७६५४३२१०, ईमेल: john@email.com, तारीख: ५ फरवरी २०२६, पता: १२३ मुख्य सड़क मुंबई"

**आवश्यक जानकारी:**
• आपका पूरा नाम
• देश कोड के साथ व्हाट्सएप नंबर (जैसे, +९१, +९७७)
• ईमेल पता
• कार्यक्रम तिथि
• कार्यक्रम पता
• पिन/डाक कोड

क्या साझा करना चाहेंगे?"""
        }
        
        return templates.get(language, templates["en"])
    
    def _get_missing_fields_prompt(self, intent: BookingIntent, language: str, extracted: Dict[str, str], missing: List[str]) -> str:
        """Prompt for specific missing fields"""
        
        # Acknowledge what was collected
        ack_parts = []
        if extracted:
            ack_templates = {
                "en": "✅ Got it! I've recorded:\n",
                "ne": "✅ बुझें! मैले रेकर्ड गरें:\n",
                "hi": "✅ समझ गया! मैंने रिकॉर्ड किया:\n",
                "mr": "✅ समजले! मी रेकॉर्ड केले:\n"
            }
            ack_text = ack_templates.get(language, ack_templates["en"])
            
            for field, value in extracted.items():
                # Format phone for display
                if "Phone" in field and value and value.startswith('+'):
                    # Extract last 4 digits for display
                    digits = re.sub(r'\D', '', value)
                    if len(digits) >= 4:
                        display_value = f"{value[:8]}****{digits[-4:]}"
                    else:
                        display_value = value
                    ack_text += f"• {field}: {display_value}\n"
                else:
                    ack_text += f"• {field}: {value}\n"
            
            ack_parts.append(ack_text.strip())
        
        # Ask for missing fields
        if missing:
            # Special handling for phone
            if "phone number with country code" in missing:
                phone_prompts = {
                    "en": """📱 **WhatsApp Number with Country Code**

Please share your WhatsApp number WITH country code:
• +91-9876543210 (India)
• +977-9851234567 (Nepal)
• +92-3001234567 (Pakistan)
• +880-1712345678 (Bangladesh)
• +971-501234567 (Dubai)

We'll send OTP to this number for verification.""",
                    "ne": """📱 **देश कोड सहित व्हाट्सएप नम्बर**

कृपया देश कोड सहित आफ्नो व्हाट्सएप नम्बर साझा गर्नुहोस्:
• +९१-९८७६५४३२१० (भारत)
• +९७७-९८५१२३४५६७ (नेपाल)
• +९२-३००१२३४५६७ (पाकिस्तान)
• +८८०-१७१२३४५६७८ (बंगलादेश)
• +९७१-५०१२३४५६७ (दुबई)

हामी प्रमाणीकरणको लागि यो नम्बरमा OTP पठाउनेछौं।""",
                    "hi": """📱 **देश कोड के साथ व्हाट्सएप नंबर**

कृपया देश कोड के साथ अपना व्हाट्सएप नंबर साझा करें:
• +९१-९८७६५४३२१० (भारत)
• +९७७-९८५१२३४५६७ (नेपाल)
• +९२-३००१२३४५६७ (पाकिस्तान)
• +८८०-१७१२३४५६७८ (बांग्लादेश)
• +९७१-५०१२३४५६७ (दुबई)

हम सत्यापन के लिए इस नंबर पर OTP भेजेंगे।"""
                }
                ask_text = phone_prompts.get(language, phone_prompts["en"])
            else:
                ask_templates = {
                    "en": f"\n\n📝 I still need:\n{chr(10).join(f'• {field}' for field in missing)}\n\nPlease provide:",
                    "ne": f"\n\n📝 मलाई अझै चाहिन्छ:\n{chr(10).join(f'• {field}' for field in missing)}\n\nकृपया प्रदान गर्नुहोस्:",
                    "hi": f"\n\n📝 मुझे अभी भी चाहिए:\n{chr(10).join(f'• {field}' for field in missing)}\n\nकृपया दें:",
                    "mr": f"\n\n📝 मला अजून हवे:\n{chr(10).join(f'• {field}' for field in missing)}\n\nकृपया द्या:"
                }
                ask_text = ask_templates.get(language, ask_templates["en"])
            ack_parts.append(ask_text)
        
        return "\n".join(ack_parts).strip()
    
    def _get_confirmation_prompt(self, intent: BookingIntent, language: str) -> str:
        """Confirmation prompt"""
        
        # Format phone for display
        phone_display = intent.phone
        if phone_display and len(phone_display) > 8:
            # Extract last 4 digits
            digits = re.sub(r'\D', '', phone_display)
            if len(digits) >= 4:
                phone_display = f"{phone_display[:8]}****{digits[-4:]}"
        
        templates = {
            "en": f"""🎯 **BOOKING SUMMARY**

✅ **Service Details:**
• Service: {intent.service}
• Package: {intent.package}

✅ **Contact Information:**
• Name: {intent.name}
• Phone: {phone_display or 'Not provided'}
• Email: {intent.email}

✅ **Event Details:**
• Date: {intent.date}
• Location: {intent.service_country}
• Address: {intent.address[:50]}{'...' if intent.address and len(intent.address) > 50 else ''}
• PIN: {intent.pincode}

**Please confirm:** Is everything correct? (yes/no)""",
            
            "ne": f"""🎯 **बुकिङ सारांश**

✅ **सेवा विवरण:**
• सेवा: {intent.service}
• प्याकेज: {intent.package}

✅ **सम्पर्क जानकारी:**
• नाम: {intent.name}
• फोन: {phone_display or 'उपलब्ध छैन'}
• इमेल: {intent.email}

✅ **कार्यक्रम विवरण:**
• मिति: {intent.date}
• स्थान: {intent.service_country}
• ठेगाना: {intent.address[:50]}{'...' if intent.address and len(intent.address) > 50 else ''}
• पिन: {intent.pincode}

**कृपया पुष्टि गर्नुहोस्:** के सबै ठीक छ? (हो/होइन)""",
            
            "hi": f"""🎯 **बुकिंग सारांश**

✅ **सेवा विवरण:**
• सेवा: {intent.service}
• पैकेज: {intent.package}

✅ **संपर्क जानकारी:**
• नाम: {intent.name}
• फोन: {phone_display or 'उपलब्ध नहीं'}
• ईमेल: {intent.email}

✅ **कार्यक्रम विवरण:**
• तारीख: {intent.date}
• स्थान: {intent.service_country}
• पता: {intent.address[:50]}{'...' if intent.address and len(intent.address) > 50 else ''}
• पिन: {intent.pincode}

**कृपया पुष्टि करें:** क्या सब कुछ सही है? (हां/नहीं)"""
        }
        
        return templates.get(language, templates["en"])


booking_fsm = BookingFSM()