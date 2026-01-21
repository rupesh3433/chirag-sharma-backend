import json
import logging
import requests
import re
from typing import Tuple, Dict, Any
from datetime import datetime, timedelta

from config import GROQ_API_KEY, COUNTRY_CODES
from agent_models import BookingIntent, ConversationMemory
from agent_prompts import SERVICES, get_package_options

logger = logging.getLogger(__name__)

def extract_intent_from_message(message: str, current_intent: BookingIntent, last_asked_field: str = None) -> BookingIntent:
    """
    Enhanced intent extraction that respects conversation context
    """
    updated = current_intent.copy()
    msg_lower = message.lower().strip()
    
    # If we just asked for a specific field, prioritize extracting that field
    if last_asked_field:
        if last_asked_field == "service":
            service = _extract_service(message)
            if service:
                updated.service = service
                return updated
        
        elif last_asked_field == "package":
            package = _extract_package(message, updated.service)
            if package:
                updated.package = package
                return updated
        
        elif last_asked_field == "name":
            name = _extract_name(message)
            if name:
                updated.name = name
                return updated
        
        elif last_asked_field == "email":
            email = _extract_email(message)
            if email:
                updated.email = email
                return updated
        
        elif last_asked_field == "phone":
            phone = _extract_phone(message)
            if phone:
                updated.phone = phone
                # Try to extract country from message
                country = _extract_country(message)
                if country and not updated.phone_country:
                    updated.phone_country = country
                return updated
        
        elif last_asked_field == "service_country":
            country = _extract_country(message)
            if country:
                updated.service_country = country
                if not updated.phone_country:
                    updated.phone_country = country
                return updated
        
        elif last_asked_field == "address":
            # For address, take the whole message (cleaned)
            address = _extract_address(message)
            if address:
                updated.address = address
                # Also extract country if mentioned
                country = _extract_country(message)
                if country and not updated.service_country:
                    updated.service_country = country
                return updated
        
        elif last_asked_field == "pincode":
            pincode = _extract_pincode(message)
            if pincode:
                updated.pincode = pincode
                return updated
        
        elif last_asked_field == "date":
            date = _extract_date(message)
            if date:
                updated.date = date
                return updated
    
    # General extraction (for when user provides multiple details at once)
    if not updated.service:
        service = _extract_service(message)
        if service:
            updated.service = service
    
    if updated.service and not updated.package:
        package = _extract_package(message, updated.service)
        if package:
            updated.package = package
    
    if not updated.name:
        name = _extract_name(message)
        if name:
            updated.name = name
    
    if not updated.email:
        email = _extract_email(message)
        if email:
            updated.email = email
    
    if not updated.phone:
        phone = _extract_phone(message)
        if phone:
            updated.phone = phone
    
    if not updated.service_country or not updated.phone_country:
        country = _extract_country(message)
        if country:
            if not updated.service_country:
                updated.service_country = country
            if not updated.phone_country:
                updated.phone_country = country
    
    if not updated.address:
        address = _extract_address(message)
        if address:
            updated.address = address
    
    if not updated.pincode:
        pincode = _extract_pincode(message)
        if pincode:
            updated.pincode = pincode
    
    if not updated.date:
        date = _extract_date(message)
        if date:
            updated.date = date
    
    return updated

# Helper extraction functions
def _extract_service(message: str) -> str:
    """Extract service from message"""
    msg_lower = message.lower()
    
    # Check for numeric selection (1-4)
    num_match = re.search(r'\b([1-4])\b', message)
    if num_match:
        idx = int(num_match.group(1)) - 1
        services = list(SERVICES.keys())
        if 0 <= idx < len(services):
            return services[idx]
    
    # Keyword matching
    service_keywords = {
        "Bridal Makeup Services": ["bridal", "bride", "wedding", "dulhan", "shaadi", "marriage"],
        "Party Makeup Services": ["party", "function", "celebration", "event"],
        "Engagement & Pre-Wedding Makeup": ["engagement", "pre-wedding", "pre wedding", "sangeet"],
        "Henna (Mehendi) Services": ["henna", "mehendi", "mehndi", "mehandi"]
    }
    
    for service, keywords in service_keywords.items():
        if any(keyword in msg_lower for keyword in keywords):
            return service
    
    return None

def _extract_package(message: str, service: str) -> str:
    """Extract package from message based on service"""
    if not service or service not in SERVICES:
        return None
    
    msg_lower = message.lower()
    packages = list(SERVICES[service]["packages"].keys())
    
    # Check for numeric selection
    num_match = re.search(r'\b([1-3])\b', message)
    if num_match:
        idx = int(num_match.group(1)) - 1
        if 0 <= idx < len(packages):
            return packages[idx]
    
    # Keyword matching for specific packages
    package_keywords = {
        "Chirag's Signature Bridal Makeup": ["signature", "chirag signature", "premium bridal", "99999"],
        "Luxury Bridal Makeup (HD / Brush)": ["luxury", "hd", "brush", "79999"],
        "Reception / Engagement / Cocktail Makeup": ["reception", "cocktail", "engagement", "59999"],
        "Party Makeup by Chirag Sharma": ["chirag party", "by chirag", "premium party", "19999"],
        "Party Makeup by Senior Artist": ["senior", "senior artist", "basic party", "6999"],
        "Engagement Makeup by Chirag": ["chirag engagement", "premium engagement"],
        "Pre-Wedding Makeup by Senior Artist": ["senior pre-wedding", "basic pre-wedding"],
        "Henna by Chirag Sharma": ["chirag henna", "chirag mehendi", "premium henna", "49999"],
        "Henna by Senior Artist": ["senior henna", "senior mehendi", "basic henna", "19999"]
    }
    
    for pkg, keywords in package_keywords.items():
        if pkg in packages and any(keyword in msg_lower for keyword in keywords):
            return pkg
    
    return None

def _extract_name(message: str) -> str:
    """Extract name from message"""
    msg = message.strip()
    
    # Remove common phrases
    for phrase in ["my name is", "i am", "i'm", "name:", "name is", "this is", "call me"]:
        msg = re.sub(f"(?i){phrase}", "", msg).strip()
    
    # Check if it's not a common phrase or command
    common_words = ["yes", "no", "ok", "okay", "sure", "correct", "right", "single", "session", 
                    "bridal", "party", "makeup", "service", "package"]
    
    msg_lower = msg.lower()
    if msg_lower in common_words:
        return None
    
    # Extract capitalized words or quoted text
    name_match = re.search(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', msg)
    if name_match:
        return name_match.group(1).strip()
    
    # If message is 2-4 words and looks like a name
    words = msg.split()
    if 2 <= len(words) <= 4 and all(len(w) > 1 for w in words):
        # Check if not all lowercase (indicates it might be a name)
        if any(c.isupper() for c in msg):
            return msg.strip()[:50]
    
    return None

def _extract_email(message: str) -> str:
    """Extract email from message"""
    email_match = re.search(r'\b[\w\.-]+@[\w\.-]+\.\w{2,}\b', message)
    if email_match:
        return email_match.group(0)
    return None

def _extract_phone(message: str) -> str:
    """Extract phone from message"""
    # Try to find phone with country code
    phone_match = re.search(r'\+\d{1,3}[\s-]?\d{10}', message)
    if phone_match:
        # Extract all digits
        digits = re.sub(r'\D', '', phone_match.group(0))
        # Return last 10 digits (mobile number)
        return digits[-10:] if len(digits) >= 10 else None
    
    # Try to find 10-digit phone
    phone_match = re.search(r'\b\d{10}\b', message)
    if phone_match:
        return phone_match.group(0)
    
    # Try different formats
    phone_match = re.search(r'(\d{3}[-\.\s]?\d{3}[-\.\s]?\d{4})', message)
    if phone_match:
        digits = re.sub(r'\D', '', phone_match.group(0))
        if len(digits) == 10:
            return digits
    
    return None

def _extract_country(message: str) -> str:
    """Extract country from message"""
    msg_lower = message.lower()
    
    country_keywords = {
        "India": ["india", "indian", "भारत", "इंडिया", "+91", "91"],
        "Nepal": ["nepal", "nepali", "नेपाल", "+977", "977"],
        "Pakistan": ["pakistan", "pakistani", "पाकिस्तान", "+92", "92"],
        "Bangladesh": ["bangladesh", "bangladeshi", "बांग्लादेश", "+880", "880"],
        "Dubai": ["dubai", "uae", "emirates", "दुबई", "+971", "971"]
    }
    
    for country, keywords in country_keywords.items():
        if any(keyword in msg_lower for keyword in keywords):
            return country
    
    return None

def _extract_address(message: str) -> str:
    """Extract address from message"""
    msg = message.strip()
    
    # Remove common phrases
    for phrase in ["address:", "address is", "my address is", "location:", "at"]:
        msg = re.sub(f"(?i){phrase}", "", msg).strip()
    
    # If message has multiple words and is not too short
    if len(msg.split()) >= 2 and len(msg) > 5:
        return msg[:200]  # Limit length
    
    return None

def _extract_pincode(message: str) -> str:
    """Extract PIN code from message"""
    # 5-6 digit PIN codes
    pin_match = re.search(r'\b(\d{5,6})\b', message)
    if pin_match:
        return pin_match.group(1)
    return None

def _extract_date(message: str) -> str:
    """Extract date from message"""
    # Various date formats
    date_patterns = [
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', 'ymd'),  # 2026-01-25
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', 'dmy'),  # 25-01-2026
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'dmy'),  # 25/01/2026
        (r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})', 'text')
    ]
    
    for pattern, format_type in date_patterns:
        match = re.search(pattern, message.lower())
        if match:
            if format_type == 'ymd':
                year, month, day = match.groups()
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            elif format_type == 'dmy':
                day, month, year = match.groups()
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            elif format_type == 'text':
                day, month_name, year = match.groups()
                months = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
                         'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
                month = months.get(month_name[:3], 1)
                return f"{year}-{str(month).zfill(2)}-{day.zfill(2)}"
    
    return None

def format_phone_for_api(phone: str, country: str = "India") -> str:
    """Format phone for Twilio API"""
    if not phone:
        return ""
    
    # Extract only digits
    digits = re.sub(r'\D', '', phone)
    
    # Should be 10 digits for mobile
    if len(digits) < 10:
        return ""
    
    # Take last 10 digits
    phone_number = digits[-10:]
    
    # Get country code
    country_code = COUNTRY_CODES.get(country, "+91")
    
    return f"{country_code}{phone_number}"

def format_phone_display(phone: str, country: str = "India") -> str:
    """Format phone for display"""
    if not phone:
        return ""
    
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 10:
        return phone
    
    phone_number = digits[-10:]
    country_code = COUNTRY_CODES.get(country, "+91")
    
    return f"{country_code} {phone_number[:5]} {phone_number[5:]}"

def create_booking_data(memory: ConversationMemory) -> Dict[str, Any]:
    """Create booking data for database"""
    return {
        "service": memory.intent.service,
        "package": memory.intent.package,
        "name": memory.intent.name,
        "email": memory.intent.email,
        "phone": format_phone_for_api(memory.intent.phone, memory.intent.phone_country or memory.intent.service_country or "India"),
        "phone_country": memory.intent.phone_country or memory.intent.service_country or "India",
        "service_country": memory.intent.service_country or "India",
        "address": memory.intent.address,
        "pincode": memory.intent.pincode,
        "date": memory.intent.date,
        "message": memory.intent.message or "",
        "language": memory.language,
        "session_id": memory.session_id,
        "status": "pending",
        "otp_verified": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "source": "agent_chat"
    }