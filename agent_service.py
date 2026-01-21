import json
import logging
import requests
import re
from typing import Tuple, List, Dict, Any
import time
from config import GROQ_API_KEY, LANGUAGE_MAP, COUNTRY_CODES
from agent_models import BookingIntent, ConversationMemory
from services import load_knowledge_from_db

logger = logging.getLogger(__name__)

# ==========================================================
# KNOWLEDGE BASE - Service & Package Information
# ==========================================================

SERVICES = {
    "bridal": {
        "name": "Bridal Makeup Services",
        "packages": {
            "1": "Chirag's Signature Bridal Makeup",
            "2": "Luxury Bridal Makeup (HD / Brush)",
            "3": "Reception / Engagement / Cocktail Makeup"
        },
        "prices": {
            "Chirag's Signature Bridal Makeup": "₹99,999",
            "Luxury Bridal Makeup (HD / Brush)": "₹79,999",
            "Reception / Engagement / Cocktail Makeup": "₹59,999"
        }
    },
    "party": {
        "name": "Party Makeup Services",
        "packages": {},
        "prices": {}
    },
    "engagement": {
        "name": "Engagement & Pre-Wedding Makeup",
        "packages": {},
        "prices": {}
    },
    "henna": {
        "name": "Henna (Mehendi) Services",
        "packages": {},
        "prices": {}
    }
}

def get_intent_extraction_prompt(language: str) -> str:
    """Prompt for extracting booking information from conversation"""
    language_name = LANGUAGE_MAP.get(language, "English")
    
    return f"""
You are an expert information extractor for a makeup artist booking system.

TASK: Extract booking information from the user's message in {language_name}.

AVAILABLE SERVICES:
- Bridal Makeup Services
- Party Makeup Services
- Engagement & Pre-Wedding Makeup
- Henna (Mehendi) Services

AVAILABLE PACKAGES FOR BRIDAL:
1. Chirag's Signature Bridal Makeup
2. Luxury Bridal Makeup (HD / Brush)
3. Reception / Engagement / Cocktail Makeup

FIELDS TO EXTRACT:
- service: The makeup service (choose from available services above)
- package: The package type (choose from available packages if service is bridal)
- name: Customer's full name
- email: Customer's email address (if provided)
- phone: Phone number (10 digits)
- phone_country: Country for phone (India, Nepal, Pakistan, Bangladesh, Dubai)
- service_country: Country where service will be provided
- address: Full address where service is needed
- pincode: Postal/PIN code
- date: Preferred date for service (format: YYYY-MM-DD)
- message: Any additional message

COUNTRY CODES: {', '.join(COUNTRY_CODES.keys())}

RULES:
1. Extract ONLY information explicitly mentioned by the user
2. Do NOT invent or assume information
3. Return ONLY valid JSON, no extra text
4. Use null for fields not mentioned
5. For dates, try to parse to YYYY-MM-DD format
6. Clean phone numbers: keep only digits

RESPONSE FORMAT (JSON only):
{{
  "service": "value or null",
  "package": "value or null",
  "name": "value or null",
  "email": "value or null",
  "phone": "value or null",
  "phone_country": "value or null",
  "service_country": "value or null",
  "address": "value or null",
  "pincode": "value or null",
  "date": "value or null",
  "message": "value or null"
}}
"""

def get_agent_system_prompt(language: str, memory: ConversationMemory) -> str:
    """Generate agent system prompt with memory context"""
    language_name = LANGUAGE_MAP.get(language, "English")
    website_content = load_knowledge_from_db(language)
    
    intent = memory.intent
    missing = get_missing_fields(intent)
    
    collected_info = f"""
COLLECTED INFORMATION SO FAR:
- Service: {intent.service or "Not provided"}
- Package: {intent.package or "Not provided"}
- Name: {intent.name or "Not provided"}
- Email: {intent.email or "Not provided"}
- Phone: {intent.phone or "Not provided"}
- Phone Country: {intent.phone_country or "Not provided"}
- Service Country: {intent.service_country or "Not provided"}
- Address: {intent.address or "Not provided"}
- Pincode: {intent.pincode or "Not provided"}
- Date: {intent.date or "Not provided"}
- Message: {intent.message or "Not provided"}

MISSING INFORMATION: {', '.join(missing) if missing else "All information collected!"}
CURRENT STAGE: {memory.stage}
"""
    
    # Build service options text
    service_options = "\n".join([f"- {service['name']}" for service in SERVICES.values()])
    
    return f"""
You are an AI booking assistant for "JinniChirag Makeup Artist". You help users book makeup services through conversation.

RESPOND ONLY IN: {language_name}

CONVERSATION STAGES:
1. greeting - Welcome user, understand their needs
2. collecting_info - Gather all required booking information
3. otp_sent - OTP has been sent, waiting for user to provide it
4. otp_verification - Verify the OTP provided by user
5. confirmed - Booking confirmed

YOUR CURRENT TASK:
{collected_info}

AVAILABLE SERVICES:
{service_options}

BEHAVIOR RULES:
1. Be conversational, friendly, and professional
2. Ask for ONE piece of information at a time naturally
3. When user provides info, acknowledge it briefly and ask for next needed item
4. DO NOT ask for information already collected
5. DO NOT send OTP until ALL information is collected
6. When all info is ready, inform user you'll send OTP to their WhatsApp
7. Phone numbers should be in international format with country code
8. Available countries: {', '.join(COUNTRY_CODES.keys())}
9. If user provides OTP, simply repeat the 6-digit number back to confirm
10. DO NOT invent prices or package details - use only what's provided
11. If user asks about packages, list available packages for their selected service
12. If user provides "My details are:" with multiple fields, extract all information

CRITICAL:
- NEVER invent prices, dates, or contact information
- ONLY use information from website content
- If info is not in website content, say you don't have that information
- When user provides multiple pieces of information at once, acknowledge all of them
"""

def extract_intent_from_message(message: str, language: str, current_intent: BookingIntent) -> BookingIntent:
    """Extract booking information from user message"""
    
    # Use manual extraction to reduce API calls
    updated_intent = current_intent.copy()
    msg_lower = message.lower()
    
    # Extract service type
    if "bridal" in msg_lower or "bride" in msg_lower or "wedding" in msg_lower:
        updated_intent.service = "Bridal Makeup Services"
    elif "party" in msg_lower:
        updated_intent.service = "Party Makeup Services"
    elif "engagement" in msg_lower or "pre-wedding" in msg_lower:
        updated_intent.service = "Engagement & Pre-Wedding Makeup"
    elif "henna" in msg_lower or "mehendi" in msg_lower:
        updated_intent.service = "Henna (Mehendi) Services"
    
    # Extract package (for bridal)
    if "signature" in msg_lower or "chirag" in msg_lower or "99" in msg_lower or "1." in msg_lower:
        updated_intent.package = "Chirag's Signature Bridal Makeup"
    elif "luxury" in msg_lower or "hd" in msg_lower or "brush" in msg_lower or "79" in msg_lower or "2." in msg_lower:
        updated_intent.package = "Luxury Bridal Makeup (HD / Brush)"
    elif "reception" in msg_lower or "cocktail" in msg_lower or "59" in msg_lower or "3." in msg_lower:
        updated_intent.package = "Reception / Engagement / Cocktail Makeup"
    
    # Extract name (look for name patterns)
    if not updated_intent.name:
        # Pattern: "Name: XYZ" or "My name is XYZ" or just a name at the beginning
        name_patterns = [
            r'(?:name|naam)[:\s]+([a-zA-Z\s\.]+)(?:\n|$)',
            r'my name is\s+([a-zA-Z\s\.]+)(?:\n|$)',
            r'^([a-zA-Z\s\.]{3,40})$'
        ]
        
        for pattern in name_patterns:
            name_match = re.search(pattern, message, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 2:  # Valid name
                    updated_intent.name = name
                    break
    
    # Extract email
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message)
    if email_match:
        updated_intent.email = email_match.group(0)
    
    # Extract phone number (10 digits)
    phone_match = re.search(r'(\+?91)?[ -]?(\d{10})\b', message)
    if phone_match:
        updated_intent.phone = phone_match.group(2)
        if not updated_intent.phone_country:
            # Try to infer from context
            if "nepal" in msg_lower:
                updated_intent.phone_country = "Nepal"
            else:
                updated_intent.phone_country = "India"  # Default
    
    # Extract pincode (5-6 digits)
    pin_match = re.search(r'\b(\d{5,6})\b', message)
    if pin_match:
        updated_intent.pincode = pin_match.group(1)
    
    # Extract date (try multiple formats)
    date_patterns = [
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
        r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})',
        r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
        r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})'
    ]
    
    for pattern in date_patterns:
        date_match = re.search(pattern, msg_lower, re.IGNORECASE)
        if date_match:
            try:
                groups = date_match.groups()
                if len(groups) == 3:
                    if pattern in [date_patterns[1], date_patterns[3]]:  # "2nd jan 2026" or "2 jan 2026"
                        day, month_str, year = groups
                        month_map = {
                            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                        }
                        month = month_map.get(month_str[:3].lower(), '01')
                        updated_intent.date = f"{year}-{month}-{str(day).zfill(2)}"
                    else:
                        # DD-MM-YYYY or YYYY-MM-DD
                        if len(groups[0]) == 4:  # YYYY-MM-DD
                            updated_intent.date = f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}"
                        else:  # DD-MM-YYYY
                            updated_intent.date = f"{groups[2]}-{groups[1].zfill(2)}-{groups[0].zfill(2)}"
                break
            except Exception as e:
                logger.warning(f"Date parsing error: {e}")
                continue
    
    # Extract address/country
    country_patterns = {
        "india": "India",
        "nepal": "Nepal", 
        "pakistan": "Pakistan",
        "bangladesh": "Bangladesh",
        "dubai": "Dubai"
    }
    
    for pattern, country in country_patterns.items():
        if pattern in msg_lower:
            if not updated_intent.service_country:
                updated_intent.service_country = country
            if not updated_intent.phone_country and updated_intent.phone:
                updated_intent.phone_country = country
            break
    
    # Extract address (look for location mentions after keywords)
    address_keywords = ["address", "location", "city", "live in", "from", "at"]
    for keyword in address_keywords:
        if keyword in msg_lower:
            # Try to extract text after the keyword
            pattern = fr'{keyword}[:\s]+([^,\n]+)'
            addr_match = re.search(pattern, msg_lower, re.IGNORECASE)
            if addr_match and not updated_intent.address:
                updated_intent.address = addr_match.group(1).strip()
                break
    
    # Common city detection
    cities = ["biratnagar", "morang", "pune", "mumbai", "delhi", "kathmandu"]
    for city in cities:
        if city in msg_lower and not updated_intent.address:
            updated_intent.address = city.title()
            if city in ["biratnagar", "morang", "kathmandu"] and not updated_intent.service_country:
                updated_intent.service_country = "Nepal"
            break
    
    # Extract message/notes
    if "message" in msg_lower or "note" in msg_lower or "request" in msg_lower:
        # Try to extract after keyword
        msg_pattern = r'(?:message|note|request)[:\s]+(.+)'
        msg_match = re.search(msg_pattern, msg_lower, re.IGNORECASE)
        if msg_match and not updated_intent.message:
            updated_intent.message = msg_match.group(1).strip()
    
    # Only use AI extraction if we have complex multi-line text
    lines = message.strip().split('\n')
    if len(lines) > 2 or (len(message.split()) > 8 and not all(field for field in [
        updated_intent.service, updated_intent.package, updated_intent.name,
        updated_intent.email, updated_intent.phone, updated_intent.date
    ])):
        return ai_extract_intent(message, language, updated_intent)
    
    return updated_intent

def ai_extract_intent(message: str, language: str, current_intent: BookingIntent) -> BookingIntent:
    """Use AI to extract intent (with retry logic)"""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": get_intent_extraction_prompt(language)},
                        {"role": "user", "content": f"Current data: {current_intent.dict()}\n\nNew message: {message}"}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500
                },
                timeout=10,
            )
            
            if response.status_code == 429:
                wait_time = 2 ** (attempt + 1)  # Exponential backoff
                time.sleep(wait_time)
                continue
            elif response.status_code != 200:
                logger.error(f"GROQ API error: {response.status_code}")
                return current_intent
            
            data = response.json()
            extracted_text = data["choices"][0]["message"]["content"].strip()
            
            # Clean JSON
            if "```json" in extracted_text:
                extracted_text = extracted_text.split("```json")[1].split("```")[0].strip()
            elif "```" in extracted_text:
                extracted_text = extracted_text.split("```")[1].split("```")[0].strip()
            
            # Find JSON
            start = extracted_text.find("{")
            end = extracted_text.rfind("}") + 1
            if start != -1 and end > start:
                extracted_text = extracted_text[start:end]
            
            try:
                extracted_data = json.loads(extracted_text)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}, text: {extracted_text[:100]}")
                return current_intent
            
            # Merge with current intent (only update if new value is not None and not empty)
            for key, value in extracted_data.items():
                if value is not None and value != "" and hasattr(current_intent, key):
                    # Clean up the value
                    if isinstance(value, str):
                        value = value.strip()
                        if value.lower() == "null" or value.lower() == "none":
                            continue
                    
                    # Special handling for phone: keep only digits
                    if key == "phone" and value:
                        value = re.sub(r'\D', '', value)
                        if len(value) == 10:
                            setattr(current_intent, key, value)
                    else:
                        setattr(current_intent, key, value)
            
            return current_intent
            
        except requests.exceptions.Timeout:
            logger.error(f"AI extraction timeout on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                return current_intent
        except Exception as e:
            logger.error(f"AI extraction attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                return current_intent
            time.sleep(1)
    
    return current_intent

def get_missing_fields(intent: BookingIntent) -> List[str]:
    """Get list of required fields that are still missing"""
    required = [
        ("service", "service type"),
        ("package", "package"),
        ("name", "name"),
        ("email", "email"),
        ("phone", "phone number"),
        ("phone_country", "phone country"),
        ("service_country", "service country"),
        ("address", "address"),
        ("pincode", "pincode"),
        ("date", "preferred date"),
    ]
    
    missing = []
    for field, label in required:
        if not getattr(intent, field):
            missing.append(label)
    
    return missing

def generate_agent_response(
    user_message: str,
    memory: ConversationMemory,
    language: str
) -> Tuple[str, ConversationMemory, str]:
    """Generate conversational response while managing booking state"""
    
    # Extract intent from user message
    memory.intent = extract_intent_from_message(user_message, language, memory.intent)
    
    # Check for OTP input
    if memory.stage == "otp_sent":
        otp_match = re.search(r'\b\d{6}\b', user_message)
        if otp_match:
            memory.stage = "otp_verification"
            return otp_match.group(0), memory, "verify_otp"
    
    # Check if all information is collected
    missing_fields = get_missing_fields(memory.intent)
    
    # Special handling for package selection when service is bridal
    intent = memory.intent
    if intent.service == "Bridal Makeup Services" and not intent.package:
        # Ask for package
        reply = (
            "For Bridal Makeup Services, we offer the following packages:\n"
            "1. Chirag's Signature Bridal Makeup: ₹99,999\n"
            "2. Luxury Bridal Makeup (HD / Brush): ₹79,999\n"
            "3. Reception / Engagement / Cocktail Makeup: ₹59,999\n\n"
            "Please let me know which package you're interested in (1, 2, or 3)."
        )
        memory.conversation_history.append({"role": "user", "content": user_message})
        memory.conversation_history.append({"role": "assistant", "content": reply})
        return reply, memory, "continue"
    
    # If all required info is collected, move to OTP stage
    if not missing_fields and memory.stage == "collecting_info":
        memory.stage = "otp_sent"
        confirmation_msg = build_otp_confirmation_message(memory.intent, language)
        # Clear conversation history for OTP stage to keep it clean
        memory.conversation_history = []
        return confirmation_msg, memory, "send_otp"
    
    # Generate AI response
    return generate_ai_response(user_message, memory, language, missing_fields)

def build_otp_confirmation_message(intent: BookingIntent, language: str) -> str:
    """Build confirmation message before sending OTP"""
    
    # Format phone for display
    phone_display = ""
    if intent.phone:
        country_code = COUNTRY_CODES.get(intent.phone_country, "+91")
        phone_display = f"{country_code}{intent.phone}"
    
    messages = {
        "en": f"""
✅ Perfect! I have all your details:

• Service: {intent.service}
• Package: {intent.package}
• Name: {intent.name}
• Email: {intent.email}
• Phone: {phone_display}
• Service Country: {intent.service_country}
• Address: {intent.address}
• Pincode: {intent.pincode}
• Date: {intent.date}
• Message: {intent.message or "None"}

I'll now send a 6-digit OTP to your WhatsApp number for verification.
Please provide the OTP once you receive it.
""",
        "ne": f"""
✅ उत्तम! मसँग तपाईंको सबै विवरणहरू छन्:

• सेवा: {intent.service}
• प्याकेज: {intent.package}
• नाम: {intent.name}
• इमेल: {intent.email}
• फोन: {phone_display}
• सेवा देश: {intent.service_country}
• ठेगाना: {intent.address}
• पिनकोड: {intent.pincode}
• मिति: {intent.date}
• सन्देश: {intent.message or "कुनै पनि होईन"}

म अब तपाईंको व्हाट्सएप नम्बरमा प्रमाणीकरणको लागि ६-अंकको OTP पठाउँछु।
कृपया OTP प्राप्त भएपछि यहाँ प्रदान गर्नुहोस्।
""",
        "hi": f"""
✅ बिल्कुल सही! मेरे पास आपकी सभी जानकारी है:

• सेवा: {intent.service}
• पैकेज: {intent.package}
• नाम: {intent.name}
• ईमेल: {intent.email}
• फोन: {phone_display}
• सेवा देश: {intent.service_country}
• पता: {intent.address}
• पिनकोड: {intent.pincode}
• तारीख: {intent.date}
• संदेश: {intent.message or "कोई नहीं"}

म अब आपके व्हाट्सएप नंबर पर सत्यापन के लिए 6-अंकीय OTP भेजूंगा।
कृपया OTP प्राप्त होने के बाद यहाँ प्रदान करें।
""",
        "mr": f"""
✅ परफेक्ट! माझ्याकडे तुमची सर्व माहिती आहे:

• सेवा: {intent.service}
• पॅकेज: {intent.package}
• नाव: {intent.name}
• ईमेल: {intent.email}
• फोन: {phone_display}
• सेवा देश: {intent.service_country}
• पत्ता: {intent.address}
• पिनकोड: {intent.pincode}
• तारीख: {intent.date}
• संदेश: {intent.message or "काहीही नाही"}

मी आता तुमच्या व्हाट्सअॅप नंबरवर सत्यापनासाठी 6-अंकी OTP पाठवेन.
कृपया OTP प्राप्त झाल्यावर येथे प्रदान करा।
"""
    }
    return messages.get(language, messages["en"])

def generate_ai_response(user_message: str, memory: ConversationMemory, language: str, missing_fields: List[str]) -> Tuple[str, ConversationMemory, str]:
    """Generate AI response with retry logic"""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            system_prompt = get_agent_system_prompt(language, memory)
            
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add conversation history (last 4 exchanges)
            history = memory.conversation_history[-8:] if memory.conversation_history else []
            for msg in history:
                messages.append(msg)
            
            messages.append({"role": "user", "content": user_message})
            
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 500
                },
                timeout=15,
            )
            
            if response.status_code == 429:
                wait_time = 2 ** (attempt + 1)
                time.sleep(wait_time)
                continue
            elif response.status_code != 200:
                logger.error(f"GROQ API error: {response.status_code}")
                return handle_ai_failure(user_message, memory, missing_fields, language)
            
            data = response.json()
            if "choices" not in data or not data["choices"]:
                logger.error("No choices in AI response")
                return handle_ai_failure(user_message, memory, missing_fields, language)
                
            reply = data["choices"][0]["message"]["content"]
            
            # Update conversation history
            memory.conversation_history.append({"role": "user", "content": user_message})
            memory.conversation_history.append({"role": "assistant", "content": reply})
            
            # Limit conversation history to prevent token overflow
            if len(memory.conversation_history) > 20:
                memory.conversation_history = memory.conversation_history[-10:]
            
            return reply, memory, "continue"
            
        except requests.exceptions.Timeout:
            logger.error(f"AI response timeout on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                return handle_ai_failure(user_message, memory, missing_fields, language)
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            if attempt == max_retries - 1:
                return handle_ai_failure(user_message, memory, missing_fields, language)
            time.sleep(1)
    
    return handle_ai_failure(user_message, memory, missing_fields, language)

def handle_ai_failure(user_message: str, memory: ConversationMemory, missing_fields: List[str], language: str) -> Tuple[str, ConversationMemory, str]:
    """Fallback when AI fails"""
    
    intent = memory.intent
    
    if not missing_fields:
        fallback = "Great! I have all your details. Let me send an OTP to your WhatsApp for verification."
    elif len(missing_fields) == 1:
        field = missing_fields[0]
        questions = {
            "service type": "What type of service are you interested in? (Bridal, Party, Engagement, or Henna)",
            "package": "Which package would you like?",
            "name": "What is your full name?",
            "email": "What is your email address?",
            "phone number": "What is your phone number? (10 digits)",
            "phone country": "Which country is your phone number from? (India, Nepal, etc.)",
            "service country": "In which country will the service be provided?",
            "address": "What is the service address?",
            "pincode": "What is the pincode/postal code?",
            "preferred date": "What is your preferred date? (Format: DD-MM-YYYY or YYYY-MM-DD)"
        }
        fallback = questions.get(field, f"Could you please provide your {field}?")
    else:
        # Prioritize the most important missing fields
        priority_fields = ["service type", "name", "phone number", "email", "date"]
        priority_missing = [f for f in missing_fields if f in priority_fields]
        if priority_missing:
            fallback = f"I still need: {', '.join(priority_missing[:2])}. Could you provide them?"
        else:
            fallback = f"I still need: {', '.join(missing_fields[:3])}. Could you provide them?"
    
    # Language translations
    if language == "ne":
        fallback = "कृपया आफ्नो विवरण प्रदान गर्नुहोस्।"
    elif language == "hi":
        fallback = "कृपया अपना विवरण प्रदान करें।"
    elif language == "mr":
        fallback = "कृपया तुमचा तपशील द्या."
    
    memory.conversation_history.append({"role": "user", "content": user_message})
    memory.conversation_history.append({"role": "assistant", "content": fallback})
    
    return fallback, memory, "continue"

def format_phone_with_country_code(phone: str, country: str) -> str:
    """Format phone number with country code"""
    if not phone:
        return ""
    
    # Clean phone number - keep only digits
    phone = re.sub(r'\D', '', phone)
    
    if not phone:
        return ""
    
    # If already has country code (starts with country code)
    country_code = COUNTRY_CODES.get(country, "+91")
    
    # Remove leading zeros and existing country code
    if phone.startswith(country_code.replace('+', '')):
        return f"+{phone}"
    elif len(phone) == 10:
        return f"{country_code}{phone}"
    elif len(phone) > 10:
        # Might already have country code
        return f"+{phone}"
    else:
        # Invalid length
        return f"{country_code}{phone}"