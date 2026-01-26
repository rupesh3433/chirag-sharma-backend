"""
Configuration Package
Centralized configuration for the booking agent system
"""

from .config import (
    # Version
    __version__,
    
    # ==================== CORE SETTINGS ====================
    SUPPORTED_LANGUAGES,
    LANGUAGE_NAMES,
    DEFAULT_LANGUAGE,
    
    # ==================== KNOWLEDGE BASE SETTINGS ====================
    KB_LANGUAGE_INSTRUCTIONS,
    KB_UNWANTED_PREFIXES,
    KB_API_SETTINGS,
    
    # ==================== SERVICE HEALTH & MONITORING ====================
    SERVICE_HEALTH_SETTINGS,
    
    # ==================== ENVIRONMENT SETTINGS ====================
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_API_URL,
    GROQ_RATE_LIMIT,
    GROQ_RETRY_DELAY,
    MONGO_URI,
    FRONTEND_URL,
    JWT_SECRET,
    BREVO_API_KEY,
    PORT,
    HOST,
    
    # ==================== CORS CONFIGURATION ====================
    CORS_ORIGINS,
    
    # ==================== TWILIO CONFIGURATION ====================
    TWILIO_CONFIG,
    
    # ==================== BREVO EMAIL CONFIGURATION ====================
    BREVO_CONFIG,
    
    # ==================== GROQ AI CONFIGURATION ====================
    GROQ_CONFIG,
    
    # ==================== DATABASE CONFIGURATION ====================
    DATABASE_CONFIG,
    
    # ==================== LOGGING CONFIGURATION ====================
    LOGGING_CONFIG,
    
    # ==================== FEATURE FLAGS ====================
    FEATURE_FLAGS,
    
    # ==================== SERVICE CONFIGURATION ====================
    SERVICES,
    SERVICE_LIST,
    SERVICE_NUMBER_MAP,
    
    # ==================== COUNTRY CONFIGURATIONS ====================
    COUNTRIES,
    COUNTRY_CODES,
    COUNTRY_PHONE_PATTERNS,
    COUNTRY_PINCODE_LENGTHS,
    
    # ==================== SYSTEM SETTINGS ====================
    AGENT_SETTINGS,
    LLM_SETTINGS,
    
    # ==================== EXTRACTION PATTERNS ====================
    PHONE_PATTERNS,
    EMAIL_PATTERNS,
    DATE_EXTRACTION_PATTERNS,
    DATE_VALIDATION_PATTERNS,
    PINCODE_PATTERNS,
    ADDRESS_INDICATORS,
    NAME_PATTERNS,
    
    # ==================== INTENT DETECTION PATTERNS ====================
    INTENT_PATTERNS,
    QUESTION_STARTERS,
    QUESTION_PATTERNS,
    BOOKING_DETAIL_KEYWORDS,
    
    # ==================== OFF-TOPIC DETECTION ====================
    OFF_TOPIC_CATEGORIES,
    
    # ==================== VALIDATION PATTERNS ====================
    VALIDATION_PATTERNS,
    ADDRESS_COMPONENTS,
    CITY_NAMES,
    
    # ==================== PACKAGE SELECTION ====================
    PACKAGE_SELECTION_PATTERNS,
    PACKAGE_ATTRIBUTE_KEYWORDS,
    
    # ==================== INTENT DETECTION SETTINGS ====================
    INTENT_CONFIDENCE_THRESHOLDS,
    INTENT_SCORING_WEIGHTS,
    
    # ==================== FSM STATE CONFIGURATION ====================
    FSM_STATES,
    FSM_STATE_DESCRIPTIONS,
    FSM_STATE_PROGRESS,
    
    # ==================== DISPLAY FORMATTING ====================
    FIELD_DISPLAY_ORDER,
    COLLECTED_INFO_HEADERS,
    MISSING_INFO_HEADERS,
    PROGRESS_INDICATORS,
    
    # ==================== MULTILINGUAL TEMPLATES ====================
    PROMPT_TEMPLATES,
    ERROR_MESSAGES,
    FIELD_DISPLAY_NAMES,
    VALIDATION_ERRORS,
    
    # ==================== PATTERN UTILITY FUNCTIONS ====================
    get_service_keywords,
    get_service_packages,
    get_service_description,
    get_package_keywords,
    get_country_phone_pattern,
    get_field_display_name,
    get_validation_error,
    is_service_related_keyword,
    get_service_by_keyword,
    get_intent_patterns,
    is_off_topic,
    get_phone_extraction_patterns,
    get_date_extraction_patterns,
    get_date_validation_patterns,
    is_question_starter,
    get_package_attribute_keywords,
    get_booking_detail_keywords,
    get_address_components,
    get_city_names,
    get_validation_patterns,
    get_agent_setting,
    get_llm_setting,
    get_collected_info_header,
    get_missing_info_header,
    get_progress_indicator,
    validate_language,
    get_kb_language_instruction,
)

# ==================== EXPORT GROUPS ====================

# Core settings
CORE_EXPORTS = [
    'SUPPORTED_LANGUAGES',
    'LANGUAGE_NAMES',
    'DEFAULT_LANGUAGE',
]

# Knowledge Base settings
KB_EXPORTS = [
    'KB_LANGUAGE_INSTRUCTIONS',
    'KB_UNWANTED_PREFIXES',
    'KB_API_SETTINGS',
]

# Service health
HEALTH_EXPORTS = [
    'SERVICE_HEALTH_SETTINGS',
]

# Environment
ENV_EXPORTS = [
    'TWILIO_ACCOUNT_SID',
    'TWILIO_AUTH_TOKEN',
    'TWILIO_WHATSAPP_FROM',
    'GROQ_API_KEY',
    'GROQ_MODEL',
    'GROQ_API_URL',
    'GROQ_RATE_LIMIT',
    'GROQ_RETRY_DELAY',
    'MONGO_URI',
    'FRONTEND_URL',
    'JWT_SECRET',
    'BREVO_API_KEY',
    'PORT',
    'HOST',
]

# Config objects
CONFIG_OBJECTS = [
    'CORS_ORIGINS',
    'TWILIO_CONFIG',
    'BREVO_CONFIG',
    'GROQ_CONFIG',
    'DATABASE_CONFIG',
    'LOGGING_CONFIG',
    'FEATURE_FLAGS',
]

# Service configuration
SERVICE_EXPORTS = [
    'SERVICES',
    'SERVICE_LIST',
    'SERVICE_NUMBER_MAP',
]

# Country configuration
COUNTRY_EXPORTS = [
    'COUNTRIES',
    'COUNTRY_CODES',
    'COUNTRY_PHONE_PATTERNS',
    'COUNTRY_PINCODE_LENGTHS',
]

# System settings
SYSTEM_EXPORTS = [
    'AGENT_SETTINGS',
    'LLM_SETTINGS',
]

# Patterns and detection
PATTERN_EXPORTS = [
    'PHONE_PATTERNS',
    'EMAIL_PATTERNS',
    'DATE_EXTRACTION_PATTERNS',
    'DATE_VALIDATION_PATTERNS',
    'PINCODE_PATTERNS',
    'PINCODE_PATTERN',
    'ADDRESS_INDICATORS',
    'NAME_PATTERNS',
    'INTENT_PATTERNS',
    'QUESTION_STARTERS',
    'QUESTION_PATTERNS',
    'BOOKING_DETAIL_KEYWORDS',
    'OFF_TOPIC_CATEGORIES',
    'VALIDATION_PATTERNS',
    'ADDRESS_COMPONENTS',
    'CITY_NAMES',
    'PACKAGE_SELECTION_PATTERNS',
    'PACKAGE_ATTRIBUTE_KEYWORDS',
    'INTENT_CONFIDENCE_THRESHOLDS',
    'INTENT_SCORING_WEIGHTS',
]


# Display formatting
DISPLAY_EXPORTS = [
    'FIELD_DISPLAY_ORDER',
    'COLLECTED_INFO_HEADERS',
    'MISSING_INFO_HEADERS',
    'PROGRESS_INDICATORS',
]

# FSM configuration
FSM_EXPORTS = [
    'FSM_STATES',
    'FSM_STATE_DESCRIPTIONS',
    'FSM_STATE_PROGRESS',
]

# Templates and messages
TEMPLATE_EXPORTS = [
    'PROMPT_TEMPLATES',
    'ERROR_MESSAGES',
    'FIELD_DISPLAY_NAMES',
    'VALIDATION_ERRORS',
]

# Utility functions
UTILITY_EXPORTS = [
    'get_service_keywords',
    'get_service_packages',
    'get_service_description',
    'get_package_keywords',
    'get_country_phone_pattern',
    'get_field_display_name',
    'get_validation_error',
    'is_service_related_keyword',
    'get_service_by_keyword',
    'get_intent_patterns',
    'is_off_topic',
    'get_phone_extraction_patterns',
    'get_date_extraction_patterns',
    'get_date_validation_patterns',
    'is_question_starter',
    'get_package_attribute_keywords',
    'get_booking_detail_keywords',
    'get_address_components',
    'get_city_names',
    'get_validation_patterns',
    'get_agent_setting',
    'get_llm_setting',
    'get_collected_info_header',
    'get_missing_info_header',
    'get_progress_indicator',
    'validate_language',
    'get_kb_language_instruction',
]

# ==================== COMPLETE EXPORT LIST ====================

__all__ = [
    # Version
    '__version__',
    
    # All export groups
    *CORE_EXPORTS,
    *KB_EXPORTS,
    *HEALTH_EXPORTS,
    *ENV_EXPORTS,
    *CONFIG_OBJECTS,
    *SERVICE_EXPORTS,
    *COUNTRY_EXPORTS,
    *SYSTEM_EXPORTS,
    *PATTERN_EXPORTS,
    *DISPLAY_EXPORTS,
    *FSM_EXPORTS,
    *TEMPLATE_EXPORTS,
    *UTILITY_EXPORTS,
]


# ==================== CONFIGURATION VALIDATION ====================

def validate_config():
    """
    Validate configuration integrity
    Run this at startup to ensure all configs are properly set
    """
    errors = []
    
    # Validate languages
    if not SUPPORTED_LANGUAGES:
        errors.append("SUPPORTED_LANGUAGES is empty")
    
    if DEFAULT_LANGUAGE not in SUPPORTED_LANGUAGES:
        errors.append(f"DEFAULT_LANGUAGE '{DEFAULT_LANGUAGE}' not in SUPPORTED_LANGUAGES")
    
    # Validate KB settings
    for lang in SUPPORTED_LANGUAGES:
        if lang not in KB_LANGUAGE_INSTRUCTIONS:
            errors.append(f"Missing KB language instruction for: {lang}")
    
    if not KB_UNWANTED_PREFIXES:
        errors.append("KB_UNWANTED_PREFIXES is empty")
    
    if not KB_API_SETTINGS or 'endpoint' not in KB_API_SETTINGS:
        errors.append("KB_API_SETTINGS missing or incomplete")
    
    # Validate services
    if not SERVICES:
        errors.append("SERVICES is empty")
    
    for service_name, service_data in SERVICES.items():
        if 'packages' not in service_data:
            errors.append(f"Service '{service_name}' missing 'packages'")
        if 'keywords' not in service_data:
            errors.append(f"Service '{service_name}' missing 'keywords'")
    
    # Validate templates for all languages
    for template_name in ['greeting', 'service_selection', 'package_selection']:
        if template_name not in PROMPT_TEMPLATES:
            errors.append(f"Missing prompt template: {template_name}")
        else:
            for lang in SUPPORTED_LANGUAGES:
                if lang not in PROMPT_TEMPLATES[template_name]:
                    errors.append(f"Missing {lang} translation for '{template_name}'")
    
    # Validate error messages for all languages
    for error_name in ['service_not_found', 'package_not_found', 'not_understood']:
        if error_name not in ERROR_MESSAGES:
            errors.append(f"Missing error message: {error_name}")
        else:
            for lang in SUPPORTED_LANGUAGES:
                if lang not in ERROR_MESSAGES[error_name]:
                    errors.append(f"Missing {lang} translation for error '{error_name}'")
    
    # Validate field display names for all languages
    required_fields = ['name', 'phone', 'email', 'date', 'address', 'pincode']
    for lang in SUPPORTED_LANGUAGES:
        if lang not in FIELD_DISPLAY_NAMES:
            errors.append(f"Missing FIELD_DISPLAY_NAMES for language: {lang}")
        else:
            for field in required_fields:
                if field not in FIELD_DISPLAY_NAMES[lang]:
                    errors.append(f"Missing field '{field}' in FIELD_DISPLAY_NAMES[{lang}]")
    
    # Validate intent patterns
    required_intents = ['booking', 'info', 'completion', 'exit', 'affirmative', 'negative']
    for intent in required_intents:
        if intent not in INTENT_PATTERNS:
            errors.append(f"Missing intent pattern: {intent}")
        elif not INTENT_PATTERNS[intent]:
            errors.append(f"Empty intent pattern: {intent}")
    
    # Validate FSM states
    if len(FSM_STATES) == 0:
        errors.append("FSM_STATES is empty")
    
    # Validate agent settings
    required_settings = ['kb_cache_ttl_minutes', 'otp_cleanup_interval_seconds', 'memory_cleanup_interval_seconds']
    for setting in required_settings:
        if setting not in AGENT_SETTINGS:
            errors.append(f"Missing AGENT_SETTING: {setting}")
    
    # Validate LLM settings
    if 'kb_max_retries' not in LLM_SETTINGS:
        errors.append("Missing LLM_SETTING: kb_max_retries")
    
    # Return validation results
    if errors:
        return {
            "valid": False,
            "errors": errors,
            "error_count": len(errors)
        }
    else:
        return {
            "valid": True,
            "message": "Configuration validation passed",
            "services_count": len(SERVICES),
            "languages_count": len(SUPPORTED_LANGUAGES),
            "intents_count": len(INTENT_PATTERNS),
            "kb_configured": bool(KB_API_SETTINGS.get('endpoint'))
        }


# ==================== CONFIGURATION INFO ====================

def get_config_info():
    """
    Get configuration information summary
    Useful for debugging and monitoring
    """
    return {
        "version": __version__,
        "core": {
            "supported_languages": SUPPORTED_LANGUAGES,
            "default_language": DEFAULT_LANGUAGE,
        },
        "knowledge_base": {
            "api_endpoint": KB_API_SETTINGS.get('endpoint'),
            "supported_languages": list(KB_LANGUAGE_INSTRUCTIONS.keys()),
            "unwanted_prefixes_count": len(KB_UNWANTED_PREFIXES),
        },
        "services": {
            "count": len(SERVICES),
            "names": SERVICE_LIST,
        },
        "countries": {
            "count": len(COUNTRIES),
            "supported": COUNTRIES,
        },
        "agent_settings": {
            "max_sessions": AGENT_SETTINGS.get("max_sessions"),
            "session_ttl_hours": AGENT_SETTINGS.get("session_ttl_hours"),
            "max_otp_attempts": AGENT_SETTINGS.get("max_otp_attempts"),
            "kb_cache_ttl_minutes": AGENT_SETTINGS.get("kb_cache_ttl_minutes"),
            "otp_cleanup_interval": AGENT_SETTINGS.get("otp_cleanup_interval_seconds"),
        },
        "llm_settings": {
            "model": LLM_SETTINGS.get("model"),
            "temperature": LLM_SETTINGS.get("temperature"),
            "max_tokens": LLM_SETTINGS.get("max_tokens"),
            "kb_max_retries": LLM_SETTINGS.get("kb_max_retries"),
        },
        "patterns": {
            "phone_patterns": len(PHONE_PATTERNS),
            "intent_patterns": len(INTENT_PATTERNS),
            "question_starters": len(QUESTION_STARTERS),
        },
        "fsm": {
            "states": len(FSM_STATES),
            "state_names": list(FSM_STATES.keys()),
        },
        "templates": {
            "prompt_templates": len(PROMPT_TEMPLATES),
            "error_messages": len(ERROR_MESSAGES),
        },
        "environment": {
            "twilio_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN),
            "groq_configured": bool(GROQ_API_KEY),
        }
    }


# ==================== EXPORT VALIDATION FUNCTIONS ====================

__all__.extend(['validate_config', 'get_config_info'])