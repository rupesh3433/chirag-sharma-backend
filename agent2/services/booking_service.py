"""
Booking Service - FINAL VERSION
Uses templates.py for all messages
"""

import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import threading

from ..models.memory import ConversationMemory
from ..config.config import (
    COUNTRY_CODES,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE
)
from ..prompts.templates import (
    get_whatsapp_confirmation_message,
    get_booking_summary_for_display,
    validate_language
)

logger = logging.getLogger(__name__)


class BookingService:
    """Booking creation and management - FINAL VERSION"""
    
    def __init__(self, booking_collection, twilio_client, whatsapp_from: str):
        """Initialize booking service"""
        self.booking_collection = booking_collection
        self.twilio_client = twilio_client
        self.whatsapp_from = whatsapp_from
        
        # Use config for country codes
        self.country_codes = COUNTRY_CODES
        
        # Stats tracking
        self.stats = {
            'created': 0,
            'saved': 0,
            'failed': 0,
            'whatsapp_sent': 0,
            'whatsapp_failed': 0
        }
        self.stats_lock = threading.RLock()
        
        logger.info("✅ BookingService initialized")
    
    def create_booking_payload(self, memory: ConversationMemory) -> Dict[str, Any]:
        """Create booking data from memory"""
        with self.stats_lock:
            self.stats['created'] += 1
        
        phone_country = memory.intent.phone_country
        
        # Infer phone country if not set
        if not phone_country and memory.intent.phone and memory.intent.phone.startswith('+'):
            phone_code_map = {
                '91': 'India', '977': 'Nepal', '92': 'Pakistan',
                '880': 'Bangladesh', '971': 'Dubai'
            }
            
            for code, country in phone_code_map.items():
                if memory.intent.phone.startswith(f'+{code}'):
                    phone_country = country
                    break
        
        if not phone_country:
            phone_country = memory.intent.service_country or "India"
        
        # Format phone
        formatted_phone = self._format_phone_for_api(memory.intent.phone, phone_country)
        
        # Validate phone has country code
        if not formatted_phone or not formatted_phone.startswith('+'):
            logger.error(f"❌ Invalid phone: {memory.intent.phone}")
            digits = re.sub(r'\D', '', memory.intent.phone or "")
            if len(digits) >= 10:
                formatted_phone = f"+91{digits[-10:]}"
            else:
                formatted_phone = ""
        
        return {
            "service": memory.intent.service,
            "package": memory.intent.package,
            "name": memory.intent.name,
            "email": memory.intent.email,
            "phone": formatted_phone,
            "phone_country": phone_country,
            "service_country": memory.intent.service_country or "India",
            "address": memory.intent.address,
            "pincode": memory.intent.pincode,
            "date": memory.intent.date,
            "message": memory.intent.message or "",
            "language": memory.language,
            "session_id": memory.session_id,
            "stage": memory.stage,
            "status": "pending",
            "otp_verified": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "source": "agent_chat"
        }
    
    def validate_booking_completeness(self, intent) -> bool:
        """Validate booking has all required fields"""
        return intent.is_complete()
    
    def save_booking(self, booking_data: Dict) -> str:
        """Save booking to database"""
        try:
            result = self.booking_collection.insert_one(booking_data)
            booking_id = str(result.inserted_id)
            
            with self.stats_lock:
                self.stats['saved'] += 1
            
            logger.info(f"✅ Booking saved: {booking_id}")
            return booking_id
            
        except Exception as e:
            logger.error(f"❌ Booking save failed: {e}", exc_info=True)
            
            with self.stats_lock:
                self.stats['failed'] += 1
            
            raise
    
    def send_confirmation_whatsapp(self, phone: str, booking_data: Dict, language: str) -> bool:
        """Send WhatsApp confirmation"""
        try:
            # ✅ Use template function for message
            whatsapp_msg = get_whatsapp_confirmation_message(booking_data, language)
            
            # Format phone for WhatsApp
            whatsapp_phone = phone
            if not whatsapp_phone.startswith('whatsapp:'):
                whatsapp_phone = f"whatsapp:{phone}"
            
            # Send via Twilio
            self.twilio_client.messages.create(
                from_=self.whatsapp_from,
                to=whatsapp_phone,
                body=whatsapp_msg
            )
            
            with self.stats_lock:
                self.stats['whatsapp_sent'] += 1
            
            logger.info(f"✅ Confirmation sent to {phone}")
            return True
            
        except Exception as e:
            logger.error(f"❌ WhatsApp send failed: {e}")
            
            with self.stats_lock:
                self.stats['whatsapp_failed'] += 1
            
            return False
    
    def format_booking_summary(self, intent, language: str) -> str:
        """
        Format booking summary for display
        
        Args:
            intent: Booking intent object
            language: Language code
            
        Returns:
            Formatted summary string
        """
        # Validate language
        language = validate_language(language)
        
        # Build intent data dict
        intent_data = {
            'service': intent.service,
            'package': intent.package,
            'name': intent.name,
            'date': intent.date,
            'service_country': intent.service_country
        }
        
        # ✅ Use template function
        return get_booking_summary_for_display(intent_data, language)
    
    def _format_phone_for_api(self, phone: str, country: str = "India") -> str:
        """Format phone for API (add country code)"""
        if not phone:
            return ""
        
        # Already has country code
        if phone.startswith('+'):
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 10:
                return phone
            else:
                logger.warning(f"⚠️ Phone with + but insufficient digits: {phone}")
                return ""
        
        # Extract digits only
        digits = re.sub(r'\D', '', phone)
        
        if len(digits) < 10:
            logger.warning(f"⚠️ Phone too short: {phone}")
            return ""
        
        # Get last 10 digits
        phone_number = digits[-10:]
        
        # Get country code from config
        country_code = self.country_codes.get(country, "+91")
        
        # Clean country code
        if country_code.startswith('+'):
            clean_code = country_code[1:]
        else:
            clean_code = country_code
        
        formatted = f"+{clean_code}{phone_number}"
        logger.debug(f"📞 Formatted: {phone} -> {formatted}")
        
        return formatted
    
    def get_stats(self) -> Dict[str, Any]:
        """Get booking service statistics"""
        with self.stats_lock:
            stats = self.stats.copy()
            stats.update({
                "timestamp": datetime.utcnow().isoformat()
            })
            return stats