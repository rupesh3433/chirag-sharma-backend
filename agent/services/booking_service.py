"""
Booking Service - COMPLETE IMPLEMENTATION
Booking creation and management
"""

import re
import logging
from datetime import datetime
from typing import Dict, Any

from ..models.memory import ConversationMemory

logger = logging.getLogger(__name__)


class BookingService:
    """Booking creation and management"""
    
    def __init__(self, booking_collection, twilio_client, whatsapp_from: str):
        """Initialize booking service"""
        self.booking_collection = booking_collection
        self.twilio_client = twilio_client
        self.whatsapp_from = whatsapp_from
        
        self.country_codes = {
            "India": "+91",
            "Nepal": "+977",
            "Pakistan": "+92",
            "Bangladesh": "+880",
            "Dubai": "+971"
        }
    
    def create_booking_payload(self, memory: ConversationMemory) -> Dict[str, Any]:
        """Create booking data from memory"""
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
        
        if not formatted_phone.startswith('+'):
            logger.error(f"Phone missing country code: {memory.intent.phone}")
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
            logger.info(f"✅ Booking saved: {booking_id}")
            return booking_id
        except Exception as e:
            logger.error(f"❌ Booking save failed: {e}")
            raise
    
    def send_confirmation_whatsapp(self, phone: str, booking_data: Dict, language: str) -> bool:
        """Send WhatsApp confirmation"""
        try:
            whatsapp_msg = self.generate_whatsapp_message(booking_data, language)
            
            whatsapp_phone = phone
            if not whatsapp_phone.startswith('whatsapp:'):
                whatsapp_phone = f"whatsapp:{phone}"
            
            self.twilio_client.messages.create(
                from_=self.whatsapp_from,
                to=whatsapp_phone,
                body=whatsapp_msg
            )
            
            logger.info(f"✅ Confirmation WhatsApp sent to {phone}")
            return True
            
        except Exception as e:
            logger.error(f"❌ WhatsApp send failed: {e}")
            return False
    
    def generate_whatsapp_message(self, booking_data: Dict, language: str) -> str:
        """Generate WhatsApp confirmation message"""
        name = booking_data.get("name", "")
        service = booking_data.get("service", "")
        package = booking_data.get("package", "")
        date = booking_data.get("date", "")
        country = booking_data.get("service_country", "India")
        
        messages = {
            "en": f"""✅ **Booking Request Sent to Chirag Sharma!**

📋 **Details:**
• Name: {name}
• Service: {service}
• Package: {package}
• Date: {date}
• Location: {country}

⏳ **Status:** Pending Approval
Chirag will review and contact you within 24 hours via WhatsApp.

Thank you for choosing JinniChirag! 💄✨""",
            
            "ne": f"""✅ **बुकिङ अनुरोध चिराग शर्मालाई पठाइएको छ!**

📋 **विवरण:**
• नाम: {name}
• सेवा: {service}
• प्याकेज: {package}
• मिति: {date}
• स्थान: {country}

⏳ **स्थिति:** स्वीकृति पर्खिरहेको
चिराग २४ घण्टा भित्र तपाईंलाई व्हाट्सएप मार्फत सम्पर्क गर्नेछ।

JinniChirag छनोट गर्नुभएकोमा धन्यवाद! 💄✨""",
            
            "hi": f"""✅ **बुकिंग अनुरोध चिराग शर्मा को भेजा गया!**

📋 **विवरण:**
• नाम: {name}
• सेवा: {service}
• पैकेज: {package}
• तारीख: {date}
• स्थान: {country}

⏳ **स्थिति:** स्वीकृति की प्रतीक्षा
चिराग २४ घंटे के भीतर आपसे व्हाट्सएप पर संपर्क करेगा।

JinniChirag चुनने के लिए धन्यवाद! 💄✨"""
        }
        
        return messages.get(language, messages["en"])
    
    def format_booking_summary(self, intent, language: str) -> str:
        """Format booking summary"""
        summary_parts = []
        
        if intent.service:
            summary_parts.append(f"Service: {intent.service}")
        if intent.package:
            summary_parts.append(f"Package: {intent.package}")
        if intent.name:
            summary_parts.append(f"Name: {intent.name}")
        if intent.date:
            summary_parts.append(f"Date: {intent.date}")
        if intent.service_country:
            summary_parts.append(f"Location: {intent.service_country}")
        
        return "\n".join(summary_parts)
    
    def _format_phone_for_api(self, phone: str, country: str = "India") -> str:
        """Format phone for API (add country code)"""
        if not phone:
            return ""
        
        if phone.startswith('+'):
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 10:
                return phone
            else:
                return ""
        
        digits = re.sub(r'\D', '', phone)
        
        if len(digits) < 10:
            return ""
        
        phone_number = digits[-10:]
        country_code = self.country_codes.get(country, "+91")
        
        if country_code.startswith('+'):
            clean_code = country_code[1:]
        else:
            clean_code = country_code
        
        return f"+{clean_code}{phone_number}"