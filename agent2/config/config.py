"""
Configuration file for JinniChirag Backend
"""

import os
import re  # Add this import
from typing import List, Dict, Any, Tuple, Optional, Callable
from dotenv import load_dotenv
# Load environment variables
load_dotenv()

__version__ = "4.0.0"

# ==================== CORE SETTINGS ====================

SUPPORTED_LANGUAGES = ["en", "ne", "hi", "mr"]
LANGUAGE_NAMES = {
    "en": "English",
    "ne": "Nepali",
    "hi": "Hindi",
    "mr": "Marathi"
}

DEFAULT_LANGUAGE = "en"


# ==================== KNOWLEDGE BASE SETTINGS ====================

# Knowledge Base Language Instructions
KB_LANGUAGE_INSTRUCTIONS = {
    "en": "Answer in English naturally and concisely. Keep it short (2-3 sentences max).",
    "hi": "Answer in Hindi (Devanagari script) naturally and concisely. Keep it short (2-3 sentences max).",
    "ne": "Answer in Nepali (Devanagari script) naturally and concisely. Keep it short (2-3 sentences max).",
    "mr": "Answer in Marathi (Devanagari script) naturally and concisely. Keep it short (2-3 sentences max)."
}

# Knowledge Base Answer Cleaning
KB_UNWANTED_PREFIXES = [
    "According to the knowledge base",
    "Based on the information",
    "As per the knowledge base",
    "The knowledge base states",
    "From the knowledge base",
    "According to",
    "Based on"
]

# Knowledge Base API Settings
KB_API_SETTINGS = {
    "endpoint": "https://api.groq.com/openai/v1/chat/completions",
    "max_tokens_with_kb": 150,
    "max_tokens_without_kb": 120,
    "system_role": "You are a helpful assistant for Chirag Sharma's celebrity makeup artist booking service."
}

# KB System Prompt Template
KB_SYSTEM_PROMPT_TEMPLATE = """You are Chirag Sharma, a celebrity makeup artist and bridal makeup specialist.

{language_instruction}

**About Services:**
{services_info}

**Current Context:**
{context}

**Guidelines:**
1. Keep answers concise (1-2 sentences)
2. Be professional and helpful
3. If user asks off-topic questions, answer briefly and gently guide back to booking
4. Never make up prices or services
5. If unsure, suggest contacting for more details
6. Always respond in {language_name}

Current task: {current_state}"""



# ✅ ADD ENTIRE NEW SECTION:
# Service Health & Monitoring Settings
SERVICE_HEALTH_SETTINGS = {
    "enable_stats_tracking": True,
    "stats_reset_interval_hours": 24,
    "log_level": "INFO",
    "enable_performance_logging": True
}

# ==================== ENVIRONMENT VARIABLES ====================

# Groq AI Settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")

# Rate limiting
GROQ_RATE_LIMIT = int(os.getenv("GROQ_RATE_LIMIT", "30"))  # requests per minute
GROQ_RETRY_DELAY = int(os.getenv("GROQ_RETRY_DELAY", "2"))  # seconds

# MongoDB Settings
MONGO_URI = os.getenv(
    "MONGO_URI"
)

# Frontend URL
FRONTEND_URL = os.getenv("FRONTEND_URL")

# JWT Secret
JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-jwt-key-change-this-to-something-random")

# Twilio/WhatsApp Settings
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")

# Brevo Email Settings
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

# Server Settings
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# ==================== CORS CONFIGURATION ====================

CORS_ORIGINS = [
    FRONTEND_URL,
    "http://localhost:5173",
    "http://localhost:5174",
    "https://sharmachirag.vercel.app",
    "https://sharmachiragadmin.vercel.app",
]

# ==================== TWILIO CONFIGURATION ====================

TWILIO_CONFIG = {
    "account_sid": TWILIO_ACCOUNT_SID,
    "auth_token": TWILIO_AUTH_TOKEN,
    "whatsapp_from": TWILIO_WHATSAPP_FROM,
    "enabled": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)
}

# ==================== BREVO EMAIL CONFIGURATION ====================

BREVO_CONFIG = {
    "api_key": BREVO_API_KEY,
    "enabled": bool(BREVO_API_KEY),
    "sender_email": "noreply@jinnichirag.com",
    "sender_name": "JinniChirag"
}

# ==================== GROQ AI CONFIGURATION ====================

GROQ_CONFIG = {
    "api_key": GROQ_API_KEY,
    "model": GROQ_MODEL,
    "api_url": GROQ_API_URL,
    "rate_limit": GROQ_RATE_LIMIT,
    "retry_delay": GROQ_RETRY_DELAY,
    "enabled": bool(GROQ_API_KEY)
}
# ==================== DATABASE CONFIGURATION ====================

DATABASE_CONFIG = {
    "uri": MONGO_URI,
    "db_name": "jinnichirag_db",
    "collections": {
        "bookings": "bookings",
        "users": "users",
        "admin": "admin",
        "knowledge_base": "knowledge_base",
        "analytics": "analytics",
        "sessions": "sessions"
    }
}

# ==================== LOGGING CONFIGURATION ====================

LOGGING_CONFIG = {
    "level": os.getenv("LOG_LEVEL", "INFO"),
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "date_format": "%Y-%m-%d %H:%M:%S"
}

# ==================== FEATURE FLAGS ====================

FEATURE_FLAGS = {
    "enable_whatsapp": TWILIO_CONFIG["enabled"],
    "enable_email": BREVO_CONFIG["enabled"],
    "enable_ai_chat": GROQ_CONFIG["enabled"],
    "enable_analytics": True,
    "enable_knowledge_base": True,
    "enable_multi_language": True
}

# ==================== SERVICE CONFIGURATION ====================

SERVICES = {
    "Bridal Makeup Services": {
        "packages": {
            "Chirag's Signature Bridal Makeup": "₹99,999",
            "Luxury Bridal Makeup (HD / Brush)": "₹79,999",
            "Reception / Engagement / Cocktail Makeup": "₹59,999"
        },
        "description": "Premium bridal makeup by Chirag Sharma, customized for weddings",
        "keywords": [
            'bridal', 'bride', 'wedding', 'marriage', 'shaadi',
            'dulhan', 'wedding makeup', 'bridal makeup'
        ],
        "package_keywords": {
            "Chirag's Signature Bridal Makeup": ['signature', 'chirag', 'premium', 'chirag\'s'],
            "Luxury Bridal Makeup (HD / Brush)": ['luxury', 'hd', 'brush', 'high definition'],
            "Reception / Engagement / Cocktail Makeup": ['reception', 'cocktail', 'engagement']
        }
    },
    "Party Makeup Services": {
        "packages": {
            "Party Makeup by Chirag Sharma": "₹19,999",
            "Party Makeup by Senior Artist": "₹6,999"
        },
        "description": "Makeup for parties, receptions, and special occasions",
        "keywords": [
            'party', 'function', 'celebration', 'event',
            'party makeup', 'occasion', 'gathering'
        ],
        "package_keywords": {
            "Party Makeup by Chirag Sharma": ['chirag', 'premium'],
            "Party Makeup by Senior Artist": ['senior', 'artist', 'economy', 'budget']
        }
    },
    "Engagement & Pre-Wedding Makeup": {
        "packages": {
            "Engagement Makeup by Chirag": "₹59,999",
            "Pre-Wedding Makeup by Senior Artist": "₹19,999"
        },
        "description": "Makeup for engagement and pre-wedding functions",
        "keywords": [
            'engagement', 'pre-wedding', 'pre wedding', 'sangeet',
            'mehendi', 'cocktail', 'engagement makeup',
            'engagement ceremony', 'ring ceremony'
        ],
        "package_keywords": {
            "Engagement Makeup by Chirag": ['chirag', 'premium'],
            "Pre-Wedding Makeup by Senior Artist": ['senior', 'artist']
        }
    },
    "Henna (Mehendi) Services": {
        "packages": {
            "Henna by Chirag Sharma": "₹49,999",
            "Henna by Senior Artist": "₹19,999"
        },
        "description": "Henna services for bridal and special occasions",
        "keywords": [
            'henna', 'mehendi', 'mehndi', 'henna art',
            'bridal henna', 'mehandi', 'mendhi'
        ],
        "package_keywords": {
            "Henna by Chirag Sharma": ['chirag', 'premium'],
            "Henna by Senior Artist": ['senior', 'artist', 'economy']
        }
    }
}

# Service utilities
SERVICE_LIST = list(SERVICES.keys())
SERVICE_NUMBER_MAP = {i+1: service for i, service in enumerate(SERVICE_LIST)}

# ==================== COUNTRY CONFIGURATIONS ====================

COUNTRIES = ["India", "Nepal", "Pakistan", "Bangladesh", "Dubai"]
COUNTRY_CODES = {
    "India": "+91",
    "Nepal": "+977", 
    "Pakistan": "+92",
    "Bangladesh": "+880",
    "Dubai": "+971"
}

COUNTRY_PHONE_PATTERNS = {
    "India": r'^\+91[6-9]\d{9}$',
    "Nepal": r'^\+977[9]\d{8}$',
    "Pakistan": r'^\+92[3]\d{9}$',
    "Bangladesh": r'^\+880[1]\d{9}$',
    "Dubai": r'^\+971[5]\d{8}$'
}

COUNTRY_PINCODE_LENGTHS = {
    "India": 6,
    "Nepal": 5,
    "Pakistan": 5,
    "Bangladesh": 4,
    "Dubai": 5
}

# ==================== SYSTEM SETTINGS ====================
AGENT_SETTINGS = {
    "max_sessions": 1000,
    "session_ttl_hours": 2,
    "max_history_messages": 20,
    "otp_expiry_minutes": 5,
    "max_otp_attempts": 3,
    "max_off_track_attempts": 6,
    "rate_limit_per_minute": 10,
    "cleanup_interval_seconds": 300,
    "default_language": "en",
    "max_consecutive_questions": 3,
    # ✅ ADD THESE 4 NEW SETTINGS:
    "kb_cache_ttl_minutes": 30,           # Knowledge base cache TTL
    "otp_cleanup_interval_seconds": 300,  # OTP cleanup interval (5 min)
    "memory_cleanup_interval_seconds": 300, # Memory cleanup interval (5 min)
    "max_off_topic_attempts": 5,          # Off-topic attempts before chat mode
    # Rate Limiting
    "rate_limit_per_minute": GROQ_RATE_LIMIT,
    "retry_delay_seconds": GROQ_RETRY_DELAY,
    # Add these if not present:
    "kb_response_timeout": 10,           # KB API timeout in seconds
    "enable_kb_fallback": True,          # Enable KB fallback responses
}

LLM_SETTINGS = {
    "model": "llama-3.1-8b-instant",
    "temperature": 0.4,
    "max_tokens": 300,
    "timeout": 15,
    "max_retries": 3,
    # ✅ ADD THIS NEW SETTING:
    "kb_max_retries": 2  # Knowledge base API retry count
}

# ==================================================
# ADVANCED PHONE EXTRACTION PATTERNS (INDIA + NEPAL + GLOBAL)
# ==================================================

PHONE_PATTERNS = {

    # -------------------------------------------------
    # 1. India (with or without country code)
    # +91 9876543210 | 091-9876543210 | 9876543210
    # -------------------------------------------------
    "india": r'''
        (?:
            (?:\+91|91|0)\s*[-.\s]?
        )?
        ([6-9]\d{9})
        \b
    ''',

    # -------------------------------------------------
    # 2. Nepal (mobile numbers)
    # +977 98xxxxxxxx | 98xxxxxxxx | 0-98xxxxxxxx
    # -------------------------------------------------
    "nepal": r'''
        (?:
            (?:\+977|977|0)\s*[-.\s]?
        )?
        (9[6-9]\d{7})
        \b
    ''',

    # -------------------------------------------------
    # 3. Explicit WhatsApp mention
    # "whatsapp +91 98765 43210"
    # -------------------------------------------------
    "whatsapp": r'''
        \b(?:whatsapp|wa|w\.a\.|whats\s*app)\b
        [\s:\-]*
        ([+\d][\d\s\-().]{9,})
    ''',

    # -------------------------------------------------
    # 4. Labeled numbers
    # phone:, mobile:, contact:
    # -------------------------------------------------
    "labeled": r'''
        \b(?:phone|mobile|contact|number|फोन|मोबाइल|नंबर|नम्बर)\b
        [\s:\-]*
        ([+\d][\d\s\-().]{9,})
    ''',

    # -------------------------------------------------
    # 5. Bracketed / formatted numbers
    # (987) 654-3210 | (98) 76543210
    # -------------------------------------------------
    "formatted": r'''
        \(
        (\d{2,4})
        \)
        [\s\-\.]*
        (\d{6,10})
    ''',

    # -------------------------------------------------
    # 6. Generic international (strict + required)
    # +971 50 123 4567 | +44 7700 900123
    # -------------------------------------------------
    "international": r'''
        \+
        (\d{1,3})
        [\s\-\.]*
        (\d{6,12})
        \b
    ''',

    # -------------------------------------------------
    # 7. Plain long digits fallback
    # (Used ONLY if others fail)
    # -------------------------------------------------
    "fallback": r'''
        \b
        ([6-9]\d{9}|9\d{8}|\d{10,15})
        \b
    ''',
}


EMAIL_PATTERNS = [

    # ==================================================
    # 1️⃣ Standard RFC-style email
    # ==================================================
    r'\b[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}'
    r'@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b',

    # ==================================================
    # 2️⃣ Email with explicit labels (EN / HI / NE)
    # ==================================================
    r'\b(?:email|e-mail|mail|gmail|email id|mail id|'
    r'ईमेल|मेल|इमेल|'
    r'email address|mail address)\s*[:\-]?\s*'
    r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})',

    # ==================================================
    # 3️⃣ Spoken / conversational formats
    # ==================================================
    r'\b(?:my|mera|mero|hamro)?\s*'
    r'(?:email|mail|gmail|id)\s*'
    r'(?:is|hai|ho|cha)\s*'
    r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})',

    # ==================================================
    # 4️⃣ Brackets / quotes / symbols
    # ==================================================
    r'[\(<\[\{\"\']\s*'
    r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})'
    r'\s*[\)\]\}\"\']',

    # ==================================================
    # 5️⃣ Obfuscated "at / dot" formats
    # ==================================================
    r'\b[A-Za-z0-9._%+-]+\s*(?:@|\(at\)|\[at\]| at )\s*'
    r'[A-Za-z0-9.-]+\s*(?:\.|\(dot\)|\[dot\]| dot )\s*'
    r'[A-Za-z]{2,}\b',

    # ==================================================
    # 6️⃣ Gmail/Yahoo/Outlook without .com typed
    # ==================================================
    r'\b[A-Za-z0-9._%+-]+@'
    r'(?:gmail|yahoo|outlook|hotmail|rediff)'
    r'\.(?:com|co\.in|in|net)\b',

    # ==================================================
    # 7️⃣ Multi-subdomain / corporate emails
    # ==================================================
    r'\b[A-Za-z0-9._%+-]+@'
    r'(?:[A-Za-z0-9-]+\.){2,}'
    r'[A-Za-z]{2,}\b',

    # ==================================================
    # 8️⃣ Government / education domains
    # ==================================================
    r'\b[A-Za-z0-9._%+-]+@'
    r'(?:gov|gov\.in|edu|edu\.in|ac\.in|org)\b',

    # ==================================================
    # 9️⃣ Emails at start of line
    # ==================================================
    r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',

    # ==================================================
    # 🔟 Emails at end of line
    # ==================================================
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$',

    # ==================================================
    # 1️⃣1️⃣ Uppercase emails
    # ==================================================
    r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',

    # ==================================================
    # 1️⃣2️⃣ Emails with numbers-heavy usernames
    # ==================================================
    r'\b[A-Za-z0-9]{3,}[._-]?[0-9]{2,}@'
    r'[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',

    # ==================================================
    # 1️⃣3️⃣ Short local-part corporate emails
    # ==================================================
    r'\b[A-Za-z]{1,3}@'
    r'[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',

    # ==================================================
    # 1️⃣4️⃣ Email after "reach/contact"
    # ==================================================
    r'\b(?:reach|contact|send|write|message)\s+(?:me|us)?\s*(?:at|on)?\s*'
    r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})',

    # ==================================================
    # 1️⃣5️⃣ Fallback – aggressive capture
    # ==================================================
    r'\b\S+@\S+\.\S+\b'
]



# ==================================================
# OBFUSCATED EMAIL PATTERNS
# ==================================================
OBFUSCATED_EMAIL_PATTERNS = [
    # Pattern 1: "something at gmail dot com"
    r'(\S+(?:\s+\S+)*)\s*(?:@|at|\[at\]|\(at\))\s*(\S+(?:\s+\S+)*)\s*(?:\.|dot|\[dot\]|\(dot\))\s*(\S+)',
    
    # Pattern 2: "something @ gmail dot com"
    r'(\S+)\s*@\s*(\S+)\s*dot\s*(\S+)',
    
    # Pattern 3: "something at gmail . com"
    r'(\S+)\s*at\s*(\S+)\s*\.\s*(\S+)',
    
    # Pattern 4: "something @ gmail . com"
    r'(\S+)\s*@\s*(\S+)\s*\.\s*(\S+)',
    
    # Pattern 5: Common Indian/Nepali patterns
    r'(?:email|mail|gmail|ईमेल|इमेल)\s+(?:is|hai|ho|cha)\s+(\S+)\s*(?:@|at)\s*(\S+)\s*(?:\.|dot)\s*(\S+)',
    
    # Pattern 6: With parentheses
    r'(\S+)\s*(?:\(at\)|\[at\])\s*(\S+)\s*(?:\(dot\)|\[dot\])\s*(\S+)',
]

# ==================================================
# CLEANING PATTERNS FOR EXTRACTED FIELDS
# ==================================================
CLEANING_PATTERNS = {
    'email': [
        (r'\s+', ''),  # Remove spaces
        (r'\[dot\]', '.'),  # Replace [dot] with .
        (r'\(dot\)', '.'),  # Replace (dot) with .
        (r'dot', '.'),  # Replace dot with .
        (r'\[at\]', '@'),  # Replace [at] with @
        (r'\(at\)', '@'),  # Replace (at) with @
        (r' at ', '@'),  # Replace " at " with @
        (r'\s*at\s*', '@'),  # Replace "at" with @
    ],
    'phone': [
        (r'[^\d+]', ''),  # Keep only digits and +
    ],
    'name': [
        (r'\s+', ' '),  # Normalize spaces
        (r'^\s+|\s+$', ''),  # Trim
    ]
}

# ==================================================
# FIELD UPDATE RULES
# ==================================================
FIELD_UPDATE_RULES = {
    'email': {
        'always_update': True,  # Always update if better email found
        'better_if': [
            lambda new, old: '@' in new and '.' in new,  # Valid email format
            lambda new, old: ' ' not in new,  # No spaces
            lambda new, old: not ('dot' in new or 'at' in new),  # Not obfuscated
        ]
    },
    'phone': {
        'always_update': False,
        'better_if': [
            lambda new, old: new.startswith('+'),  # Has country code
            lambda new, old: len(re.sub(r'\D', '', new)) >= 10,  # At least 10 digits
        ]
    }
}



# ==================================================
# DATE EXTRACTION PATTERNS – ADVANCED & ROBUST
# Supports: English, Hindi, Nepali, numeric, ranges, relative
# ==================================================

DATE_EXTRACTION_PATTERNS = [

    # --------------------------------------------------
    # 1. FULL DATE WITH MONTH NAME (ENGLISH)
    # --------------------------------------------------
    r'\b(\d{1,2}(?:st|nd|rd|th)?[\s\-]+'
    r'(?:january|february|march|april|may|june|july|august|'
    r'september|october|november|december|'
    r'jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)'
    r'[a-z]*[\s,\-]+\d{4})\b',

    # --------------------------------------------------
    # 2. DATE WITH MONTH NAME (NO YEAR)
    # --------------------------------------------------
    r'\b(\d{1,2}(?:st|nd|rd|th)?[\s\-]+'
    r'(?:january|february|march|april|may|june|july|august|'
    r'september|october|november|december|'
    r'jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)'
    r'[a-z]*)\b',

    # --------------------------------------------------
    # 3. NUMERIC DATES (DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY)
    # --------------------------------------------------
    r'\b(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})\b',

    # --------------------------------------------------
    # 4. ISO FORMAT (YYYY-MM-DD)
    # --------------------------------------------------
    r'\b(\d{4}[\/\-.]\d{1,2}[\/\-.]\d{1,2})\b',

    # --------------------------------------------------
    # 5. DAY NAME + DATE
    # --------------------------------------------------
    r'\b((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)[\s,]+'
    r'\d{1,2}(?:st|nd|rd|th)?[\s\-]+'
    r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*)\b',

    # --------------------------------------------------
    # 6. RELATIVE DATES (ENGLISH)
    # --------------------------------------------------
    r'\b(today|tomorrow|day after tomorrow|'
    r'tonight|this morning|this evening|'
    r'this week|this month|this year|'
    r'next week|next month|next year|'
    r'coming week|coming month|'
    r'in\s+\d+\s+(?:day|days|week|weeks|month|months))\b',

    # --------------------------------------------------
    # 7. DATE RANGES (ENGLISH)
    # --------------------------------------------------
    r'\b(\d{1,2}(?:st|nd|rd|th)?\s+'
    r'(?:to|\-|until|till|through)\s+'
    r'\d{1,2}(?:st|nd|rd|th)?\s+'
    r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*)\b',

    # --------------------------------------------------
    # 8. HINDI DATE FORMAT
    # --------------------------------------------------
    r'\b(\d{1,2}\s+'
    r'(?:जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|'
    r'सितंबर|अक्टूबर|नवंबर|दिसंबर)\s+'
    r'\d{4})\b',

    # --------------------------------------------------
    # 9. NEPALI DATE FORMAT (DEVANAGARI)
    # --------------------------------------------------
    r'\b(\d{1,2}\s+'
    r'(?:बैशाख|जेठ|असार|साउन|भदौ|असोज|कार्तिक|'
    r'मंसिर|पुष|माघ|फागुन|चैत)\s+'
    r'\d{4})\b',

    # --------------------------------------------------
    # 10. SHORT NUMERIC DATE (NO YEAR – LOW CONFIDENCE)
    # --------------------------------------------------
    r'\b(\d{1,2}[\/\-]\d{1,2})\b(?!\d)',

    # --------------------------------------------------
    # 11. EVENT-STYLE DATES
    # --------------------------------------------------
    r'\b(on|from|starting|scheduled for|booked for)\s+'
    r'(\d{1,2}(?:st|nd|rd|th)?[\s\-]+'
    r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*)\b'
]


# Date validation patterns
DATE_VALIDATION_PATTERNS = [
    r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}',
    r'\d{1,2}[/-]\d{1,2}[/-]\d{4}',
    r'\d{4}[/-]\d{1,2}[/-]\d{1,2}'
]

PINCODE_PATTERNS = [

    # ==================================================
    # 1️⃣ India PIN (strict – 6 digits, non-zero start)
    # ==================================================
    r'\b([1-9][0-9]{5})\b',

    # ==================================================
    # 2️⃣ India PIN with labels
    # ==================================================
    r'\b(?:pin|pincode|pin code|postal code|zip|'
    r'पिन|पिनकोड|डाक कोड|पिन नम्बर)\s*[:\-]?\s*'
    r'([1-9][0-9]{5})\b',

    # ==================================================
    # 3️⃣ India PIN with space (XXX XXX)
    # ==================================================
    r'\b([1-9][0-9]{2})\s+([0-9]{3})\b',

    # ==================================================
    # 4️⃣ Nepal PIN (5 digits)
    # ==================================================
    r'\b([1-9][0-9]{4})\b',

    # ==================================================
    # 5️⃣ Nepal PIN with labels
    # ==================================================
    r'\b(?:postal|zip|pin|postcode|'
    r'हुलाक कोड|पोस्टल कोड|पिन)\s*[:\-]?\s*'
    r'([1-9][0-9]{4})\b',

    # ==================================================
    # 6️⃣ Pakistan PIN (5 digits)
    # ==================================================
    r'\b([1-9][0-9]{4})\b',

    # ==================================================
    # 7️⃣ Bangladesh PIN (4 digits)
    # ==================================================
    r'\b([1-9][0-9]{3})\b',

    # ==================================================
    # 8️⃣ UAE / Dubai postal-style numeric codes
    # (often used unofficially)
    # ==================================================
    r'\b([1-9][0-9]{4,5})\b',

    # ==================================================
    # 9️⃣ PIN after address indicators
    # ==================================================
    r'\b(?:area|sector|block|ward|zone|district|'
    r'इलाका|क्षेत्र|वार्ड)\s*[:\-]?\s*'
    r'([1-9][0-9]{3,5})\b',

    # ==================================================
    # 🔟 PIN inside brackets / punctuation
    # ==================================================
    r'[\(\[\{]\s*([1-9][0-9]{3,5})\s*[\)\]\}]',

    # ==================================================
    # 1️⃣1️⃣ PIN at end of sentence
    # ==================================================
    r'\b([1-9][0-9]{3,5})[.,]?$',

    # ==================================================
    # 1️⃣2️⃣ PIN at beginning of line
    # ==================================================
    r'^([1-9][0-9]{3,5})\b',

    # ==================================================
    # 1️⃣3️⃣ PIN after keywords like "my", "is"
    # ==================================================
    r'\b(?:is|hai|ho|cha|my|mera|mero)\s+'
    r'([1-9][0-9]{3,5})\b',

    # ==================================================
    # 1️⃣4️⃣ Aggressive numeric fallback (LAST)
    # ==================================================
    r'\b([0-9]{4,6})\b'
]


# ==================================================
# ADDRESS INDICATORS – ADVANCED & MULTI-LINGUAL
# ==================================================

ADDRESS_INDICATORS = [

    # ----------------------------
    # Street / Road types (EN)
    # ----------------------------
    "street", "st", "st.", "road", "rd", "rd.", "lane", "ln", "ln.",
    "avenue", "ave", "ave.", "boulevard", "blvd", "blvd.",
    "drive", "dr", "dr.", "court", "ct", "ct.",
    "circle", "cir", "cir.", "way", "walk",
    "terrace", "terr", "terr.", "place", "pl", "pl.",
    "parkway", "pkwy", "highway", "hwy", "expressway", "flyover",

    # ----------------------------
    # Buildings / Units
    # ----------------------------
    "house", "home", "flat", "apartment", "apt", "apt.",
    "villa", "bungalow", "building", "bldg", "bldg.",
    "floor", "fl", "fl.", "room", "rm", "rm.",
    "suite", "ste", "unit", "block", "blk", "blk.",
    "tower", "wing", "complex", "compound",
    "residency", "residence", "society", "housing",

    # ----------------------------
    # Administrative / Area
    # ----------------------------
    "sector", "phase", "area", "locality", "layout",
    "colony", "enclave", "extension",
    "village", "town", "city",
    "district", "state", "province", "region",
    "zone", "ward", "ward no", "municipality",

    # ----------------------------
    # Market / Traditional Indian-Nepali
    # ----------------------------
    "nagar", "pura", "pur", "ganj",
    "bazar", "bazaar", "market", "chowk",
    "mohalla", "para", "tola",

    # ----------------------------
    # Proximity / Landmark words
    # ----------------------------
    "near", "beside", "behind", "opposite",
    "in front of", "next to", "adjacent to",
    "across from", "by", "at",

    # ----------------------------
    # Number markers
    # ----------------------------
    "no", "no.", "number", "#", "plot",
    "plot no", "house no", "flat no",
    "ward no", "door no",

    # ----------------------------
    # Explicit address intent
    # ----------------------------
    "address", "location", "place", "venue", "spot", "site",

    # ----------------------------
    # Hindi / Nepali / Marathi
    # ----------------------------
    "पता", "ठेगाना", "ठाउँ", "स्थान", "स्थल",
    "गली", "मार्ग", "मोहल्ला",
    "बाटो", "टोल", "चोक",
    "गल्ली", "रस्ता", "वाडी",
]


# ==================================================
# ADVANCED NAME EXTRACTION PATTERNS (INDIA + NEPAL)
# ==================================================

NAME_PATTERNS = [

    # -------------------------------------------------
    # 1. Strong self-identification (highest confidence)
    # -------------------------------------------------
    r'\b(?:my\s+name\s+is|i\s+am|i\'m|name\s+is|name\s*:)\s+'
    r'([A-Za-z][A-Za-z\'\-.]{1,}'
    r'(?:\s+[A-Za-z][A-Za-z\'\-.]{1,}){0,3})'
    r'(?:\s*[,.\n]|$)',

    # -------------------------------------------------
    # 2. Titles (Indian + Nepali + Western)
    # -------------------------------------------------
    r'\b(?:Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?|Prof\.?|'
    r'Shri|Shree|Sri|Smt\.?|'
    r'Er\.?|Adv\.?|'
    r'Pandit|Pdt\.?|Guru)\s+'
    r'([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+){1,3})\b',

    # -------------------------------------------------
    # 3. Initials + Name
    # Examples: R. K. Sharma, A P J Abdul Kalam
    # Also common in Nepal
    # -------------------------------------------------
    r'\b((?:[A-Z]\.\s*){1,3}[A-Z][a-z]+'
    r'(?:\s+[A-Z][a-z]+){0,2})\b',

    # -------------------------------------------------
    # 4. Capitalized full names (2–4 words)
    # Country-neutral, high precision
    # -------------------------------------------------
    r'\b([A-Z][a-z]{2,}'
    r'(?:\s+[A-Z][a-z]{2,}){1,3})\b'
    r'(?!\s*(?:is|was|were|are|am|phone|email|@|\+|\d))',

    # -------------------------------------------------
    # 5. Common surnames (BALANCED – India + Nepal)
    # -------------------------------------------------
    r'\b([A-Z][a-z]+(?:\s+'
    r'(?:'
    # Indian + Nepali shared / common
    r'Sharma|Kumar|Singh|Thapa|Rai|'
    r'Gupta|Verma|Joshi|Pandey|Mishra|'
    r'Adhikari|Poudel|Bhandari|Karki|'
    r'Gurung|Magar|Tamang|Lama|'
    r'KC|K\.C\.|'
    # Neutral South Asian
    r'Reddy|Rao|Das|Nair|Iyer|Pillai'
    r')))\b',

    # -------------------------------------------------
    # 6. Lowercase names after strong intent
    # Example: "my name is ram bahadur"
    # -------------------------------------------------
    r'\b(?:my\s+name\s+is|i\s+am|i\'m)\s+'
    r'([a-z]{3,}(?:\s+[a-z]{3,}){0,2})\b',

    # -------------------------------------------------
    # 7. Hyphenated / apostrophe names
    # Works globally
    # -------------------------------------------------
    r'\b([A-Z][A-Za-z]+(?:[-\'][A-Z][A-Za-z]+)+'
    r'(?:\s+[A-Z][A-Za-z]+)*)\b',

    # -------------------------------------------------
    # 8. Devanagari names (Hindi + Nepali)
    # -------------------------------------------------
    r'\b([\u0900-\u097F]{2,}'
    r'(?:\s+[\u0900-\u097F]{2,}){1,3})\b',

    # -------------------------------------------------
    # 9. Mixed Latin + Devanagari
    # Example: "Ram बहादुर", "Sita देवी"
    # -------------------------------------------------
    r'\b([A-Za-z]{3,}(?:\s+[\u0900-\u097F]{2,})+)\b',

    # -------------------------------------------------
    # 10. Single-word name ONLY with explicit signal
    # -------------------------------------------------
    r'\b(?:name\s+is|i\s+am|i\'m)\s+([A-Z][a-z]{2,})\b',
]


# ==================== INTENT DETECTION PATTERNS ====================

# Organized intent patterns
INTENT_PATTERNS = {
    "booking": [
        "book", "booking", "i want to book", "want to book", "book this",
        "book it", "proceed with booking", "confirm booking", "make booking",
        "schedule", "reserve", "appointment", "i'll book", "let's book",
        "go for", "go with", "choose", "select", "pick", "get", "proceed",
        "confirm", "go ahead", "take", "i'd like to book", "i'd like to make",
        "book for", "book a", "book an", "make a booking", "make reservation"
    ],
    
    "info": [
        "what", "which", "how", "tell me", "show me", "list",
        "information", "info", "details", "about", "price", "cost",
        "available", "offer", "have", "do you have", "can you show",
        "what are", "what is", "how much", "pricing", "packages",
        "explain", "describe", "compare", "difference between"
    ],
    
    "completion": [
        "done", "finish", "finished", "complete", "completed",
        "proceed", "confirm", "confirmed", "go ahead", "send otp",
        "book now", "ready", "all set", "submit", "finalize",
        "that's all", "that's it", "all done", "ready to book"
    ],
    
    "exit": [
        "exit", "cancel", "quit", "stop", "nevermind", "never mind",
        "exit booking", "cancel booking", "stop booking", "abort",
        "forget it", "not interested", "changed my mind"
    ],
    
    "restart": [
        "restart", "start over", "begin again", "reset", "new booking",
        "start fresh", "start again", "from beginning", "retry"
    ],
    
    "affirmative": [
        "yes", "yeah", "yep", "yup", "sure", "ok", "okay",
        "correct", "right", "exactly", "absolutely", "definitely",
        "of course", "indeed", "affirmative", "confirmed",
        "हां", "हो", "सही",  # Hindi/Nepali
        "होय", "ठिक"  # Marathi
    ],
    
    "negative": [
        "no", "nope", "nah", "not", "never", "wrong", "incorrect",
        "not correct", "not right", "don't", "dont", "negative",
        "नहीं", "होइन", "गलत",  # Hindi/Nepali
        "नाही", "चूक"  # Marathi
    ],
    
    "chat_mode": [
        "i want to chat", "want to chat", "let's chat", "just chat",
        "don't book", "don't ask me to book", "not booking",
        "just talking", "only chat", "chat only", "chat mode",
        "talk about", "discuss", "have a conversation", "chat",
        "converse", "talk", "speak", "have a talk", "have discussion",
        "cancel booking and chat", "stop booking and chat",
        "no booking just chat", "skip booking"
    ],
    
    "frustration": [
        "again", "seriously", "ugh", "come on", "really", "annoying",
        "frustrating", "ridiculous", "whats wrong", "what's wrong",
        "hello?", "hey", "are you there", "anyone", "this is crazy",
        "unbelievable", "omg", "oh my god", "god", "jeez", "jesus",
        "what the hell", "what the fuck", "wtf", "damn", "dammit",
        "didnt get", "didn't get", "not getting", "where is", "when will"
    ]
}



# Question detection
QUESTION_STARTERS = [
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "list", "show", "tell", "give", "explain", "describe", "compare",
    "define", "clarify", "summarize",
    "what is", "what are", "what does", "what do", "what kind",
    "what type", "how to", "how do", "how can", "how does", "how should",
    "how much", "how many", "how long", "when is", "where is",
    "who is", "who are", "which is", "which are",
    "tell me", "show me", "give me", "explain this", "describe this",
    "list all", "list your", "compare between", "difference between",
    "price of", "cost of", "details of", "information about",
    "what is the", "what are the", "how much does", "how many types",
    "how can i", "how do i", "how does it", "what does it",
    "tell me about", "show me about", "give me details",
    "give me information", "list all services", "list available services",
    "compare the difference", "difference between two",
    "price of the", "cost of the",
    "can you", "could you", "would you", "will you",
    "can you please", "could you please", "would you please",
    "will you please", "can u", "could u",
    "i want to know", "i would like to know",
    "i want information on", "i would like information on",
    "i need information about", "i am looking for information on",
    "i am curious about", "i want details about",
    "i would like details about",
    "explain to me", "explain it", "explain this to me",
    "describe it", "describe this", "walk me through",
    "help me understand",
    "do you have", "do you offer", "do you provide",
    "are you offering", "is there", "are there",
    "is it possible", "are you able to",
    "what is the price", "what is the cost",
    "how much is", "how much are",
    "how much does it cost", "how much do you charge",
    "charges for", "fee for",
    "i was wondering", "i am wondering",
    "just wanted to ask", "just want to ask",
    "need some information", "need some details",
    "looking for information", "looking for details",
    "tell me the", "show me the", "give me the",
    "say the", "explain the", "describe the",
    "can i know", "could i know", "may i know",
    "is it true that", "is this true",
    "what about", "how about"
]

QUESTION_PATTERNS = [
    r'\?$',
    r'^(what|where|when|why|how|which|who|can|could|would|will|is|are|do|does)',
    r'(tell me|show me|explain|describe|help me understand)',
    r'(what if|how about|what about)',
]

# Booking detail keywords for extraction
BOOKING_DETAIL_KEYWORDS = [
    'name', 'phone', 'number', 'email', 'mail',
    'date', 'day', 'month', 'year', 'time',
    'address', 'location', 'place', 'venue',
    'pincode', 'zipcode', 'postal', 'code',
    'country', 'city', 'state', 'district',
    'event', 'function', 'ceremony', 'wedding',
    'my ', 'i ', 'me ', 'mine '
]

# ==================== OFF-TOPIC DETECTION ====================

OFF_TOPIC_CATEGORIES = {
    "social_media": [
        'instagram', 'facebook', 'twitter', 'youtube', 'linkedin',
        'social media', 'social', 'media', 'follow', 'subscriber', 
        'subscribers', 'channel', 'profile', 'page', 'account',
        'handle', 'username', 'link', 'website', 'web', 'site',
        'online', 'internet', 'net', 'whatsapp channel', 'telegram',
        'tiktok', 'snapchat', 'pinterest'
    ],
    
    "greetings": [
        'hi', 'hello', 'hey', 'good morning', 'good afternoon',
        'good evening', 'how are you', 'how do you do', 'nice to meet you',
        'thank you', 'thanks', 'please', 'sorry', 'excuse me',
        'never mind', 'forget it', 'cancel', 'stop', 'wait',
        'hold on', 'one second', 'one minute', 'just a moment'
    ],
    
    "self_reference": [
        'about you', 'about your', 'who are you',
        'what do you do', 'where are you',
        'experience', 'portfolio', 'gallery',
        'rating', 'review', 'feedback', 'testimonial'
    ],
    
    "general_off_topic": [
        'let me think', 'i think', 'i believe', 'maybe', 'perhaps',
        'could be', 'not sure', 'i don\'t know', 'i forgot',
        'i don\'t remember', 'remind me', 'tell me again'
    ]
}

VALIDATION_PATTERNS = {

    # ==================================================
    # 📧 Email (RFC-safe, subdomains, no trailing dots)
    # ==================================================
    "email": (
        r'^(?!\.)(?!.*\.\.)'
        r'[A-Za-z0-9._%+-]{1,64}'
        r'@'
        r'(?:[A-Za-z0-9-]+\.)+'
        r'[A-Za-z]{2,24}$'
    ),

    # ==================================================
    # 📮 PIN / Postal Code (India, Nepal, PK, BD, UAE)
    # ==================================================
    "pincode": (
        r'^(?:'
        r'[1-9][0-9]{5}|'     # India (6)
        r'[1-9][0-9]{4}|'     # Nepal / Pakistan (5)
        r'[1-9][0-9]{3}'      # Bangladesh (4)
        r')$'
    ),

    # ==================================================
    # 🏠 Address (natural language, symbols allowed)
    # ==================================================
    "address": (
        r'^(?=.*[A-Za-z\u0900-\u097F])'  # must contain text
        r'[A-Za-z0-9\u0900-\u097F\s,.\-/#()]{10,250}$'
    ),

    # ==================================================
    # 👤 Name (English + Hindi + Nepali, titles safe)
    # ==================================================
    "name": (
        r'^(?:'
        r'(?:Mr|Mrs|Ms|Dr|Shri|Smt)\.?\s+)?'
        r'[A-Za-z\u0900-\u097F]'
        r'[A-Za-z\u0900-\u097F\s.\'-]{1,48}'
        r'$'
    ),

    # ==================================================
    # 📱 Phone (E.164 + India/Nepal friendly)
    # ==================================================
    "phone": (
        r'^\+?'
        r'(?:'
        r'(?:91|977|92|880|971)?'
        r')'
        r'[1-9][0-9]{8,14}$'
    ),

    # ==================================================
    # 📅 Date (numeric + text month, strict year)
    # ==================================================
    "date": (
        r'^(?:'
        r'\d{1,2}[-/]\d{1,2}[-/]\d{4}|'          # DD/MM/YYYY
        r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|'          # YYYY-MM-DD
        r'(?:jan|feb|mar|apr|may|jun|jul|aug|'
        r'sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}'
        r')$'
    )
}

# ==================================================
# ADDRESS COMPONENTS – CONTEXT + SUPPORT WORDS
# ==================================================

ADDRESS_COMPONENTS = [

    # Include all strong indicators
    *ADDRESS_INDICATORS,

    # ----------------------------
    # Structure words
    # ----------------------------
    "main", "cross", "junction", "corner",
    "square", "circle", "roundabout",
    "phase", "block", "row", "line",

    # ----------------------------
    # Directionals
    # ----------------------------
    "north", "south", "east", "west",
    "north east", "north west",
    "south east", "south west",
    "upper", "lower", "central",

    # ----------------------------
    # Landmark hints
    # ----------------------------
    "temple", "mandir", "masjid", "church",
    "school", "college", "hospital",
    "mall", "market", "station", "bus stand",
    "metro", "railway", "airport",

    # ----------------------------
    # Residence indicators
    # ----------------------------
    "near temple", "near hospital",
    "behind school", "opposite bank",

    # ----------------------------
    # Nepali / Hindi extras
    # ----------------------------
    "नगरपालिका", "गाउँपालिका",
    "वार्ड", "इलाका",
]


# ==================================================
# CITY NAMES – EXTENDED (INDIA + NEPAL FOCUS)
# ==================================================

CITY_NAMES = [

    # ==========================
    # 🇮🇳 INDIA – MAJOR
    # ==========================
    "delhi", "new delhi",
    "mumbai", "bombay",
    "bangalore", "bengaluru",
    "chennai", "madras",
    "kolkata", "calcutta",
    "hyderabad", "secunderabad",
    "pune", "nagpur",
    "ahmedabad", "surat", "vadodara",
    "jaipur", "udaipur", "jodhpur",
    "lucknow", "kanpur", "prayagraj",
    "indore", "bhopal", "gwalior",
    "patna", "gaya",
    "ranchi", "dhanbad",
    "bhubaneswar", "cuttack",
    "coimbatore", "madurai",
    "kochi", "ernakulam", "thrissur",
    "trivandrum", "thiruvananthapuram",
    "trichy", "salem",
    "vijayawada", "visakhapatnam",
    "tirupati", "nellore",

    # ==========================
    # 🇳🇵 NEPAL – MAJOR
    # ==========================
    "kathmandu", "lalitpur", "patan", "bhaktapur",
    "pokhara", "bharatpur",
    "biratnagar", "birgunj",
    "hetauda", "janakpur",
    "butwal", "bhairahawa", "siddharthanagar",
    "dharan", "itahari",
    "damak", "birtamode",
    "nepalgunj", "kohalpur",
    "dhangadhi", "mahendranagar",
    "tulsipur", "ghorahi",
    "baglung", "lamjung",
    "dhankuta", "illam",

    # ==========================
    # 🇵🇰 PAKISTAN
    # ==========================
    "karachi", "lahore", "islamabad", "rawalpindi",
    "faisalabad", "multan", "quetta",
    "peshawar", "sialkot", "gujranwala",

    # ==========================
    # 🇧🇩 BANGLADESH
    # ==========================
    "dhaka", "chattogram", "chittagong",
    "khulna", "rajshahi", "sylhet",
    "barisal", "rangpur", "comilla",

    # ==========================
    # 🇦🇪 UAE
    # ==========================
    "dubai", "deira", "bur dubai",
    "jumeirah", "jbr", "marina",
    "abu dhabi", "sharjah",
    "ajman", "fujairah",
    "ras al khaimah", "umm al quwain",
]




FIELD_TYPE_PATTERNS = {

    # =========================
    # 👤 NAME
    # =========================
    "name": [
        # Explicit self-introduction
        r'\b(?:my\s+name\s+is|name\s+is|i\s+am|i\'m|this\s+is)\b',
        r'\b(?:नाम|नाम\s+है|मेरा\s+नाम|मेरो\s+नाम)\b',

        # Label-based
        r'\bname\s*[:=\-]\s*[A-Za-z\u0900-\u097F]',

        # Capitalized human names (2–4 words)
        r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$',

        # Titles
        r'\b(?:Mr|Mrs|Ms|Dr|Shri|Smt|Sri)\.?\s+[A-Z]'
    ],

    # =========================
    # 📱 PHONE
    # =========================
    "phone": [
        r'\b(?:phone|mobile|contact|number|call|whatsapp|wa)\b',
        r'\b(?:फोन|मोबाइल|नंबर|नम्बर)\b',

        # Country codes
        r'\+(?:91|977|92|880|971)\b',

        # Long numeric sequences
        r'\b[6-9]\d{9}\b',
        r'\b\d{10,15}\b',

        # WhatsApp hints
        r'\b(?:wa\.?|whatsapp)\b'
    ],

    # =========================
    # 📧 EMAIL
    # =========================
    "email": [
        r'\b(?:email|e-mail|mail)\b',
        r'\b(?:ईमेल|इमेल)\b',

        # Strong indicators
        r'@[A-Za-z0-9.-]+\.',
        r'\.(?:com|net|org|edu|gov|in|np|pk|ae)\b'
    ],

    # =========================
    # 📅 DATE
    # =========================
    "date": [
        r'\b(?:date|day|when|event\s+date)\b',
        r'\b(?:तारीख|दिनांक|मिति)\b',

        # Numeric
        r'\b\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?\b',

        # Month names
        r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b',

        # Relative
        r'\b(?:today|tomorrow|next\s+week|next\s+month)\b'
    ],

    # =========================
    # 🏠 ADDRESS
    # =========================
    "address": [
        r'\b(?:address|location|place|venue|site)\b',
        r'\b(?:पता|ठेगाना|स्थान)\b',

        # Structural hints
        r'\b(?:street|road|lane|sector|colony|area|block|flat|house)\b',

        # Landmark language
        r'\b(?:near|opposite|behind|beside|next\s+to)\b'
    ],

    # =========================
    # 📮 PINCODE
    # =========================
    "pincode": [
        r'\b(?:pincode|pin\s*code|postal\s*code|zip\s*code)\b',
        r'\b(?:पिन\s*कोड)\b',

        # Country-aware lengths
        r'\b\d{4}\b',
        r'\b\d{5}\b',
        r'\b\d{6}\b'
    ],

    # =========================
    # 🌍 COUNTRY
    # =========================
    "country": [
        r'\b(?:india|nepal|pakistan|bangladesh|uae|dubai)\b',
        r'\b(?:भारत|नेपाल)\b'
    ]
}


# ================================================

FIELD_EXTRACTION_PRIORITY = {
    "phone": 100,     # strongest numeric signal
    "email": 95,      # extremely distinctive
    "pincode": 85,    # short numeric but structured
    "date": 75,       # needs context
    "country": 65,    # keyword-based
    "name": 60,       # ambiguous, human language
    "address": 50     # weakest, extract last
}

# ==================================================


SMART_EXTRACTION_RULES = {

    # =========================
    # 👤 LIKELY NAME
    # =========================
    "likely_name": {
        "condition": lambda text: (
            2 <= len(text.split()) <= 4 and
            all(word[:1].isupper() for word in text.split() if word.isalpha()) and
            not any(char.isdigit() for char in text) and
            '@' not in text and
            '+' not in text
        ),
        "field": "name",
        "confidence": 0.82
    },

    # =========================
    # 📮 LIKELY PINCODE
    # =========================
    "likely_pincode": {
        "condition": lambda text: (
            text.isdigit() and
            len(text) in (4, 5, 6) and
            not text.startswith("0")
        ),
        "field": "pincode",
        "confidence": 0.92
    },

    # =========================
    # 📱 LIKELY PHONE
    # =========================
    "likely_phone": {
        "condition": lambda text: (
            text.isdigit() and
            len(text) == 10 and
            text[0] in "6789"
        ),
        "field": "phone",
        "confidence": 0.88
    },

    # =========================
    # 📧 LIKELY EMAIL
    # =========================
    "likely_email": {
        "condition": lambda text: (
            '@' in text and
            '.' in text and
            len(text) >= 6 and
            ' ' not in text
        ),
        "field": "email",
        "confidence": 0.96
    },

    # =========================
    # 📅 LIKELY DATE
    # =========================
    "likely_date": {
        "condition": lambda text: (
            any(month in text.lower() for month in
                ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]) or
            any(sep in text for sep in ["/", "-"])
        ),
        "field": "date",
        "confidence": 0.78
    },

    # =========================
    # 🏠 LIKELY ADDRESS
    # =========================
    "likely_address": {
        "condition": lambda text: (
            len(text) > 15 and
            any(word in text.lower() for word in
                ["road","street","sector","colony","near","block","flat","house"])
        ),
        "field": "address",
        "confidence": 0.7
    }
}



# ==================== PACKAGE SELECTION ====================

PACKAGE_SELECTION_PATTERNS = [
    r'(?:go\s+for|choose|select|pick|want|need)\s+([1-3])',
    r'([1-3])\s+(?:please|pls)',
    r'option\s+([1-3])',
    r'number\s+([1-3])',
    r'package\s+([1-3])',
    r'([1-3])\s+please',
    r'([1-3])$'
]

PACKAGE_ATTRIBUTE_KEYWORDS = {
    'lowest': ['lowest', 'cheapest', 'affordable', 'budget', 'economy'],
    'highest': ['highest', 'premium', 'best', 'top', 'luxury', 'deluxe'],
    'senior': ['senior', 'artist', 'by senior', 'senior artist'],
    'chirag': ['chirag', 'signature', 'by chirag', 'chirag\'s']
}

# ==================== INTENT DETECTION SETTINGS ====================

INTENT_CONFIDENCE_THRESHOLDS = {
    'booking': 0.6,
    'info': 0.5,
    'completion': 0.7,
    'exit': 0.8,
    'restart': 0.7,
    'affirmative': 0.8,
    'negative': 0.8,
    'chat_mode': 0.7,
    'frustration': 0.6
}

INTENT_SCORING_WEIGHTS = {
    'booking_keyword': 0.4,
    'info_keyword': 0.3,
    'completion_keyword': 0.5,
    'exit_keyword': 0.6,
    'restart_keyword': 0.6,
    'affirmative_keyword': 0.5,
    'negative_keyword': 0.5,
    'chat_mode_keyword': 0.6,
    'frustration_keyword': 0.5,
    'question_mark': 0.2,
    'question_pattern': 0.4
}

# ==================== FSM STATE CONFIGURATION ====================

FSM_STATES = {
    'GREETING': 'greeting',
    'INFO_MODE': 'info_mode',
    'SELECTING_SERVICE': 'selecting_service',
    'SELECTING_PACKAGE': 'selecting_package',
    'COLLECTING_DETAILS': 'collecting_details',
    'CONFIRMING': 'confirming',
    'OTP_SENT': 'otp_sent',
    'COMPLETED': 'completed'
}

FSM_STATE_DESCRIPTIONS = {
    'GREETING': "Initial greeting and intent detection",
    'INFO_MODE': "Providing information to user",
    'SELECTING_SERVICE': "User selecting service type",
    'SELECTING_PACKAGE': "User selecting package",
    'COLLECTING_DETAILS': "Collecting user details (name, email, phone, etc.)",
    'CONFIRMING': "User confirming booking details",
    'OTP_SENT': "OTP sent, waiting for verification",
    'COMPLETED': "Booking completed successfully"
}

FSM_STATE_PROGRESS = {
    'GREETING': 0,
    'INFO_MODE': 0,
    'SELECTING_SERVICE': 20,
    'SELECTING_PACKAGE': 40,
    'COLLECTING_DETAILS': 60,
    'CONFIRMING': 80,
    'OTP_SENT': 90,
    'COMPLETED': 100
}




# ==================== DISPLAY FORMATTING ====================

# Field display order for collected info summary
FIELD_DISPLAY_ORDER = [
    'service',
    'package', 
    'name',
    'phone',
    'email',
    'date',
    'service_country',
    'address',
    'pincode'
]

# Collected info headers
COLLECTED_INFO_HEADERS = {
    "en": "✅ **Information Collected:**",
    "hi": "✅ **एकत्रित जानकारी:**",
    "ne": "✅ **सङ्कलित जानकारी:**",
    "mr": "✅ **संकलित माहिती:**"
}

# Missing info headers  
MISSING_INFO_HEADERS = {
    "en": "📝 **Please provide the following information:**",
    "hi": "📝 **कृपया निम्नलिखित जानकारी प्रदान करें:**",
    "ne": "📝 **कृपया तलका जानकारीहरू प्रदान गर्नुहोस्:**",
    "mr": "📝 **कृपया खालील माहिती प्रदान करा:**"
}

# Progress indicators
PROGRESS_INDICATORS = {
    "en": {
        "collecting": "🔄 Collecting your details...",
        "almost_done": "✨ Almost done! Just a few more details...",
        "final_step": "🎯 Final step! Please provide:"
    },
    "hi": {
        "collecting": "🔄 आपकी जानकारी एकत्र कर रहे हैं...",
        "almost_done": "✨ लगभग हो गया! बस कुछ और विवरण...",
        "final_step": "🎯 अंतिम चरण! कृपया प्रदान करें:"
    },
    "ne": {
        "collecting": "🔄 तपाईंको विवरण सङ्कलन गर्दै...",
        "almost_done": "✨ लगभग सकियो! केही थप विवरणहरू...",
        "final_step": "🎯 अन्तिम चरण! कृपया प्रदान गर्नुहोस्:"
    },
    "mr": {
        "collecting": "🔄 तुमची माहिती संकलित करत आहोत...",
        "almost_done": "✨ जवळजवळ झाले! फक्त काही अधिक तपशील...",
        "final_step": "🎯 अंतिम पायरी! कृपया प्रदान करा:"
    }
}

# ==================== MULTILINGUAL TEMPLATES ====================

PROMPT_TEMPLATES = {
    "greeting": {
        "en": "👋 **Welcome to Chirag Sharma Makeup Services!**\n\nI can help you:\n• Book makeup services\n• Answer questions about our services\n\nHow can I assist you today?",
        "hi": "👋 **चिराग शर्मा मेकअप सर्विसेज में आपका स्वागत है!**\n\nमैं आपकी मदद कर सकता हूं:\n• मेकअप सेवाएं बुक करने में\n• हमारी सेवाओं के बारे में सवालों के जवाब देने में\n\nआज मैं आपकी कैसे मदद कर सकता हूं?",
        "ne": "👋 **चिराग शर्मा मेकअप सर्भिसमा स्वागत छ!**\n\nम तपाईंलाई मद्दत गर्न सक्छु:\n• मेकअप सेवाहरू बुक गर्न\n• हाम्रा सेवाहरूको बारेमा प्रश्नहरूको जवाफ दिन\n\nआज म तपाईंलाई कसरी मद्दत गर्न सक्छु?",
        "mr": "👋 **चिराग शर्मा मेकअप सर्व्हिसेसमध्ये आपले स्वागत आहे!**\n\nमी तुम्हाला मदत करू शकतो:\n• मेकअप सेवा बुक करण्यात\n• आमच्या सेवांबद्दल प्रश्नांची उत्तरे देण्यात\n\nआज मी तुम्हाला कशी मदत करू शकतो?"
    },
    
    "service_selection": {
        "en": "📋 **Please select a service:**\n\n1️⃣ Bridal Makeup Services\n2️⃣ Party Makeup Services\n3️⃣ Engagement & Pre-Wedding Makeup\n4️⃣ Henna (Mehendi) Services\n\nReply with the number or name of the service.",
        "hi": "📋 **कृपया एक सेवा चुनें:**\n\n1️⃣ दुल्हन मेकअप सेवाएं\n2️⃣ पार्टी मेकअप सेवाएं\n3️⃣ सगाई और प्री-वेडिंग मेकअप\n4️⃣ मेहंदी सेवाएं\n\nनंबर या सेवा का नाम लिखकर जवाब दें।",
        "ne": "📋 **कृपया एउटा सेवा छान्नुहोस्:**\n\n1️⃣ दुलही मेकअप सेवाहरू\n2️⃣ पार्टी मेकअप सेवाहरू\n3️⃣ संगीत र प्री-वेडिंग मेकअप\n4️⃣ मेहन्दी सेवाहरू\n\nनम्बर वा सेवाको नामले जवाफ दिनुहोस्।",
        "mr": "📋 **कृपया एक सेवा निवडा:**\n\n1️⃣ वधू मेकअप सेवा\n2️⃣ पार्टी मेकअप सेवा\n3️⃣ एंगेजमेंट आणि प्री-वेडिंग मेकअप\n4️⃣ मेहंदी सेवा\n\nनंबर किंवा सेवेचे नाव लिहून उत्तर द्या."
    },
    
    "package_selection": {
        "en": "💼 **{service} - Select a package:**\n\n{package_list}\n\nReply with the number or package name.",
        "hi": "💼 **{service} - एक पैकेज चुनें:**\n\n{package_list}\n\nनंबर या पैकेज का नाम लिखें।",
        "ne": "💼 **{service} - प्याकेज छान्नुहोस्:**\n\n{package_list}\n\nनम्बर वा प्याकेज नाम लेख्नुहोस्।",
        "mr": "💼 **{service} - पॅकेज निवडा:**\n\n{package_list}\n\nनंबर किंवा पॅकेजचे नाव लिहा."
    },
    
    "details_collection": {
        "en": "📝 **Please provide your booking details:**\n\n• Full Name\n• WhatsApp Number\n• Email Address\n• Event Date\n• Event Location\n• PIN Code\n\nYou can provide all at once or one by one.",
        "hi": "📝 **कृपया अपनी बुकिंग जानकारी प्रदान करें:**\n\n• पूरा नाम\n• व्हाट्सएप नंबर\n• ईमेल पता\n• इवेंट की तारीख\n• इवेंट का स्थान\n• पिन कोड\n\nआप सभी एक साथ या एक-एक करके दे सकते हैं।",
        "ne": "📝 **कृपया आफ्नो बुकिङ विवरण प्रदान गर्नुहोस्:**\n\n• पूरा नाम\n• व्हाट्सएप नम्बर\n• इमेल ठेगाना\n• कार्यक्रम मिति\n• कार्यक्रम स्थान\n• पिन कोड\n\nतपाईं सबै एकैपटक वा एक-एक गरेर दिन सक्नुहुन्छ।",
        "mr": "📝 **कृपया तुमची बुकिंग माहिती द्या:**\n\n• पूर्ण नाव\n• व्हाट्सएप नंबर\n• ईमेल पत्ता\n• कार्यक्रम तारीख\n• कार्यक्रम स्थान\n• पिन कोड\n\nतुम्ही सर्व एकाच वेळी किंवा एक-एक करून देऊ शकता."
    },
    
    "confirmation": {
        "en": "✅ **Please confirm your booking details:**\n\n{summary}\n\nIs this correct? (Yes/No)",
        "hi": "✅ **कृपया अपनी बुकिंग जानकारी की पुष्टि करें:**\n\n{summary}\n\nक्या यह सही है? (हां/नहीं)",
        "ne": "✅ **कृपया आफ्नो बुकिङ विवरण पुष्टि गर्नुहोस्:**\n\n{summary}\n\nके यो सहि छ? (हो/होइन)",
        "mr": "✅ **कृपया तुमच्या बुकिंगची माहिती पुष्टी करा:**\n\n{summary}\n\nहे बरोबर आहे का? (होय/नाही)"
    },
    
    "otp_sent": {
        "en": "📱 **OTP sent to {phone}**\n\nPlease check your WhatsApp and enter the 6-digit OTP to confirm your booking.",
        "hi": "📱 **{phone} पर OTP भेजा गया**\n\nकृपया अपना व्हाट्सएप चेक करें और बुकिंग की पुष्टि के लिए 6 अंकों का OTP दर्ज करें।",
        "ne": "📱 **{phone} मा OTP पठाइयो**\n\nकृपया आफ्नो व्हाट्सएप जाँच गर्नुहोस् र बुकिङ पुष्टि गर्न ६ अंकको OTP प्रविष्ट गर्नुहोस्।",
        "mr": "📱 **{phone} वर OTP पाठवला**\n\nकृपया तुमचा व्हाट्सएप तपासा आणि बुकिंग पुष्टी करण्यासाठी ६ अंकी OTP टाका."
    },
    
    "otp_resent": {
        "en": "📱 **OTP resent to {phone}**\n\nPlease check your WhatsApp for the new OTP.",
        "hi": "📱 **{phone} पर OTP फिर से भेजा गया**\n\nकृपया नए OTP के लिए अपना व्हाट्सएप चेक करें।",
        "ne": "📱 **{phone} मा OTP पुन: पठाइयो**\n\nकृपया नयाँ OTP को लागि आफ्नो व्हाट्सएप जाँच गर्नुहोस्।",
        "mr": "📱 **{phone} वर OTP पुन्हा पाठवला**\n\nकृपया नवीन OTP साठी तुमचा व्हाट्सएप तपासा."
    },
    
    "booking_confirmed": {
        "en": "🎉 **Booking Confirmed, {name}!**\n\nThank you for booking with Chirag Sharma Makeup Services. You'll receive a confirmation on WhatsApp shortly.\n\nWould you like to make another booking?",
        "hi": "🎉 **बुकिंग की पुष्टि हो गई, {name}!**\n\nचिराग शर्मा मेकअप सर्विसेज के साथ बुकिंग के लिए धन्यवाद। आपको जल्द ही व्हाट्सएप पर पुष्टि मिलेगी।\n\nक्या आप एक और बुकिंग करना चाहेंगे?",
        "ne": "🎉 **बुकिङ पुष्टि भयो, {name}!**\n\nचिराग शर्मा मेकअप सर्भिसमा बुकिङको लागि धन्यवाद। तपाईंले चाँडै व्हाट्सएपमा पुष्टि प्राप्त गर्नुहुनेछ।\n\nके तपाईं अर्को बुकिङ गर्न चाहनुहुन्छ?",
        "mr": "🎉 **बुकिंग पुष्टी झाली, {name}!**\n\nचिराग शर्मा मेकअप सर्व्हिसेसमध्ये बुकिंगसाठी धन्यवाद। तुम्हाला लवकरच व्हाट्सएपवर पुष्टी मिळेल।\n\nतुम्हाला दुसरी बुकिंग करायची आहे का?"
    },
    
    "exit_message": {
        "en": "👋 **Booking cancelled.**\n\nNo problem! Feel free to come back anytime. Have a great day!",
        "hi": "👋 **बुकिंग रद्द की गई।**\n\nकोई बात नहीं! कभी भी वापस आने के लिए स्वतंत्र महसूस करें। आपका दिन शुभ हो!",
        "ne": "👋 **बुकिङ रद्द गरियो।**\n\nकुनै समस्या छैन! जुनसुकै बेला फर्केर आउन स्वतन्त्र महसुस गर्नुहोस्। शुभ दिन!",
        "mr": "👋 **बुकिंग रद्द केली.**\n\nकाही हरकत नाही! कधीही परत येण्यास मोकळे वाटा. तुमचा दिवस चांगला जावो!"
    },
    
    "restart_message": {
        "en": "🔄 **Let's start fresh!**\n\nWhat would you like to do?\n• Book a service\n• Ask questions about our services",
        "hi": "🔄 **चलिए नए सिरे से शुरू करते हैं!**\n\nआप क्या करना चाहेंगे?\n• सेवा बुक करें\n• हमारी सेवाओं के बारे में सवाल पूछें",
        "ne": "🔄 **नयाँबाट सुरु गरौं!**\n\nतपाईं के गर्न चाहनुहुन्छ?\n• सेवा बुक गर्नुहोस्\n• हाम्रा सेवाहरूको बारेमा प्रश्न सोध्नुहोस्",
        "mr": "🔄 **नव्याने सुरुवात करूया!**\n\nतुम्हाला काय करायचे आहे?\n• सेवा बुक करा\n• आमच्या सेवांबद्दल प्रश्न विचारा"
    },
    
    "chat_mode_message": {
        "en": "💬 **Chat mode activated!**\n\nFeel free to ask me anything about our makeup services, packages, pricing, or booking process. When you're ready to book, just let me know!",
        "hi": "💬 **चैट मोड सक्रिय!**\n\nहमारी मेकअप सेवाओं, पैकेज, मूल्य निर्धारण या बुकिंग प्रक्रिया के बारे में मुझसे कुछ भी पूछने के लिए स्वतंत्र महसूस करें। जब आप बुक करने के लिए तैयार हों, तो बस मुझे बताएं!",
        "ne": "💬 **च्याट मोड सक्रिय!**\n\nहाम्रो मेकअप सेवाहरू, प्याकेजहरू, मूल्य निर्धारण वा बुकिङ प्रक्रियाको बारेमा मलाई जे पनि सोध्न स्वतन्त्र महसुस गर्नुहोस्। जब तपाईं बुक गर्न तयार हुनुहुन्छ, मलाई मात्र थाहा दिनुहोस्!",
        "mr": "💬 **चॅट मोड सक्रिय!**\n\nआमच्या मेकअप सेवा, पॅकेजेस, किंमत किंवा बुकिंग प्रक्रियेबद्दल मला काहीही विचारण्यास मोकळे वाटा. जेव्हा तुम्ही बुक करण्यास तयार असाल, फक्त मला सांगा!"
    },
    
    "generic_fallback": {
        "en": "I'm here to help you book makeup services with Chirag Sharma. Would you like to:\n• Book a service\n• Learn about our packages\n• Ask specific questions",
        "hi": "मैं चिराग शर्मा के साथ मेकअप सेवाएं बुक करने में आपकी मदद के लिए यहां हूं। क्या आप चाहेंगे:\n• सेवा बुक करें\n• हमारे पैकेज के बारे में जानें\n• विशिष्ट सवाल पूछें",
        "ne": "म चिराग शर्मासँग मेकअप सेवाहरू बुक गर्न तपाईंलाई मद्दत गर्न यहाँ छु। के तपाईं चाहनुहुन्छ:\n• सेवा बुक गर्नुहोस्\n• हाम्रो प्याकेजको बारेमा जान्नुहोस्\n• विशेष प्रश्नहरू सोध्नुहोस्",
        "mr": "मी चिराग शर्माबरोबर मेकअप सेवा बुक करण्यात तुम्हाला मदत करण्यासाठी येथे आहे. तुम्हाला काय हवे आहे:\n• सेवा बुक करा\n• आमच्या पॅकेजेसबद्दल जाणून घ्या\n• विशिष्ट प्रश्न विचारा"
    },
    
    "generic_price_info": {
        "en": "💰 **Our Services & Pricing:**\n\nWe offer various makeup packages ranging from ₹6,999 to ₹99,999, including:\n• Bridal Makeup (₹59,999 - ₹99,999)\n• Party Makeup (₹6,999 - ₹19,999)\n• Engagement & Pre-Wedding (₹19,999 - ₹59,999)\n• Henna Services (₹19,999 - ₹49,999)\n\nWould you like details on a specific service?",
        "hi": "💰 **हमारी सेवाएं और मूल्य निर्धारण:**\n\nहम ₹6,999 से ₹99,999 तक के विभिन्न मेकअप पैकेज पेश करते हैं, जिनमें शामिल हैं:\n• दुल्हन मेकअप (₹59,999 - ₹99,999)\n• पार्टी मेकअप (₹6,999 - ₹19,999)\n• सगाई और प्री-वेडिंग (₹19,999 - ₹59,999)\n• मेहंदी सेवाएं (₹19,999 - ₹49,999)\n\nक्या आप किसी विशिष्ट सेवा के बारे में विवरण चाहेंगे?",
        "ne": "💰 **हाम्रा सेवाहरू र मूल्य निर्धारण:**\n\nहामी ₹6,999 देखि ₹99,999 सम्मका विभिन्न मेकअप प्याकेजहरू प्रदान गर्छौं, जसमा समावेश छ:\n• दुलही मेकअप (₹59,999 - ₹99,999)\n• पार्टी मेकअप (₹6,999 - ₹19,999)\n• संगीत र प्री-वेडिंग (₹19,999 - ₹59,999)\n• मेहन्दी सेवाहरू (₹19,999 - ₹49,999)\n\nके तपाईं कुनै विशेष सेवाको बारेमा विवरण चाहनुहुन्छ?",
        "mr": "💰 **आमच्या सेवा आणि किंमत:**\n\nआम्ही ₹6,999 ते ₹99,999 पर्यंत विविध मेकअप पॅकेजेस ऑफर करतो, ज्यात समाविष्ट आहे:\n• वधू मेकअप (₹59,999 - ₹99,999)\n• पार्टी मेकअप (₹6,999 - ₹19,999)\n• एंगेजमेंट आणि प्री-वेडिंग (₹19,999 - ₹59,999)\n• मेहंदी सेवा (₹19,999 - ₹49,999)\n\nतुम्हाला एखाद्या विशिष्ट सेवेचा तपशील हवा आहे का?"
    },

        "off_topic_reminders": {
        "selecting_service": {
            "en": "Now, please select a service from the list above.",
            "hi": "अब, कृपया ऊपर दी गई सूची से एक सेवा चुनें।",
            "ne": "अब, कृपया माथिको सूचीबाट एउटा सेवा छान्नुहोस्।",
            "mr": "आता, कृपया वरील यादीतून एक सेवा निवडा."
        },
        "selecting_package": {
            "en": "Getting back to your {service} booking, please select a package.",
            "hi": "अपनी {service} बुकिंग पर वापस आते हुए, कृपया एक पैकेज चुनें।",
            "ne": "तपाईंको {service} बुकिङमा फर्कदै, कृपया प्याकेज छान्नुहोस्।",
            "mr": "तुमच्या {service} बुकिंगवर परत येताना, कृपया पॅकेज निवडा."
        },
        "collecting_details": {
            "en": "Let's continue with your booking. I still need a few details.",
            "hi": "चलिए अपनी बुकिंग जारी रखते हैं। मुझे अभी कुछ विवरण चाहिए।",
            "ne": "तपाईंको बुकिङ जारी राखौं। मलाई अझै केहि विवरणहरू चाहिन्छ।",
            "mr": "तुमची बुकिंग सुरू ठेवूया. मला अजून काही तपशील आवश्यक आहेत."
        },
        "confirming": {
            "en": "Let's confirm your booking details to proceed.",
            "hi": "आगे बढ़ने के लिए अपनी बुकिंग विवरण की पुष्टि करें।",
            "ne": "अगाडि बढ्न तपाईंको बुकिङ विवरण पुष्टि गर्नुहोस्।",
            "mr": "पुढे जाण्यासाठी तुमच्या बुकिंगच्या तपशीलांची पुष्टी करूया."
        },
        "otp_sent": {
            "en": "Please enter the OTP to complete your booking.",
            "hi": "अपनी बुकिंग पूरी करने के लिए OTP दर्ज करें।",
            "ne": "बुकिङ पूरा गर्न OTP प्रविष्ट गर्नुहोस्।",
            "mr": "तुमची बुकिंग पूर्ण करण्यासाठी OTP टाका."
        }
    },

    "chat_mode_activation": {
        "en": "💬 **Chat mode activated!**\n\nI notice you have many questions! I'll help with any makeup-related queries. When you're ready to book, just say 'I want to book'!\n\nWhat would you like to know?",
        "hi": "💬 **चैट मोड सक्रिय!**\n\nमैंने देखा आपके कई सवाल हैं! मैं मेकअप से जुड़े किसी भी सवाल में मदद करूंगा। जब आप बुक करने के लिए तैयार हों, तो बस कहें 'मैं बुक करना चाहता हूं'!\n\nआप क्या जानना चाहेंगे?",
        "ne": "💬 **च्याट मोड सक्रिय!**\n\nमैले देखे तपाईंसँग धेरै प्रश्नहरू छन्! म मेकअप सम्बन्धित कुनै पनि प्रश्नमा मद्दत गर्नेछु। जब तपाईं बुक गर्न तयार हुनुहुन्छ, मात्र भन्नुहोस् 'म बुक गर्न चाहन्छु'!\n\nतपाईं के जान्न चाहनुहुन्छ?",
        "mr": "💬 **चॅट मोड सक्रिय!**\n\nमला समजले तुमचे बरेच प्रश्न आहेत! मी मेकअपशी संबंधित कोणत्याही प्रश्नांमध्ये मदत करेन. जेव्हा तुम्ही बुक करण्यासाठी तयार असाल, तेव्हा फक्त सांगा 'मला बुक करायचे आहे'!\n\nतुम्हाला काय जाणून घ्यायचे आहे?"
    }
}

ERROR_MESSAGES = {
    "service_not_found": {
        "en": "❌ I couldn't find that service. Please select from:\n1️⃣ Bridal Makeup\n2️⃣ Party Makeup\n3️⃣ Engagement & Pre-Wedding\n4️⃣ Henna Services",
        "hi": "❌ मुझे वह सेवा नहीं मिली। कृपया इनमें से चुनें:\n1️⃣ दुल्हन मेकअप\n2️⃣ पार्टी मेकअप\n3️⃣ सगाई और प्री-वेडिंग\n4️⃣ मेहंदी सेवाएं",
        "ne": "❌ मैले त्यो सेवा फेला पारेन। कृपया यिनीहरूबाट छान्नुहोस्:\n1️⃣ दुलही मेकअप\n2️⃣ पार्टी मेकअप\n3️⃣ संगीत र प्री-वेडिंग\n4️⃣ मेहन्दी सेवाहरू",
        "mr": "❌ मला ती सेवा सापडली नाही. कृपया यापैकी निवडा:\n1️⃣ वधू मेकअप\n2️⃣ पार्टी मेकअप\n3️⃣ एंगेजमेंट आणि प्री-वेडिंग\n4️⃣ मेहंदी सेवा"
    },
    
    "package_not_found": {
        "en": "❌ I couldn't find that package. Please select a package number (1-3) from the list above.",
        "hi": "❌ मुझे वह पैकेज नहीं मिला। कृपया ऊपर की सूची से पैकेज नंबर (1-3) चुनें।",
        "ne": "❌ मैले त्यो प्याकेज फेला पारेन। कृपया माथिको सूचीबाट प्याकेज नम्बर (1-3) छान्नुहोस्।",
        "mr": "❌ मला तो पॅकेज सापडला नाही. कृपया वरील यादीतून पॅकेज नंबर (1-3) निवडा."
    },
    
    "not_understood": {
        "en": "❌ I didn't quite understand that. Could you please rephrase?",
        "hi": "❌ मुझे वह समझ में नहीं आया। क्या आप कृपया दोबारा बता सकते हैं?",
        "ne": "❌ मैले त्यो राम्रोसँग बुझिन। के तपाईं कृपया फेरि भन्न सक्नुहुन्छ?",
        "mr": "❌ मला ते नीट समजले नाही. कृपया पुन्हा सांगाल का?"
    },
    
    "off_track": {
        "en": "⚠️ Let's focus on the booking. Please provide {requested_field}.",
        "hi": "⚠️ चलिए बुकिंग पर ध्यान केंद्रित करते हैं। कृपया {requested_field} प्रदान करें।",
        "ne": "⚠️ बुकिङमा ध्यान केन्द्रित गरौं। कृपया {requested_field} प्रदान गर्नुहोस्।",
        "mr": "⚠️ बुकिंगवर लक्ष केंद्रित करूया. कृपया {requested_field} द्या."
    },
    
    "otp_send_failed": {
        "en": "❌ Failed to send OTP. Please try again or contact support.",
        "hi": "❌ OTP भेजने में विफल। कृपया पुनः प्रयास करें या समर्थन से संपर्क करें।",
        "ne": "❌ OTP पठाउन असफल। कृपया पुन: प्रयास गर्नुहोस् वा समर्थनसँग सम्पर्क गर्नुहोस्।",
        "mr": "❌ OTP पाठवण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा किंवा समर्थनाशी संपर्क साधा."
    },
    
    "otp_error": {
        "en": "❌ OTP error: {error}. Please try again.",
        "hi": "❌ OTP त्रुटि: {error}। कृपया पुनः प्रयास करें।",
        "ne": "❌ OTP त्रुटि: {error}। कृपया पुन: प्रयास गर्नुहोस्।",
        "mr": "❌ OTP त्रुटी: {error}. कृपया पुन्हा प्रयत्न करा."
    },
    
    "no_booking": {
        "en": "❌ No active booking found. Please start a new booking.",
        "hi": "❌ कोई सक्रिय बुकिंग नहीं मिली। कृपया नई बुकिंग शुरू करें।",
        "ne": "❌ कुनै सक्रिय बुकिङ फेला परेन। कृपया नयाँ बुकिङ सुरु गर्नुहोस्।",
        "mr": "❌ कोणतीही सक्रिय बुकिंग आढळली नाही. कृपया नवीन बुकिंग सुरू करा."
    },
    
    "too_many_attempts": {
        "en": "❌ Too many incorrect attempts. Please start a new booking.",
        "hi": "❌ बहुत अधिक गलत प्रयास। कृपया नई बुकिंग शुरू करें।",
        "ne": "❌ धेरै गलत प्रयासहरू। कृपया नयाँ बुकिङ सुरु गर्नुहोस्।",
        "mr": "❌ खूप चुकीचे प्रयत्न. कृपया नवीन बुकिंग सुरू करा."
    },
    
    "verification_error": {
        "en": "❌ Verification error. Please try again or contact support.",
        "hi": "❌ सत्यापन त्रुटि। कृपया पुनः प्रयास करें या समर्थन से संपर्क करें।",
        "ne": "❌ प्रमाणीकरण त्रुटि। कृपया पुन: प्रयास गर्नुहोस् वा समर्थनसँग सम्पर्क गर्नुहोस्।",
        "mr": "❌ सत्यापन त्रुटी. कृपया पुन्हा प्रयत्न करा किंवा समर्थनाशी संपर्क साधा."
    },
    
    "no_active_otp": {
        "en": "❌ No active OTP session found. Please request a new OTP.",
        "hi": "❌ कोई सक्रिय OTP सत्र नहीं मिला। कृपया नया OTP अनुरोध करें।",
        "ne": "❌ कुनै सक्रिय OTP सत्र फेला परेन। कृपया नयाँ OTP अनुरोध गर्नुहोस्।",
        "mr": "❌ कोणतेही सक्रिय OTP सत्र आढळले नाही. कृपया नवीन OTP विनंती करा."
    },

    "too_many_off_topic": {
        "en": "⚠️ I notice you have many questions. I'm switching to chat mode where you can ask me anything about makeup services. When you're ready to book, just say 'I want to book'!",
        "hi": "⚠️ मैंने देखा आपके कई सवाल हैं। मैं चैट मोड में स्विच कर रहा हूं जहां आप मेकअप सेवाओं के बारे में कुछ भी पूछ सकते हैं। जब आप बुक करने के लिए तैयार हों, तो बस कहें 'मैं बुक करना चाहता हूं'!",
        "ne": "⚠️ मैले देखे तपाईंसँग धेरै प्रश्नहरू छन्। म च्याट मोडमा स्विच गर्दैछु जहाँ तपाईंले मेकअप सेवाहरूको बारेमा जे पनि सोध्न सक्नुहुन्छ। जब तपाईं बुक गर्न तयार हुनुहुन्छ, मात्र भन्नुहोस् 'म बुक गर्न चाहन्छु'!",
        "mr": "⚠️ मला समजले तुमचे बरेच प्रश्न आहेत. मी चॅट मोडमध्ये स्विच करत आहे जिथे तुम्ही मेकअप सेवांबद्दल काहीही विचारू शकता. जेव्हा तुम्ही बुक करण्यासाठी तयार असाल, तेव्हा फक्त सांगा 'मला बुक करायचे आहे'!"
    },
    
    "resend_error": {
        "en": "❌ Failed to resend OTP. Please try again.",
        "hi": "❌ OTP फिर से भेजने में विफल। कृपया पुनः प्रयास करें।",
        "ne": "❌ OTP पुन: पठाउन असफल। कृपया पुन: प्रयास गर्नुहोस्।",
        "mr": "❌ OTP पुन्हा पाठवण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा."
    }
}

FIELD_DISPLAY_NAMES = {
    "en": {
        "name": "Full Name",
        "phone": "WhatsApp Number",
        "email": "Email",
        "date": "Event Date",
        "address": "Event Location",
        "pincode": "PIN Code",
        "country": "Country",
        "service": "Service",
        "package": "Package"
    },
    "hi": {
        "name": "पूरा नाम",
        "phone": "व्हाट्सएप नंबर",
        "email": "ईमेल",
        "date": "इवेंट तारीख",
        "address": "इवेंट स्थान",
        "pincode": "पिन कोड",
        "country": "देश",
        "service": "सेवा",
        "package": "पैकेज"
    },
    "ne": {
        "name": "पूरा नाम",
        "phone": "व्हाट्सएप नम्बर",
        "email": "इमेल",
        "date": "कार्यक्रम मिति",
        "address": "कार्यक्रम स्थान",
        "pincode": "पिन कोड",
        "country": "देश",
        "service": "सेवा",
        "package": "प्याकेज"
    },
    "mr": {
        "name": "पूर्ण नाव",
        "phone": "व्हाट्सएप नंबर",
        "email": "ईमेल",
        "date": "कार्यक्रम तारीख",
        "address": "कार्यक्रम स्थान",
        "pincode": "पिन कोड",
        "country": "देश",
        "service": "सेवा",
        "package": "पॅकेज"
    }
}

VALIDATION_ERRORS = {
    "en": {
        "phone": "Invalid phone number",
        "email": "Invalid email address", 
        "date": "Invalid date format",
        "pincode": "Invalid PIN code",
        "address": "Invalid address (too short)",
        "name": "Invalid name (too short)",
        "general": "Invalid input"
    },
    "hi": {
        "phone": "अमान्य फ़ोन नंबर",
        "email": "अमान्य ईमेल पता",
        "date": "अमान्य तारीख प्रारूप",
        "pincode": "अमान्य पिन कोड",
        "address": "अमान्य पता (बहुत छोटा)",
        "name": "अमान्य नाम (बहुत छोटा)",
        "general": "अमान्य इनपुट"
    },
    "ne": {
        "phone": "अमान्य फोन नम्बर",
        "email": "अमान्य इमेल ठेगाना",
        "date": "अमान्य मिति ढाँचा",
        "pincode": "अमान्य पिन कोड",
        "address": "अमान्य ठेगाना (धेरै छोटो)",
        "name": "अमान्य नाम (धेरै छोटो)",
        "general": "अमान्य इनपुट"
    },
    "mr": {
        "phone": "अवैध फोन नंबर",
        "email": "अवैध ईमेल पत्ता",
        "date": "अवैध तारीख स्वरूप",
        "pincode": "अवैध पिन कोड",
        "address": "अवैध पत्ता (खूप लहान)",
        "name": "अवैध नाव (खूप लहान)",
        "general": "अवैध इनपुट"
    }
}

# ==================== PATTERN UTILITY FUNCTIONS ====================

def get_service_keywords(service_name: str) -> list:
    """Get keywords for a service"""
    return SERVICES.get(service_name, {}).get("keywords", [])

def get_service_packages(service_name: str) -> dict:
    """Get packages for a service"""
    return SERVICES.get(service_name, {}).get("packages", {})

def get_service_description(service_name: str) -> str:
    """Get description for a service"""
    return SERVICES.get(service_name, {}).get("description", "")

def get_package_keywords(service_name: str, package_name: str) -> list:
    """Get keywords for a package"""
    service_data = SERVICES.get(service_name, {})
    return service_data.get("package_keywords", {}).get(package_name, [])

def get_country_phone_pattern(country: str) -> str:
    """Get phone pattern for a country"""
    return COUNTRY_PHONE_PATTERNS.get(country, r'^\+\d{10,15}$')

def get_field_display_name(field: str, language: str = "en") -> str:
    """Get field display name in specified language"""
    return FIELD_DISPLAY_NAMES.get(language, FIELD_DISPLAY_NAMES["en"]).get(field, field)

def get_validation_error(field: str, language: str = "en") -> str:
    """Get validation error message"""
    return VALIDATION_ERRORS.get(language, VALIDATION_ERRORS["en"]).get(field, "Invalid input")

def is_service_related_keyword(keyword: str) -> bool:
    """Check if keyword is related to any service"""
    keyword_lower = keyword.lower()
    for service_name, service_data in SERVICES.items():
        if keyword_lower in service_data.get("keywords", []):
            return True
    return False

def get_service_by_keyword(keyword: str) -> str:
    """Get service name by keyword"""
    keyword_lower = keyword.lower()
    for service_name, service_data in SERVICES.items():
        if keyword_lower in service_data.get("keywords", []):
            return service_name
    return None

def get_intent_patterns(intent_type: str) -> list:
    """Get patterns for an intent type"""
    return INTENT_PATTERNS.get(intent_type, [])

def is_off_topic(message: str, category: str = None) -> bool:
    """Check if message is off-topic"""
    msg_lower = message.lower()
    
    if category:
        patterns = OFF_TOPIC_CATEGORIES.get(category, [])
        return any(pattern in msg_lower for pattern in patterns)
    
    for patterns in OFF_TOPIC_CATEGORIES.values():
        if any(pattern in msg_lower for pattern in patterns):
            return True
    
    return False

def get_phone_extraction_patterns() -> dict:
    """Get all phone extraction patterns"""
    return PHONE_PATTERNS

def get_date_extraction_patterns() -> list:
    """Get date extraction patterns"""
    return DATE_EXTRACTION_PATTERNS

def get_date_validation_patterns() -> list:
    """Get date validation patterns"""
    return DATE_VALIDATION_PATTERNS

def is_question_starter(message: str) -> bool:
    """Check if message starts with a question starter"""
    msg_lower = message.lower().strip()
    for starter in QUESTION_STARTERS:
        if msg_lower.startswith(starter):
            return True
    return False

def get_package_attribute_keywords() -> dict:
    """Get package attribute keywords"""
    return PACKAGE_ATTRIBUTE_KEYWORDS

def get_booking_detail_keywords() -> list:
    """Get booking detail keywords"""
    return BOOKING_DETAIL_KEYWORDS

def get_address_components() -> list:
    """Get address components"""
    return ADDRESS_COMPONENTS

def get_city_names() -> list:
    """Get city names"""
    return CITY_NAMES

def get_validation_patterns() -> dict:
    """Get validation patterns"""
    return VALIDATION_PATTERNS

def get_agent_setting(key: str, default=None):
    """Setting value or default"""
    return AGENT_SETTINGS.get(key, default)

def get_llm_setting(key: str, default=None):
    """Setting value or default"""
    return LLM_SETTINGS.get(key, default)


def get_collected_info_header(language: str = "en") -> str:
    """Get collected info header in specified language"""
    return COLLECTED_INFO_HEADERS.get(language, COLLECTED_INFO_HEADERS["en"])


def get_missing_info_header(language: str = "en") -> str:
    """Get missing info header in specified language"""
    return MISSING_INFO_HEADERS.get(language, MISSING_INFO_HEADERS["en"])


def get_progress_indicator(stage: str, language: str = "en") -> str:
    """
    Get progress indicator message
    
    Args:
        stage: 'collecting', 'almost_done', or 'final_step'
        language: Language code
    """
    indicators = PROGRESS_INDICATORS.get(language, PROGRESS_INDICATORS["en"])
    return indicators.get(stage, "")


def validate_language(language: str) -> str:
    """
    Validate and normalize language code
    
    Args:
        language: Language code to validate
        
    Returns:
        Validated language code or default
    """    
    if not language or language not in SUPPORTED_LANGUAGES:
        return DEFAULT_LANGUAGE
    return language

def get_kb_language_instruction(language: str) -> str:
    """
    Get knowledge base language instruction
    
    Args:
        language: Language code
        
    Returns:
        Language instruction string
    """
    language = validate_language(language)
    return KB_LANGUAGE_INSTRUCTIONS.get(language, KB_LANGUAGE_INSTRUCTIONS["en"])


# Add this function to config.py for utility
def get_cleaning_patterns(field_type: str) -> List[Tuple[str, str]]:
    """Get cleaning patterns for a field type"""
    return CLEANING_PATTERNS.get(field_type, [])

def get_field_update_rules(field_type: str) -> Dict:
    """Get update rules for a field type"""
    return FIELD_UPDATE_RULES.get(field_type, {})



# Add to PATTERN UTILITY FUNCTIONS section:

def get_off_topic_reminder(state: str, language: str = "en") -> str:
    """Get off-topic reminder for a specific state"""
    language = validate_language(language)
    reminders = PROMPT_TEMPLATES.get("off_topic_reminders", {})
    state_reminders = reminders.get(state, {})
    return state_reminders.get(language, state_reminders.get("en", ""))

def get_permanent_chat_activation_message(language: str = "en") -> str:
    """Get permanent chat mode activation message"""
    language = validate_language(language)
    return PROMPT_TEMPLATES.get("chat_mode_activation", {}).get(
        language, 
        PROMPT_TEMPLATES.get("chat_mode_activation", {}).get("en", "")
    )

def build_kb_system_prompt_content(
    language: str,
    current_state: str,
    booking_info: Dict = None
) -> str:
    """Build KB system prompt content"""
    language = validate_language(language)
    
    # Get language instruction
    language_instruction = get_kb_language_instruction(language)
    
    # Build services info
    services_info_lines = []
    for service_name, service_data in SERVICES.items():
        packages = service_data.get("packages", {})
        package_lines = [f"  - {name}: {price}" for name, price in packages.items()]
        services_info_lines.append(f"{service_name}:")
        services_info_lines.extend(package_lines)
    
    services_info = "\n".join(services_info_lines)
    
    # Build context
    context_parts = []
    if booking_info:
        if booking_info.get('service'):
            context_parts.append(f"Selected service: {booking_info['service']}")
        if booking_info.get('package'):
            context_parts.append(f"Selected package: {booking_info['package']}")
    
    context = "\n".join(context_parts) if context_parts else "User is inquiring about makeup services."
    
    # Get language name
    language_name = LANGUAGE_NAMES.get(language, "English")
    
    return KB_SYSTEM_PROMPT_TEMPLATE.format(
        language_instruction=language_instruction,
        services_info=services_info,
        context=context,
        language_name=language_name,
        current_state=current_state or "general inquiry"
    )