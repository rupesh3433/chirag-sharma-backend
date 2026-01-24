"""
General helper utilities
"""

import secrets
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class Helpers:
    """Helper utilities"""
    
    @staticmethod
    def generate_session_id() -> str:
        """Generate secure session ID"""
        return secrets.token_urlsafe(16)
    
    @staticmethod
    def generate_booking_id() -> str:
        """Generate secure booking ID"""
        return secrets.token_urlsafe(16)
    
    @staticmethod
    def get_timestamp() -> str:
        """Get current timestamp in ISO format"""
        return datetime.utcnow().isoformat()
    
    @staticmethod
    def log_processing(stage: str, message: str, extra: Optional[dict] = None):
        """Log processing information"""
        log_data = {
            "stage": stage,
            "message_preview": message[:50] + "..." if len(message) > 50 else message,
            "timestamp": Helpers.get_timestamp()
        }
        
        if extra:
            log_data.update(extra)
        
        logger.info(f"📝 Processing: {log_data}")
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove extra whitespace
        cleaned = ' '.join(text.strip().split())
        
        # Normalize common variations
        replacements = {
            'whatsapp': 'WhatsApp',
            'whats app': 'WhatsApp',
            'pincode': 'PIN code',
            'pin code': 'PIN code',
            'postal code': 'PIN code',
            'zip code': 'PIN code'
        }
        
        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)
        
        return cleaned