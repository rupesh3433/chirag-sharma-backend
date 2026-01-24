"""
Agent and LLM configuration settings
"""

# Language support
SUPPORTED_LANGUAGES = ["en", "ne", "hi", "mr"]
LANGUAGE_NAMES = {
    "en": "English",
    "ne": "Nepali",
    "hi": "Hindi",
    "mr": "Marathi"
}

# Agent settings
AGENT_SETTINGS = {
    "max_sessions": 1000,
    "session_ttl_hours": 2,
    "max_history_messages": 15,
    "otp_expiry_minutes": 5,
    "max_otp_attempts": 3,
    "rate_limit_per_minute": 10,
    "cleanup_interval_seconds": 300
}

# LLM settings
LLM_SETTINGS = {
    "model": "llama-3.1-8b-instant",
    "temperature": 0.4,
    "max_tokens": 300,
    "timeout": 15
}