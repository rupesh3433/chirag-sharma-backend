"""
Pincode Extractor - Robust PIN/postal code extraction logic
"""

import re
from typing import Optional, Dict, Any, List
from .base_extractor import BaseExtractor


class PincodeExtractor(BaseExtractor):
    """Extract PIN/postal codes from messages with battle-tested logic"""
    
    # Country-specific pincode patterns and validations
    COUNTRY_PATTERNS = {
        'India': {
            'length': 6,
            'pattern': r'\b([1-8]\d{5})\b',  # 6 digits, starts with 1-8
            'name': 'PIN Code'
        },
        'Nepal': {
            'length': 5,
            'pattern': r'\b(\d{5})\b',  # 5 digits
            'name': 'Postal Code'
        },
        'Pakistan': {
            'length': 5,
            'pattern': r'\b(\d{5})\b',  # 5 digits
            'name': 'Postal Code'
        },
        'Bangladesh': {
            'length': 4,
            'pattern': r'\b(\d{4})\b',  # 4 digits
            'name': 'Postal Code'
        },
        'Dubai': {
            'length': 5,
            'pattern': r'\b(\d{5})\b',  # 5 digits (UAE doesn't use postal codes much)
            'name': 'Postal Code'
        }
    }
    
    # Keywords that indicate a pincode
    PINCODE_INDICATORS = [
        'pin', 'pincode', 'pin code', 'postal', 'postal code', 'zip', 'zip code',
        'post code', 'postcode', 'पिन', 'पिनकोड', 'डाक कोड', 'पोस्टल कोड'
    ]
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract pincode from message"""
        message = self.clean_message(message)
        
        # Get country from context if available
        country = None
        if context:
            country = context.get('country') or context.get('service_country')
        
        # Try explicit pincode patterns first
        pincode = self._extract_explicit_pincode(message)
        if pincode:
            detected_country = self._detect_country_from_pincode(pincode)
            return {
                'pincode': pincode,
                'country': detected_country or country,
                'confidence': 'high',
                'method': 'explicit'
            }
        
        # Try to find pincode patterns in the message
        candidates = self._find_pincode_patterns(message)
        
        if not candidates:
            return None
        
        # Validate candidates
        for candidate in candidates:
            # Skip if it looks like a phone number
            if self._looks_like_phone(candidate, message):
                continue
            
            # Skip if it looks like a date
            if self._looks_like_date(candidate, message):
                continue
            
            # Validate with country if available
            if country:
                if self._validate_pincode_for_country(candidate, country):
                    return {
                        'pincode': candidate,
                        'country': country,
                        'confidence': 'high',
                        'method': 'country_validated'
                    }
            else:
                # Detect country from pincode
                detected_country = self._detect_country_from_pincode(candidate)
                if detected_country:
                    return {
                        'pincode': candidate,
                        'country': detected_country,
                        'confidence': 'medium',
                        'method': 'country_detected'
                    }
        
        # Return first candidate if no validation possible
        if candidates:
            return {
                'pincode': candidates[0],
                'country': country,
                'confidence': 'low',
                'method': 'pattern_match'
            }
        
        return None
    
    def _extract_explicit_pincode(self, message: str) -> Optional[str]:
        """Extract pincode from explicit patterns like 'PIN: 400050'"""
        msg_lower = message.lower()
        
        # Patterns with explicit indicators
        patterns = [
            # "PIN: 400050" or "Pincode: 400050"
            r'(?:pin|pincode|pin code|postal|postal code|zip|zip code|post code|postcode)\s*[:\-]?\s*(\d{4,6})',
            # "PIN 400050"
            r'(?:pin|pincode|postal|zip)\s+(\d{4,6})',
            # Hindi/Nepali patterns
            r'(?:पिन|पिनकोड|डाक कोड|पोस्टल कोड)\s*[:\-]?\s*(\d{4,6})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                pincode = match.group(1)
                # Validate length
                if 4 <= len(pincode) <= 6:
                    return pincode
        
        return None
    
    def _find_pincode_patterns(self, message: str) -> List[str]:
        """Find all potential pincode patterns in message"""
        candidates = []
        
        # Pattern 1: 4-6 digit numbers
        pattern = r'\b(\d{4,6})\b'
        matches = re.finditer(pattern, message)
        
        for match in matches:
            number = match.group(1)
            
            # Skip if it looks like a year (1900-2100)
            if len(number) == 4:
                try:
                    year = int(number)
                    if 1900 <= year <= 2100:
                        continue
                except ValueError:
                    pass
            
            # Skip if it's part of a date pattern
            # Check context around the number
            start_pos = match.start()
            end_pos = match.end()
            
            # Get context (20 chars before and after)
            context_start = max(0, start_pos - 20)
            context_end = min(len(message), end_pos + 20)
            context = message[context_start:context_end].lower()
            
            # Check for date indicators near the number
            date_indicators = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 
                            'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
                            'month', 'day', 'date', 'st', 'nd', 'rd', 'th']
            
            # Check if any date indicator is in context
            is_likely_date = any(indicator in context for indicator in date_indicators)
            
            # Check for date patterns like dd/mm or mm/dd
            has_date_pattern = re.search(r'\d{1,2}[-/]\d{1,2}', context) is not None
            
            if not (is_likely_date or has_date_pattern):
                # Additional validation
                if self._is_valid_pincode_length(number):
                    candidates.append(number)
        
        return candidates
    
    def _is_valid_pincode_length(self, pincode: str) -> bool:
        """Check if pincode has valid length"""
        length = len(pincode)
        # Valid lengths: 4 (Bangladesh), 5 (Nepal, Pakistan, Dubai), 6 (India)
        return length in [4, 5, 6]
    
    def _validate_pincode_for_country(self, pincode: str, country: str) -> bool:
        """Validate pincode for specific country"""
        if country not in self.COUNTRY_PATTERNS:
            return False
        
        country_info = self.COUNTRY_PATTERNS[country]
        
        # Check length
        if len(pincode) != country_info['length']:
            return False
        
        # Check pattern
        pattern = country_info['pattern']
        if not re.match(pattern, pincode):
            return False
        
        # Additional country-specific validations
        if country == 'India':
            # Indian PINs start with 1-8
            if not pincode[0] in '12345678':
                return False
        
        return True
    
    def _detect_country_from_pincode(self, pincode: str) -> Optional[str]:
        """Detect country from pincode pattern"""
        length = len(pincode)
        
        if length == 6:
            # Could be India
            if pincode[0] in '12345678':
                return 'India'
        elif length == 5:
            # Could be Nepal, Pakistan, or Dubai
            # Default to Nepal if no other info
            return 'Nepal'
        elif length == 4:
            # Bangladesh
            return 'Bangladesh'
        
        return None
    
    def _looks_like_phone(self, number: str, message: str) -> bool:
        """Check if number looks like a phone number"""
        # Find the number's position in message
        try:
            pos = message.index(number)
        except ValueError:
            return False
        
        # Check context around the number
        context_before = message[max(0, pos-10):pos].lower()
        context_after = message[pos+len(number):pos+len(number)+10].lower()
        
        # Phone indicators
        phone_indicators = ['phone', 'whatsapp', 'mobile', 'contact', 'number', '+', 'call']
        
        for indicator in phone_indicators:
            if indicator in context_before or indicator in context_after:
                return True
        
        # Check if preceded by +
        if context_before.strip().endswith('+'):
            return True
        
        # Check if it's a 10-digit number (likely phone)
        if len(number) == 10:
            return True
        
        return False
    
    def _looks_like_date(self, number: str, message: str) -> bool:
        """Check if number looks like a date"""
        # Find the number's position
        try:
            pos = message.index(number)
        except ValueError:
            return False
        
        # Check context
        context_before = message[max(0, pos-15):pos].lower()
        context_after = message[pos+len(number):pos+len(number)+15].lower()
        
        # Date indicators
        date_indicators = [
            'date', 'day', 'month', 'year', 'when', 'on',
            'jan', 'feb', 'mar', 'apr', 'may', 'jun',
            'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
            'मिति', 'तारीख', 'दिन'
        ]
        
        for indicator in date_indicators:
            if indicator in context_before or indicator in context_after:
                return True
        
        # Check if it's part of a date format (DD/MM/YYYY)
        if '/' in context_before or '/' in context_after:
            return True
        
        if '-' in context_before or '-' in context_after:
            return True
        
        return False
    
    def _get_validation_error(self, pincode: str, country: str) -> str:
        """Get validation error message"""
        if country not in self.COUNTRY_PATTERNS:
            return f"Unknown country: {country}"
        
        country_info = self.COUNTRY_PATTERNS[country]
        expected_length = country_info['length']
        
        if len(pincode) != expected_length:
            return f"{country_info['name']} should be {expected_length} digits (got {len(pincode)})"
        
        if country == 'India' and pincode[0] not in '12345678':
            return "Indian PIN codes start with digits 1-8"
        
        return "Invalid format"