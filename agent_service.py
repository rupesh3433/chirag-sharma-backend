import json
import logging
import requests
import re
from typing import Tuple, Dict, Any, Optional, Union
from datetime import datetime, timedelta
from dateutil import parser as date_parser

from config import GROQ_API_KEY, COUNTRY_CODES
from agent_models import BookingIntent, ConversationMemory
from agent_prompts import SERVICES, get_package_options

logger = logging.getLogger(__name__)

def extract_intent_from_message(message: str, current_intent: BookingIntent, last_asked_field: str = None, conversation_context: str = "") -> BookingIntent:
    """
    IMPROVED: Better re-extraction and multi-field handling
    """
    updated = current_intent.copy()
    msg_lower = message.lower().strip()
    
    logger.info(f"🔍 EXTRACTING from: '{message}'")
    logger.info(f"📋 Last asked: {last_asked_field}")
    
    # ====== 1. CHECK FOR "ALREADY PROVIDED" ======
    already_patterns = [
        r'(?:i|we)\s+already\s+(?:gave|provided|told|mentioned|said)',
        r'already\s+(?:gave|provided|told|mentioned|said)',
        r'(?:i|we)\s+(?:gave|provided|told|mentioned)\s+(?:it|that|you|before)',
        r'i\s+(?:just|already)\s+(?:gave|provided|told)',
        r'(?:i|we)\s+gave\s+you',
        r'provided\s+(?:it|that|already)'
    ]
    
    already_provided = any(re.search(pattern, msg_lower) for pattern in already_patterns)
    
    if already_provided and last_asked_field:
        logger.info(f"🔄 User says they already provided {last_asked_field}. Searching history...")
        extracted = _re_extract_from_history(conversation_context, last_asked_field, updated)
        if extracted is not None:
            setattr(updated, last_asked_field, extracted)
            logger.info(f"✅ Re-extracted {last_asked_field}: {extracted}")
            
            # Also run general extraction for any other fields
            updated = _extract_all_fields(message, updated, conversation_context)
            return updated
        
        # If re-extraction failed, be more specific
        logger.warning(f"❌ Couldn't find {last_asked_field} in history. Asking again...")
        return updated
    
    # ====== 2. SKIP QUESTION MESSAGES ======
    if _is_just_question(message):
        logger.info("❓ Detected question only, skipping extraction")
        return updated
    
    # ====== 3. EXTRACT SPECIFIC FIELD IF ASKED ======
    if last_asked_field:
        logger.info(f"🎯 Looking for {last_asked_field} specifically...")
        
        # First, try direct extraction
        extracted = _extract_by_context(message, last_asked_field, updated, conversation_context)
        if extracted is not None:
            setattr(updated, last_asked_field, extracted)
            logger.info(f"✅ Extracted {last_asked_field}: {extracted}")
        
        # ALSO run multi-field extraction (important!)
        # User might say "email@example.com, PIN 123456" in one message
        updated = _extract_all_fields(message, updated, conversation_context)
        return updated
    
    # ====== 4. GENERAL MULTI-FIELD EXTRACTION ======
    logger.info("🔎 Running multi-field extraction...")
    old_summary = updated.get_summary()
    updated = _extract_all_fields(message, updated, conversation_context)
    new_summary = updated.get_summary()
    
    # Log what we found
    newly_collected = {k: v for k, v in new_summary.items() if k not in old_summary}
    if newly_collected:
        logger.info(f"✨ Newly collected fields: {newly_collected}")
    
    return updated

def _is_just_question(message: str) -> bool:
    """Check if message is just a question without info"""
    msg_lower = message.lower().strip()
    
    # Question words
    question_words = ["what", "which", "how", "why", "when", "where", "who", 
                     "can you", "could you", "would you", "will you"]
    
    # Check if starts with question word
    if any(msg_lower.startswith(word) for word in question_words):
        # But check if it also contains information
        info_patterns = [
            r'\b\d{5,6}\b',  # PIN/phone
            r'\b\d{10}\b',   # phone
            r'@\w+\.\w+',    # email
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b',  # name
            r'[1-4]',        # service/package number
            r'jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec'  # date
        ]
        
        has_info = any(re.search(pattern, message, re.IGNORECASE) for pattern in info_patterns)
        return not has_info
    
    return False



def _re_extract_from_history(conversation_context: str, field: str, current_intent: BookingIntent) -> Optional[Any]:
    """
    IMPROVED: Better history search with context
    """
    if not conversation_context:
        return None
    
    logger.info(f"🔍 Searching history for {field}...")
    
    # Parse ALL messages, not just user messages
    lines = conversation_context.strip().split('\n')
    
    # Get all messages with roles
    messages = []
    for line in lines:
        if ':' in line:
            role, content = line.split(':', 1)
            messages.append({
                'role': role.strip(),
                'content': content.strip()
            })
    
    # Search in reverse (newest first)
    for msg in reversed(messages):
        if msg['role'].lower() != 'user':
            continue
            
        content = msg['content']
        if len(content) < 2:
            continue
        
        logger.info(f"📝 Checking: '{content[:50]}...'")
        
        # Try to extract the specific field
        extracted = _extract_by_context(content, field, current_intent, conversation_context)
        if extracted is not None:
            logger.info(f"✅ Found {field} in history: {extracted}")
            return extracted
        
        # Also try multi-field extraction on this message
        # Create temp intent
        temp_intent = current_intent.copy()
        temp_intent = _extract_all_fields(content, temp_intent, conversation_context)
        
        # Check if field is now present
        temp_value = getattr(temp_intent, field, None)
        if temp_value:
            logger.info(f"✅ Found {field} via multi-extract: {temp_value}")
            return temp_value
    
    logger.warning(f"❌ No {field} found in history")
    return None


def _extract_by_context(message: str, field: str, current_intent: BookingIntent, context: str = "") -> Optional[Any]:
    """Extract specific field based on what was asked"""
    
    if field == "service":
        return _extract_service(message)
    
    elif field == "package":
        return _extract_package(message, current_intent.service)
    
    elif field == "name":
        return _extract_name(message)
    
    elif field == "email":
        return _extract_email(message)
    
    elif field == "phone":
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
    """
    IMPROVED: Better multi-field extraction with priority
    """
    # Try to split by common separators
    separators = [',', '，', ';', 'and', '&', 'also', 'with']
    
    segments = []
    for sep in separators:
        if sep in message.lower():
            parts = [p.strip() for p in re.split(sep, message, flags=re.IGNORECASE)]
            if len(parts) > 1:
                segments.extend(parts)
                break
    
    if not segments:
        segments = [message]
    
    # Add full message as segment too
    all_segments = list(set(segments + [message]))
    
    logger.info(f"🔡 Processing {len(all_segments)} segments")
    
    # Track extractions
    extractions = {}
    
    for segment in all_segments:
        if not segment or len(segment) < 2:
            continue
        
        # Check each field type
        # 1. EMAIL (highest confidence)
        if not current_intent.email:
            email = _extract_email(segment)
            if email:
                current_intent.email = email
                extractions['email'] = email
                logger.info(f"📧 Extracted email: {email}")
        
        # 2. PIN CODE (look for explicit patterns)
        if not current_intent.pincode:
            pincode = _extract_pincode(segment)
            if pincode:
                current_intent.pincode = pincode
                extractions['pincode'] = pincode
                logger.info(f"📮 Extracted pincode: {pincode}")
        
        # 3. PHONE
        if not current_intent.phone:
            phone_data = _extract_phone_smart(segment, context)
            if phone_data:
                if isinstance(phone_data, dict):
                    current_intent.phone = phone_data.get('phone')
                    if phone_data.get('phone_country'):
                        current_intent.phone_country = phone_data.get('phone_country')
                    if phone_data.get('service_country'):
                        current_intent.service_country = phone_data.get('service_country')
                else:
                    current_intent.phone = phone_data
                extractions['phone'] = current_intent.phone
                logger.info(f"📱 Extracted phone: {current_intent.phone}")
        
        # 4. NAME
        if not current_intent.name:
            name = _extract_name(segment)
            if name:
                current_intent.name = name
                extractions['name'] = name
                logger.info(f"👤 Extracted name: {name}")
        
        # 5. SERVICE
        if not current_intent.service:
            service = _extract_service(segment)
            if service:
                current_intent.service = service
                extractions['service'] = service
                logger.info(f"💄 Extracted service: {service}")
        
        # 6. PACKAGE (only if we have service)
        if current_intent.service and not current_intent.package:
            package = _extract_package(segment, current_intent.service)
            if package:
                current_intent.package = package
                extractions['package'] = package
                logger.info(f"📦 Extracted package: {package}")
        
        # 7. DATE
        if not current_intent.date:
            date = _extract_date_smart(segment)
            if date:
                current_intent.date = date
                extractions['date'] = date
                logger.info(f"📅 Extracted date: {date}")
        
        # 8. COUNTRY
        if not current_intent.service_country:
            country = _extract_country_smart(segment, context, "service")
            if country:
                current_intent.service_country = country
                extractions['country'] = country
                logger.info(f"🌍 Extracted country: {country}")
        
        # 9. ADDRESS (lower priority - might contain other info)
        if not current_intent.address:
            address = _extract_address(segment)
            if address:
                current_intent.address = address
                extractions['address'] = address[:50] + "..." if len(address) > 50 else address
                logger.info(f"📍 Extracted address: {extractions['address']}")
    
    logger.info(f"✨ Total extractions: {len(extractions)}")
    return current_intent



# ==================== SMART EXTRACTION FUNCTIONS ====================

def _extract_phone_smart(message: str, context: str = "") -> Union[Optional[Dict], Optional[str]]:
    """
    Improved phone extraction with better country detection
    """
    msg = message.strip()
    
    phone = None
    phone_country = None
    service_country = None
    
    # Pattern 1: With explicit country code +91 XXXXXXXXXX
    phone_match = re.search(r'\+(\d{1,3})[\s\-\.]?(\d{10})', msg)
    if phone_match:
        country_code, number = phone_match.groups()
        phone = number
        # Map country code to country
        code_map = {
            '91': 'India', '977': 'Nepal', '92': 'Pakistan', 
            '880': 'Bangladesh', '971': 'Dubai', '1': 'USA'
        }
        phone_country = code_map.get(country_code, 'India')
        logger.info(f"📱 Phone with code +{country_code} → {phone_country}")
    
    # Pattern 2: Country code without + (91XXXXXXXXXX)
    if not phone:
        phone_match = re.search(r'\b(91|977|92|880|971)(\d{10})\b', msg)
        if phone_match:
            country_code, number = phone_match.groups()
            phone = number
            code_map = {'91': 'India', '977': 'Nepal', '92': 'Pakistan', 
                       '880': 'Bangladesh', '971': 'Dubai'}
            phone_country = code_map.get(country_code, 'India')
            logger.info(f"📱 Phone with code {country_code} → {phone_country}")
    
    # Pattern 3: Just 10 digits
    if not phone:
        phone_match = re.search(r'\b(\d{10})\b', msg)
        if phone_match:
            phone = phone_match.group(1)
            logger.info(f"📱 Phone detected: {phone} (no country code)")
    
    # Pattern 4: Formatted phone (XXX-XXX-XXXX or XXX.XXX.XXXX)
    if not phone:
        phone_match = re.search(r'(\d{3}[-\.\s]\d{3}[-\.\s]\d{4})', msg)
        if phone_match:
            digits = re.sub(r'\D', '', phone_match.group(0))
            if len(digits) == 10:
                phone = digits
                logger.info(f"📱 Phone detected (formatted): {phone}")
    
    if not phone:
        return None
    
    # Detect service country from context if available
    if context:
        # Check if country mentioned in recent conversation
        service_country = _extract_country_smart(context, "", "service")
    
    # Default phone country if not detected
    if not phone_country:
        phone_country = "India"
    
    return {
        'phone': phone,
        'phone_country': phone_country,
        'service_country': service_country
    }

def _extract_country_smart(message: str, context: str = "", purpose: str = "service") -> Optional[str]:
    """Improved country extraction"""
    search_text = message.lower()
    if context:
        search_text = (message + " " + context).lower()
    
    # Country patterns
    country_patterns = {
        "India": [r'\bindia\b', r'\bindian\b', r'भारत', r'इंडिया', r'\+91', r'91\d{10}'],
        "Nepal": [r'\bnepal\b', r'\bnepali\b', r'नेपाल', r'\+977', r'977\d{10}'],
        "Pakistan": [r'\bpakistan\b', r'\bpakistani\b', r'पाकिस्तान', r'\+92', r'92\d{10}'],
        "Bangladesh": [r'\bbangladesh\b', r'\bbangladeshi\b', r'बांग्लादेश', r'\+880', r'880\d{10}'],
        "Dubai": [r'\bdubai\b', r'\buae\b', r'\bemirates\b', r'दुबई', r'\+971', r'971\d{10}']
    }
    
    # Service-specific patterns
    if purpose == "service":
        service_patterns = [
            r'service\s+(?:in|for)\s+(\w+)',
            r'makeup\s+(?:in|for)\s+(\w+)',
            r'wedding\s+(?:in|for)\s+(\w+)',
            r'event\s+(?:in|for)\s+(\w+)',
            r'in\s+(\w+)\s+(?:please|plz|for service)',
        ]
        
        for pattern in service_patterns:
            match = re.search(pattern, search_text)
            if match:
                country_name = match.group(1).title()
                if country_name in COUNTRY_CODES:
                    logger.info(f"🌍 Service country from pattern: {country_name}")
                    return country_name
    
    # Check all country patterns
    for country, patterns in country_patterns.items():
        for pattern in patterns:
            if re.search(pattern, search_text):
                logger.info(f"🌍 Country detected: {country}")
                return country
    
    return None

def _extract_date_smart(message: str) -> Optional[str]:
    """Better date extraction with natural language"""
    msg_lower = message.lower()
    
    # Skip if too short
    if len(msg_lower) < 3:
        return None
    
    # Date keywords
    date_keywords = [
        'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
        'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 
        'september', 'october', 'november', 'december',
        'today', 'tomorrow', 'day after', 'next week', 'next month',
        'date', 'schedule', 'on', 'for'
    ]
    
    # Check if has date keywords OR numbers with separators
    has_keywords = any(keyword in msg_lower for keyword in date_keywords)
    has_date_pattern = re.search(r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}', message)
    
    if not (has_keywords or has_date_pattern):
        return None
    
    # Clean message
    msg_clean = re.sub(r'[,，]', ' ', message)
    msg_clean = re.sub(r'\s+', ' ', msg_clean).strip()
    
    # Month mapping
    month_map = {
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
    
    # Try relative dates first
    if 'today' in msg_lower:
        date_obj = datetime.utcnow()
        return date_obj.strftime("%Y-%m-%d")
    
    if 'tomorrow' in msg_lower:
        date_obj = datetime.utcnow() + timedelta(days=1)
        return date_obj.strftime("%Y-%m-%d")
    
    if 'day after tomorrow' in msg_lower or 'day after' in msg_lower:
        date_obj = datetime.utcnow() + timedelta(days=2)
        return date_obj.strftime("%Y-%m-%d")
    
    # Try month-day-year patterns
    for month_name, month_num in month_map.items():
        # Pattern: "5 feb 2026"
        pattern1 = rf'(\d{{1,2}})\s+(?:st|nd|rd|th)?\s*{month_name}\s*(\d{{4}})?'
        # Pattern: "feb 5 2026"
        pattern2 = rf'{month_name}\s+(\d{{1,2}})\s*(?:st|nd|rd|th)?\s*(\d{{4}})?'
        
        for pattern in [pattern1, pattern2]:
            match = re.search(pattern, msg_clean.lower())
            if match:
                groups = match.groups()
                if groups[0] and groups[0].isdigit():
                    day = int(groups[0])
                    year = int(groups[1]) if groups[1] and groups[1].isdigit() else datetime.utcnow().year
                    
                    try:
                        date_obj = datetime(year, month_num, day)
                        return date_obj.strftime("%Y-%m-%d")
                    except ValueError:
                        continue
    
    # Try standard formats
    date_patterns = [
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', 'ymd'),
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', 'dmy'),
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'dmy'),
        (r'(\d{1,2})\.(\d{1,2})\.(\d{4})', 'dmy'),
    ]
    
    for pattern, format_type in date_patterns:
        match = re.search(pattern, message)
        if match:
            try:
                if format_type == 'ymd':
                    year, month, day = map(int, match.groups())
                else:
                    day, month, year = map(int, match.groups())
                
                if year < 100:  # Handle 2-digit years
                    year += 2000 if year < 30 else 1900
                
                date_obj = datetime(year, month, day)
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                continue
    
    return None

def _extract_service(message: str) -> Optional[str]:
    """Extract service with context awareness"""
    msg_lower = message.lower()
    
    # Numeric selection (1, 2, 3, 4)
    num_match = re.search(r'\b([1-4])\b', msg_lower)
    if num_match:
        idx = int(num_match.group(1)) - 1
        services = list(SERVICES.keys())
        if 0 <= idx < len(services):
            result = services[idx]
            logger.info(f"💄 Service selected by number {num_match.group(1)}: {result}")
            return result
    
    # Keyword patterns
    service_patterns = {
        "Bridal Makeup Services": [
            r'bridal', r'bride', r'wedding', r'dulhan', r'shaadi', 
            r'marriage', r'विवाह', r'ब्याह', r'शादी'
        ],
        "Party Makeup Services": [
            r'party', r'function', r'celebration', r'event', 
            r'पार्टी', r'समारोह', r'कार्यक्रम'
        ],
        "Engagement & Pre-Wedding Makeup": [
            r'engagement', r'pre[\s-]?wedding', r'sangeet', 
            r'pre[\s-]?marriage', r'प्री[\s-]?वेडिंग', r'सगाई'
        ],
        "Henna (Mehendi) Services": [
            r'henna', r'mehendi', r'mehndi', r'mehandi',
            r'मेहंदी', r'हिना', r'मेंहदी'
        ]
    }
    
    # Check for "go for 1", "choose 1", "1" in context
    selection_patterns = [
        r'go\s+(?:for|with)\s*([1-4])',
        r'choose\s+([1-4])',
        r'select\s+([1-4])',
        r'pick\s+([1-4])',
        r'want\s+([1-4])',
        r'need\s+([1-4])',
        r'^([1-4])\s*$',
        r'\b([1-4])\b(?:\s+please)?$'
    ]
    
    for pattern in selection_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            idx = int(match.group(1)) - 1
            services = list(SERVICES.keys())
            if 0 <= idx < len(services):
                result = services[idx]
                logger.info(f"💄 Service selected by pattern '{pattern}': {result}")
                return result
    
    # Keyword matching
    for service_name, patterns in service_patterns.items():
        for pattern in patterns:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                logger.info(f"💄 Service detected by keyword: {service_name}")
                return service_name
    
    return None

def _extract_package(message: str, service: str) -> Optional[str]:
    """Extract package with better matching"""
    if not service or service not in SERVICES:
        return None
    
    msg_lower = message.lower()
    packages = list(SERVICES[service]["packages"].keys())
    
    # Numeric selection (1, 2, 3)
    num_match = re.search(r'\b([1-3])\b', msg_lower)
    if num_match:
        idx = int(num_match.group(1)) - 1
        if 0 <= idx < len(packages):
            result = packages[idx]
            logger.info(f"📦 Package selected by number {num_match.group(1)}: {result}")
            return result
    
    # Check for "go for 1", "choose 1" etc.
    selection_patterns = [
        r'go\s+(?:for|with)\s*([1-3])',
        r'choose\s+([1-3])',
        r'select\s+([1-3])',
        r'pick\s+([1-3])',
        r'want\s+([1-3])',
        r'^([1-3])\s*$'
    ]
    
    for pattern in selection_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(packages):
                result = packages[idx]
                logger.info(f"📦 Package selected by pattern '{pattern}': {result}")
                return result
    
    # Keyword matching
    package_keywords = {
        "Chirag's Signature Bridal Makeup": ["signature", "chirag signature", "premium", "99,999", "99999", "first", "1st"],
        "Luxury Bridal Makeup (HD / Brush)": ["luxury", "hd", "brush", "79,999", "79999", "second", "2nd"],
        "Reception / Engagement / Cocktail Makeup": ["reception", "cocktail", "59,999", "59999", "third", "3rd"],
        "Party Makeup by Chirag Sharma": ["chirag", "19,999", "19999", "premium", "first", "1st"],
        "Party Makeup by Senior Artist": ["senior", "6,999", "6999", "basic", "second", "2nd"],
        "Engagement Makeup by Chirag": ["chirag engagement", "premium engagement"],
        "Pre-Wedding Makeup by Senior Artist": ["senior pre-wedding", "basic pre-wedding"],
        "Henna by Chirag Sharma": ["chirag henna", "premium henna", "49,999", "49999"],
        "Henna by Senior Artist": ["senior henna", "basic henna", "19,999", "19999"]
    }
    
    for pkg in packages:
        keywords = package_keywords.get(pkg, [])
        for keyword in keywords:
            if keyword in msg_lower:
                logger.info(f"📦 Package detected by keyword '{keyword}': {pkg}")
                return pkg
    
    return None

def _extract_name(message: str) -> Optional[str]:
    """Better name extraction"""
    msg = message.strip()
    msg_lower = msg.lower()
    
    # Skip if too short or common phrases
    if len(msg) < 2 or msg_lower in ['yes', 'no', 'ok', 'okay', 'sure']:
        return None
    
    # Skip if contains numbers, email, phone
    if re.search(r'\d{5}|@|\+\d|http|www|\.com|\.in', msg_lower):
        return None
    
    # Remove prefixes
    prefixes = ["my name is", "i am", "i'm", "name:", "name is", 
                "this is", "call me", "it's", "its", "मेरो नाम",
                "मैं", "मेरा नाम", "माझं नाव"]
    
    for prefix in prefixes:
        if msg_lower.startswith(prefix):
            msg = msg[len(prefix):].strip()
            break
    
    # Check for proper name pattern
    words = msg.split()
    if len(words) >= 1 and len(words) <= 3:
        # Check if words look like names (capitalized, reasonable length)
        if all(2 <= len(w) <= 20 for w in words):
            # Capitalize properly
            name = ' '.join([w.capitalize() for w in words])
            logger.info(f"👤 Name detected: {name}")
            return name
    
    return None

def _extract_email(message: str) -> Optional[str]:
    """Email extraction"""
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message)
    if email_match:
        email = email_match.group(0)
        logger.info(f"📧 Email detected: {email}")
        return email
    return None

def _extract_address(message: str) -> Optional[str]:
    """Address extraction - more lenient"""
    msg = message.strip()
    msg_lower = msg.lower()
    
    if len(msg) < 5:
        return None
    
    # Skip common phrases
    skip_phrases = ["yes", "no", "ok", "okay", "sure", "correct", "what", 
                   "which", "how", "why", "when", "where"]
    
    if msg_lower in skip_phrases:
        return None
    
    # Remove prefixes
    prefixes = ["address:", "address is", "my address is", "located at", 
                "location:", "i live at", "i live in", "at", "ठेगाना:",
                "पता:", "स्थान:", "address", "पत्ता"]
    
    for prefix in prefixes:
        if msg_lower.startswith(prefix):
            msg = msg[len(prefix):].strip()
            break
    
    # Check for address indicators
    indicators = ['street', 'road', 'lane', 'area', 'sector', 'block', 'house',
                 'flat', 'apartment', 'colony', 'nagar', 'pur', 'village',
                 'town', 'city', 'district', 'state', 'गली', 'मार्ग', 'सड़क',
                 'इलाका', 'क्षेत्र', 'गाँव', 'शहर', 'जिला', 'राज्य']
    
    has_indicator = any(ind in msg_lower for ind in indicators)
    
    # If it has indicators OR is reasonably long, accept as address
    if len(msg) >= 10 or has_indicator or ',' in msg:
        # Make sure it's not a service or other entity
        if not any(word in msg_lower for word in ["bridal", "party", "makeup", "henna", "mehendi", "booking"]):
            logger.info(f"📍 Address detected: {msg[:50]}...")
            return msg[:200]
    
    return None

def _extract_pincode(message: str) -> Optional[str]:
    """
    Robust PIN code extraction
    """
    # Explicit patterns
    explicit_patterns = [
        r'pin\s*code[:\s]+(\d{5,6})',
        r'pincode[:\s]+(\d{5,6})',
        r'postal\s*code[:\s]+(\d{5,6})',
        r'zip[:\s]+(\d{5,6})',
        r'post\s*code[:\s]+(\d{5,6})',
    ]
    
    for pattern in explicit_patterns:
        match = re.search(pattern, message.lower())
        if match:
            pin = match.group(1)
            logger.info(f"📮 PIN detected (explicit): {pin}")
            return pin
    
    # Standalone 5-6 digit numbers
    # Find all 5-6 digit numbers
    all_numbers = re.findall(r'\b(\d{5,6})\b', message)
    
    for pin in all_numbers:
        # Make sure it's not part of a phone number (10 digits)
        # Check surrounding characters
        pin_idx = message.find(pin)
        if pin_idx >= 0:
            # Check if surrounded by more digits (part of longer number)
            start = max(0, pin_idx - 1)
            end = min(len(message), pin_idx + len(pin) + 1)
            
            context = message[start:end]
            # If context has more than 6 digits total, skip
            digits_in_context = re.findall(r'\d', context)
            if len(digits_in_context) <= 6:
                logger.info(f"📮 PIN detected (standalone): {pin}")
                return pin
    
    return None

# ==================== UTILITY FUNCTIONS ====================

def format_phone_for_api(phone: str, country: str = "India") -> str:
    """Format phone for API"""
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
    """Create booking data"""
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
    """Get conversation context"""
    context = []
    
    # Get last 5 messages
    for msg in memory.conversation_history[-5:]:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        context.append(f"{role}: {content}")
    
    return "\n".join(context)


def get_comprehensive_summary(intent: BookingIntent) -> str:
    """Get a comprehensive summary of all collected fields"""
    summary = []
    
    fields = [
        ("service", "💄 Service"),
        ("package", "📦 Package"),
        ("name", "👤 Name"),
        ("email", "📧 Email"),
        ("phone", "📱 Phone"),
        ("phone_country", "📱 Phone Country"),
        ("service_country", "🌍 Service Country"),
        ("address", "📍 Address"),
        ("pincode", "📮 PIN Code"),
        ("date", "📅 Date")
    ]
    
    for field_key, label in fields:
        value = getattr(intent, field_key, None)
        if value:
            # Mask sensitive info for display
            if field_key == "phone" and len(value) >= 10:
                masked = value[:4] + "****" + value[-2:]
                summary.append(f"{label}: {masked}")
            elif field_key == "email":
                # Show email but mask partially
                if "@" in value:
                    parts = value.split("@")
                    if len(parts[0]) > 2:
                        masked_email = parts[0][:2] + "****@" + parts[1]
                        summary.append(f"{label}: {masked_email}")
                    else:
                        summary.append(f"{label}: {value}")
                else:
                    summary.append(f"{label}: {value}")
            else:
                summary.append(f"{label}: {value}")
    
    return "\n".join(summary) if summary else "No information collected yet."