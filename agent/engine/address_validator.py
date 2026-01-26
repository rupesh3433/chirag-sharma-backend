# agent/engine/address_validator.py
"""
Address validation utilities
"""
import re
from typing import List
from .engine_config import CITY_NAMES, ADDRESS_INDICATORS, QUESTION_STARTERS, SOCIAL_MEDIA_PATTERNS


class AddressValidator:
    """Address validation utilities"""
    
    @staticmethod
    def is_likely_address(message: str) -> bool:
        """Check if message is likely an address (not a question)"""
        msg_lower = message.lower().strip()
        
        # Check for question indicators
        for starter in QUESTION_STARTERS:
            if msg_lower.startswith(starter):
                return False
        
        # Check for social media patterns
        for pattern in SOCIAL_MEDIA_PATTERNS:
            if pattern in msg_lower:
                return False
        
        # Check for off-topic patterns
        for pattern in OFF_TOPIC_PATTERNS:
            if pattern in msg_lower:
                return False
        
        # Check if it contains a city name
        has_city = any(city in msg_lower for city in CITY_NAMES)
        
        # Check for address-like patterns
        has_address_indicator = any(ind in msg_lower for ind in ADDRESS_INDICATORS)
        
        # Should be reasonably long
        word_count = len(msg_lower.split())
        
        return (has_city or has_address_indicator) and word_count >= 1
    
    @staticmethod
    def is_valid_address(address: str) -> bool:
        """Validate address string - improved to accept cities and reject dates"""
        if not address or len(address) < 3:
            return False
        
        addr_lower = address.lower()
        
        # ========================
        # STRICT DATE PATTERN EXCLUSION
        # ========================
        # Month names (English)
        months = [
            'january', 'february', 'march', 'april', 'may', 'june',
            'july', 'august', 'september', 'october', 'november', 'december',
            'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'
        ]
        
        # Comprehensive date patterns
        date_patterns = [
            # DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
            r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}',
            # MM/DD/YYYY, MM-DD-YYYY
            r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}',
            # YYYY/MM/DD, YYYY-MM-DD
            r'\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}',
            # "15 04 2025", "15 april 2025", "april 15 2025"
            r'\d{1,2}\s+(?:\d{1,2}|\w+)\s+\d{4}',
            r'(?:\d{1,2}|\w+)\s+\d{1,2}\s+\d{4}',
            # Month patterns
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}',
            r'\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*',
            # Year alone (2024-2030)
            r'\b(202[4-9]|203[0-9])\b'
        ]
        
        # Check for any date pattern - if found, REJECT as address
        for pattern in date_patterns:
            if re.search(pattern, addr_lower):
                return False
        
        # Additional check for month names with year context
        for month in months:
            if month in addr_lower:
                # Check if month is followed by or preceded by numbers
                month_pattern = rf'\b{re.escape(month)}\b'
                month_match = re.search(month_pattern, addr_lower)
                if month_match:
                    # Get context around the month
                    month_pos = month_match.start()
                    context = addr_lower[max(0, month_pos-10):min(len(addr_lower), month_pos+15)]
                    
                    # Check for date-like patterns in context
                    context_patterns = [
                        r'\d{1,2}\s+\w+\s+\d{4}',  # "15 april 2025"
                        r'\w+\s+\d{1,2}\s+\d{4}',  # "april 15 2025"
                        r'\d{1,2}\s+\w+',          # "15 april"
                        r'\w+\s+\d{1,2}',          # "april 15"
                    ]
                    
                    for ctx_pattern in context_patterns:
                        if re.search(ctx_pattern, context):
                            return False
        
        # Check for question patterns (should not be in address)
        for starter in QUESTION_STARTERS:
            if addr_lower.startswith(starter):
                return False
        
        # Check for social media patterns
        for pattern in SOCIAL_MEDIA_PATTERNS:
            if pattern in addr_lower:
                return False
        
        # Check if it's a known city
        is_city = any(city in addr_lower for city in CITY_NAMES)
        
        # Check for address components
        has_component = any(comp in addr_lower for comp in ADDRESS_INDICATORS)
        
        # Check word count
        word_count = len(address.split())
        
        # Valid if:
        # 1. It's a known city (even single word like "Delhi") AND not a date, OR
        # 2. It has address components and is at least 2 words
        return (is_city and word_count >= 1) or (has_component and word_count >= 2)
