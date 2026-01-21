import json
import logging
import requests
import re
from typing import Tuple, Dict, Any, Optional
from datetime import datetime, timedelta
from dateutil import parser as date_parser

from config import GROQ_API_KEY, COUNTRY_CODES
from agent_models import BookingIntent, ConversationMemory
from agent_prompts import SERVICES, get_package_options

logger = logging.getLogger(__name__)

def extract_intent_from_message(message: str, current_intent: BookingIntent, last_asked_field: str = None, conversation_context: str = "") -> BookingIntent:
    """
    ULTRA ENHANCED: Advanced NLP-style intent extraction with context awareness
    """
    updated = current_intent.copy()
    msg_lower = message.lower().strip()
    
    # Skip extraction if user is just acknowledging or asking questions
    skip_words = ["what", "which", "how", "why", "when", "where", "list", "show", "tell me"]
    if any(msg_lower.startswith(word) for word in skip_words) and len(msg_lower.split()) <= 5:
        return updated
    
    # If we asked for a specific field, prioritize that field with conversation context
    if last_asked_field:
        extracted = _extract_by_context(message, last_asked_field, updated, conversation_context)
        if extracted is not None:
            setattr(updated, last_asked_field, extracted)
            logger.info(f"Extracted {last_asked_field}: {extracted}")
            
            # Special handling for phone - also extract country
            if last_asked_field == "phone":
                phone_data = _extract_phone_smart(message, conversation_context)
                if isinstance(phone_data, dict) and phone_data.get('country'):
                    updated.phone_country = phone_data.get('country')
                    logger.info(f"Extracted phone_country: {phone_data.get('country')}")
            
            return updated
    
    # General multi-field extraction
    updated = _extract_all_fields(message, updated, conversation_context)
    
    return updated

def _extract_by_context(message: str, field: str, current_intent: BookingIntent, context: str = "") -> Optional[Any]:
    """Extract specific field based on what was asked with full context awareness"""
    
    if field == "service":
        return _extract_service(message)
    
    elif field == "package":
        return _extract_package(message, current_intent.service)
    
    elif field == "name":
        return _extract_name(message)
    
    elif field == "email":
        return _extract_email(message)
    
    elif field == "phone":
        # Return just the phone number string
        phone_data = _extract_phone_smart(message, context)
        if isinstance(phone_data, dict):
            return phone_data.get('phone')
        return phone_data
    
    elif field == "service_country":
        return _extract_country_smart(message, context, "service")
    
    elif field == "address":
        return _extract_address(message)
    
    elif field == "pincode":
        return _extract_pincode(message)
    
    elif field == "date":
        return _extract_date_smart(message)
    
    return None

def _extract_all_fields(message: str, current_intent: BookingIntent, context: str = "") -> BookingIntent:
    """Extract all possible fields from message with context"""
    
    # Service
    if not current_intent.service:
        service = _extract_service(message)
        if service:
            current_intent.service = service
    
    # Package
    if current_intent.service and not current_intent.package:
        package = _extract_package(message, current_intent.service)
        if package:
            current_intent.package = package
    
    # Name
    if not current_intent.name:
        name = _extract_name(message)
        if name:
            current_intent.name = name
    
    # Email
    if not current_intent.email:
        email = _extract_email(message)
        if email:
            current_intent.email = email
    
    # Phone with smart country detection
    if not current_intent.phone:
        phone_data = _extract_phone_smart(message, context)
        if phone_data:
            if isinstance(phone_data, dict):
                current_intent.phone = phone_data.get('phone')
                if phone_data.get('country'):
                    current_intent.phone_country = phone_data.get('country')
            else:
                current_intent.phone = phone_data
    
    # Service Country (separate from phone country)
    if not current_intent.service_country:
        country = _extract_country_smart(message, context, "service")
        if country:
            current_intent.service_country = country
    
    # Address
    if not current_intent.address:
        address = _extract_address(message)
        if address:
            current_intent.address = address
    
    # PIN code
    if not current_intent.pincode:
        pincode = _extract_pincode(message)
        if pincode:
            current_intent.pincode = pincode
    
    # Date with natural language understanding
    if not current_intent.date:
        date = _extract_date_smart(message)
        if date:
            current_intent.date = date
    
    return current_intent

# ==================== SMART EXTRACTION FUNCTIONS ====================

def _extract_phone_smart(message: str, context: str = "") -> Optional[Any]:
    """
    SMART: Extract phone with automatic country detection
    Understands: "I live in India but service in Nepal"
    """
    msg_lower = message.lower()
    
    # Detect phone country from context clues
    phone_country = None
    
    # Pattern: "I live in X" or "my number is from X"
    live_patterns = [
        r'(?:i|we)\s+live\s+in\s+(\w+)',
        r'(?:i|we)\s+(?:am|are)\s+in\s+(\w+)',
        r'(?:i|we)\s+(?:am|are)\s+from\s+(\w+)',
        r'my\s+number\s+is\s+from\s+(\w+)',
        r'phone\s+(?:is\s+)?from\s+(\w+)',
    ]
    
    for pattern in live_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            country_name = match.group(1).title()
            if country_name in COUNTRY_CODES:
                phone_country = country_name
                logger.info(f"Detected phone country from context: {phone_country}")
                break
    
    # Extract phone number
    phone = None
    detected_country = None
    
    # Pattern 1: With explicit country code +91XXXXXXXXXX
    phone_match = re.search(r'\+(\d{1,3})[\s-]?(\d{10})', message)
    if phone_match:
        country_code, number = phone_match.groups()
        phone = number
        # Map country code to country
        code_map = {v.replace('+', ''): k for k, v in COUNTRY_CODES.items()}
        detected_country = code_map.get(country_code)
    
    # Pattern 2: Country code without + (91XXXXXXXXXX)
    if not phone:
        phone_match = re.search(r'\b(91|977|92|880|971)(\d{10})\b', message)
        if phone_match:
            country_code, number = phone_match.groups()
            phone = number
            code_map = {'91': 'India', '977': 'Nepal', '92': 'Pakistan', '880': 'Bangladesh', '971': 'Dubai'}
            detected_country = code_map.get(country_code)
    
    # Pattern 3: Just 10 digits (use context or default)
    if not phone:
        phone_match = re.search(r'\b(\d{10})\b', message)
        if phone_match:
            phone = phone_match.group(1)
    
    # Pattern 4: Formatted phone
    if not phone:
        phone_match = re.search(r'(\d{3}[-\.\s]?\d{3}[-\.\s]?\d{4})', message)
        if phone_match:
            digits = re.sub(r'\D', '', phone_match.group(0))
            if len(digits) == 10:
                phone = digits
    
    if not phone:
        return None
    
    # Determine final phone country
    final_country = phone_country or detected_country or "India"
    
    return {
        'phone': phone,
        'country': final_country
    }

def _extract_country_smart(message: str, context: str = "", purpose: str = "service") -> Optional[str]:
    """
    SMART: Extract country with context awareness
    purpose: "service" or "phone"
    Understands difference between phone location and service location
    """
    msg_lower = message.lower()
    
    # Service-specific patterns
    if purpose == "service":
        service_patterns = [
            r'(?:service|makeup|wedding|event)\s+in\s+(\w+)',
            r'(?:need|want)\s+(?:it|service|makeup)\s+in\s+(\w+)',
            r'(?:deliver|provide)\s+in\s+(\w+)',
            r'in\s+(\w+)\s+(?:please|plz)',
        ]
        
        for pattern in service_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                country_name = match.group(1).title()
                if country_name in COUNTRY_CODES:
                    logger.info(f"Detected service country: {country_name}")
                    return country_name
    
    # General country patterns
    country_patterns = {
        "India": [r'\bindia\b', r'\bindian\b', r'\b91\b', r'\+91\b', r'भारत', r'इंडिया'],
        "Nepal": [r'\bnepal\b', r'\bnepali\b', r'\b977\b', r'\+977\b', r'नेपाल'],
        "Pakistan": [r'\bpakistan\b', r'\bpakistani\b', r'\b92\b', r'\+92\b', r'पाकिस्तान'],
        "Bangladesh": [r'\bbangladesh\b', r'\bbangladeshi\b', r'\b880\b', r'\+880\b', r'बांग्लादेश'],
        "Dubai": [r'\bdubai\b', r'\buae\b', r'\bemirates\b', r'\b971\b', r'\+971\b', r'दुबई']
    }
    
    for country, patterns in country_patterns.items():
        for pattern in patterns:
            if re.search(pattern, msg_lower):
                return country
    
    return None

def _extract_date_smart(message: str) -> Optional[str]:
    """
    SMART: Extract date with advanced natural language understanding
    Handles: "2nd of the fall of february", "next friday", "in 2 weeks"
    """
    msg_lower = message.lower()
    
    # Clean up the message
    msg_lower = re.sub(r'\bthe\b', '', msg_lower)
    msg_lower = re.sub(r'\bof\b', ' ', msg_lower)
    msg_lower = re.sub(r'\bfall\b', '', msg_lower)  # Remove "fall" noise
    msg_lower = re.sub(r'\s+', ' ', msg_lower).strip()
    
    # Try to find year
    year_match = re.search(r'\b(202[4-9]|203[0-9])\b', message)
    current_year = year_match.group(1) if year_match else "2026"
    
    # Month names mapping
    month_names = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    
    # Pattern 1: "2nd february", "february 2", "2 feb"
    for month_name, month_num in month_names.items():
        patterns = [
            rf'(\d{{1,2}})\s*(?:st|nd|rd|th)?\s+{month_name}',
            rf'{month_name}\s+(\d{{1,2}})\s*(?:st|nd|rd|th)?',
        ]
        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                day = match.group(1)
                try:
                    date_obj = datetime(int(current_year), month_num, int(day))
                    return date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    continue
    
    # Pattern 2: Standard formats
    date_patterns = [
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', 'ymd'),
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', 'dmy'),
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'dmy'),
    ]
    
    for pattern, format_type in date_patterns:
        match = re.search(pattern, message)
        if match:
            try:
                if format_type == 'ymd':
                    year, month, day = match.groups()
                else:
                    day, month, year = match.groups()
                
                date_obj = datetime(int(year), int(month), int(day))
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                continue
    
    # Pattern 3: Relative dates
    relative_patterns = {
        r'today': 0,
        r'tomorrow': 1,
        r'day after tomorrow': 2,
        r'next week': 7,
        r'in (\d+) days?': lambda m: int(m.group(1)),
        r'in (\d+) weeks?': lambda m: int(m.group(1)) * 7,
    }
    
    for pattern, delta in relative_patterns.items():
        match = re.search(pattern, msg_lower)
        if match:
            if callable(delta):
                days = delta(match)
            else:
                days = delta
            target_date = datetime.utcnow() + timedelta(days=days)
            return target_date.strftime("%Y-%m-%d")
    
    # Pattern 4: Fuzzy parsing with dateutil
    try:
        # Extract words that might be dates
        potential_date = re.sub(r'[^\w\s\d/-]', '', message)
        parsed = date_parser.parse(potential_date, fuzzy=True, default=datetime(int(current_year), 1, 1))
        
        # Only accept if year is reasonable
        if 2024 <= parsed.year <= 2030:
            return parsed.strftime("%Y-%m-%d")
    except:
        pass
    
    return None

def _extract_service(message: str) -> Optional[str]:
    """Extract service with fuzzy matching"""
    msg_lower = message.lower()
    
    # Numeric selection
    num_match = re.search(r'\b([1-4])\b', message)
    if num_match:
        idx = int(num_match.group(1)) - 1
        services = list(SERVICES.keys())
        if 0 <= idx < len(services):
            return services[idx]
    
    # Keyword matching with scoring
    service_keywords = {
        "Bridal Makeup Services": {
            "keywords": ["bridal", "bride", "wedding", "dulhan", "shaadi", "marriage", "विवाह"],
            "score": 0
        },
        "Party Makeup Services": {
            "keywords": ["party", "function", "celebration", "event", "पार्टी"],
            "score": 0
        },
        "Engagement & Pre-Wedding Makeup": {
            "keywords": ["engagement", "pre-wedding", "pre wedding", "sangeet", "प्री-वेडिंग"],
            "score": 0
        },
        "Henna (Mehendi) Services": {
            "keywords": ["henna", "mehendi", "mehndi", "mehandi", "मेहंदी"],
            "score": 0
        }
    }
    
    for service, data in service_keywords.items():
        for keyword in data["keywords"]:
            if keyword in msg_lower:
                data["score"] += 1
    
    best_service = max(service_keywords.items(), key=lambda x: x[1]["score"])
    if best_service[1]["score"] > 0:
        return best_service[0]
    
    return None

def _extract_package(message: str, service: str) -> Optional[str]:
    """Extract package with intelligent matching"""
    if not service or service not in SERVICES:
        return None
    
    msg_lower = message.lower()
    packages = list(SERVICES[service]["packages"].keys())
    
    # Numeric selection
    num_match = re.search(r'\b([1-3])\b', message)
    if num_match:
        idx = int(num_match.group(1)) - 1
        if 0 <= idx < len(packages):
            return packages[idx]
    
    # Keyword matching
    package_keywords = {
        "Chirag's Signature Bridal Makeup": ["signature", "chirag signature", "premium bridal", "99999", "99,999", "1st", "first"],
        "Luxury Bridal Makeup (HD / Brush)": ["luxury", "hd", "brush", "79999", "79,999", "2nd", "second"],
        "Reception / Engagement / Cocktail Makeup": ["reception", "cocktail", "59999", "59,999", "3rd", "third"],
        "Party Makeup by Chirag Sharma": ["chirag party", "by chirag", "premium party", "19999", "19,999", "chirag", "1st", "first"],
        "Party Makeup by Senior Artist": ["senior", "senior artist", "basic", "6999", "6,999", "2nd", "second"],
        "Engagement Makeup by Chirag": ["chirag engagement", "premium engagement"],
        "Pre-Wedding Makeup by Senior Artist": ["senior pre-wedding", "basic pre-wedding"],
        "Henna by Chirag Sharma": ["chirag henna", "chirag mehendi", "premium henna", "49999", "49,999"],
        "Henna by Senior Artist": ["senior henna", "senior mehendi", "basic henna", "19999", "19,999"]
    }
    
    for pkg in packages:
        keywords = package_keywords.get(pkg, [])
        if any(keyword in msg_lower for keyword in keywords):
            return pkg
    
    return None

def _extract_name(message: str) -> Optional[str]:
    """Extract name with advanced parsing"""
    msg = message.strip()
    msg_lower = msg.lower()
    
    skip_phrases = ["yes", "no", "ok", "okay", "sure", "correct", "right", "single", "double",
                   "bridal", "party", "makeup", "service", "package", "book", "booking",
                   "want", "need", "like", "would", "could", "should"]
    
    if msg_lower in skip_phrases or len(msg) < 3:
        return None
    
    # Remove prefixes
    for prefix in ["my name is", "i am", "i'm", "name:", "name is", "this is", "call me", "it's", "its"]:
        msg = re.sub(f"(?i)^{prefix}\\s*", "", msg).strip()
    
    if re.search(r'\d|@|\.com|\.in|http|www', msg_lower):
        return None
    
    name_match = re.search(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', msg)
    if name_match:
        name = name_match.group(1).strip()
        if not any(word in name.lower() for word in ["india", "nepal", "dubai", "party", "bridal"]):
            return name[:50]
    
    words = msg.split()
    if 2 <= len(words) <= 4:
        if any(w[0].isupper() for w in words if len(w) > 1):
            return msg.strip()[:50]
    
    return None

def _extract_email(message: str) -> Optional[str]:
    """Extract email with validation"""
    email_match = re.search(r'\b[\w\.-]+@[\w\.-]+\.\w{2,}\b', message.lower())
    if email_match:
        email = email_match.group(0)
        if re.match(r'^[\w\.-]+@[\w\.-]+\.(com|in|org|net|edu|gov|co|io|ai)$', email):
            return email
    return None

def _extract_phone(message: str) -> Optional[str]:
    """Basic phone extraction (10 digits)"""
    phone_match = re.search(r'\b(\d{10})\b', message)
    if phone_match:
        return phone_match.group(1)
    return None

def _extract_country(message: str) -> Optional[str]:
    """Basic country extraction"""
    return _extract_country_smart(message, "", "service")

def _extract_address(message: str) -> Optional[str]:
    """Extract address with intelligent parsing"""
    msg = message.strip()
    msg_lower = msg.lower()
    
    if len(msg) < 5:
        return None
    
    skip_phrases = ["yes", "no", "ok", "okay", "sure", "correct", "what", "which", "how"]
    if msg_lower in skip_phrases:
        return None
    
    for prefix in ["address:", "address is", "my address is", "located at", "location:", "i live in", "at"]:
        msg = re.sub(f"(?i)^{prefix}\\s*", "", msg).strip()
    
    location_indicators = ["district", "city", "town", "village", "street", "road", "lane", "area", "sector"]
    has_location = any(indicator in msg_lower for indicator in location_indicators)
    
    words = msg.split()
    if len(words) >= 2 or has_location:
        address = msg[:200]
        if not any(word in address.lower() for word in ["bridal", "party", "makeup", "henna", "mehendi"]):
            return address
    
    return None

def _extract_pincode(message: str) -> Optional[str]:
    """Extract PIN code"""
    pin_patterns = [
        r'\bpin[:\s]+(\d{5,6})\b',
        r'\bpostal[:\s]+(\d{5,6})\b',
        r'\bcode[:\s]+(\d{5,6})\b',
        r'\b(\d{5,6})\b'
    ]
    
    for pattern in pin_patterns:
        match = re.search(pattern, message)
        if match:
            pin = match.group(1) if '(' in pattern else match.group(0)
            pin = re.sub(r'\D', '', pin)
            if 5 <= len(pin) <= 6:
                return pin
    
    return None

# ==================== UTILITY FUNCTIONS ====================

def format_phone_for_api(phone: str, country: str = "India") -> str:
    """Format phone for Twilio API"""
    if not phone:
        return ""
    
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) < 10:
        return ""
    
    phone_number = digits[-10:]
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
    phone_country = memory.intent.phone_country or memory.intent.service_country or "India"
    
    return {
        "service": memory.intent.service,
        "package": memory.intent.package,
        "name": memory.intent.name,
        "email": memory.intent.email,
        "phone": format_phone_for_api(memory.intent.phone, phone_country),
        "phone_country": phone_country,
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

def get_conversation_context(memory: ConversationMemory) -> str:
    """Build conversation context for AI"""
    context = []
    
    # Add last 5 messages
    for msg in memory.conversation_history[-5:]:
        role = msg.get("role", "")
        content = msg.get("content", "")
        context.append(f"{role}: {content}")
    
    return "\n".join(context)