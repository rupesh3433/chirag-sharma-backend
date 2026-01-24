"""
Phone Number Extractor - Comprehensive phone extraction with country code validation
"""

import re
from typing import Optional, Dict, Any, List, Tuple
from .base_extractor import BaseExtractor


class PhoneExtractor(BaseExtractor):
    """Extract phone numbers from messages with strict country code validation"""
    
    # Country-specific phone patterns with validation rules
    PHONE_PATTERNS = {
        'India': {
            'country_code': '91',
            'local_length': 10,
            'patterns': [
                r'\+91[\s\-\.]?(\d{10})',           # +91 9876543210
                r'\+91[\s\-\.]?(\d{5})[\s\-\.]?(\d{5})',  # +91 98765 43210
                r'\+91\s*\(?\d{3,5}\)?\s*\d{3,5}\s*\d{4}',  # +91 (98765) 43210
            ],
            'starts_with': ['6', '7', '8', '9'],  # Valid starting digits
            'name': 'Indian'
        },
        'Nepal': {
            'country_code': '977',
            'local_length': 10,  # Can be 9 or 10
            'patterns': [
                r'\+977[\s\-\.]?(\d{9,10})',        # +977 9851234567
                r'\+977[\s\-\.]?(\d{2})[\s\-\.]?(\d{7,8})',  # +977 98 51234567
            ],
            'starts_with': ['9'],  # Usually starts with 9
            'name': 'Nepali'
        },
        'Pakistan': {
            'country_code': '92',
            'local_length': 10,
            'patterns': [
                r'\+92[\s\-\.]?(\d{10})',           # +92 3001234567
                r'\+92[\s\-\.]?(\d{3})[\s\-\.]?(\d{7})',  # +92 300 1234567
            ],
            'starts_with': ['3'],  # Mobile numbers start with 3
            'name': 'Pakistani'
        },
        'Bangladesh': {
            'country_code': '880',
            'local_length': 10,
            'patterns': [
                r'\+880[\s\-\.]?(\d{10})',          # +880 1712345678
                r'\+880[\s\-\.]?(\d{2})[\s\-\.]?(\d{8})',  # +880 17 12345678
            ],
            'starts_with': ['1'],  # Mobile starts with 1
            'name': 'Bangladeshi'
        },
        'Dubai': {
            'country_code': '971',
            'local_length': 9,
            'patterns': [
                r'\+971[\s\-\.]?(\d{9})',           # +971 501234567
                r'\+971[\s\-\.]?(\d{2})[\s\-\.]?(\d{7})',  # +971 50 1234567
            ],
            'starts_with': ['5'],  # Mobile usually starts with 5
            'name': 'UAE'
        },
        'USA': {
            'country_code': '1',
            'local_length': 10,
            'patterns': [
                r'\+1[\s\-\.]?(\d{10})',            # +1 2025551234
                r'\+1[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}',  # +1 (202) 555-1234
            ],
            'starts_with': [],  # No specific requirement
            'name': 'US/Canada'
        }
    }
    
    # Phone keywords/indicators
    PHONE_INDICATORS = [
        'phone', 'mobile', 'whatsapp', 'contact', 'number', 'call',
        'फोन', 'मोबाइल', 'व्हाट्सएप', 'नंबर', 'फ़ोन नंबर',
        'मोबाइल नंबर', 'संपर्क', 'कॉल'
    ]
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract phone number with country code"""
        message = self.clean_message(message)
        
        # Try strict extraction (with country code) first
        result = self.extract_strict(message)
        if result:
            self.log_extraction('phone', True, 'strict')
            return result
        
        # Try to find phone without country code and infer country
        result = self._extract_with_inference(message, context)
        if result:
            self.log_extraction('phone', True, 'inference')
            return result
        
        # Try history if context provided
        if context:
            history = self.get_conversation_history(context)
            result = self.search_in_history(history, self.extract_strict)
            if result:
                self.log_extraction('phone', True, 'history')
                return result
        
        self.log_extraction('phone', False)
        return None
    
    def extract_strict(self, message: str) -> Optional[Dict]:
        """Extract phone with strict validation (must have country code)"""
        # Try each country pattern
        for country, config in self.PHONE_PATTERNS.items():
            for pattern in config['patterns']:
                match = re.search(pattern, message)
                if match:
                    # Extract all digits from the match
                    matched_text = match.group(0)
                    digits = re.sub(r'\D', '', matched_text)
                    
                    # Validate country code
                    country_code = config['country_code']
                    if digits.startswith(country_code):
                        # Extract local number
                        local_number = digits[len(country_code):]
                        
                        # Validate local number length
                        if self._validate_local_number(local_number, config):
                            full_phone = f"+{country_code}{local_number}"
                            
                            return {
                                'phone': local_number,
                                'full_phone': full_phone,
                                'country': country,
                                'country_code': country_code,
                                'confidence': 'high',
                                'method': 'pattern_match',
                                'formatted': self._format_phone(full_phone, country)
                            }
        
        return None
    
    def extract_indian(self, message: str) -> Optional[Dict]:
        """Extract Indian phone number (with or without +91)"""
        # Pattern for 10-digit Indian numbers
        patterns = [
            r'\b([6-9]\d{9})\b',                    # 9876543210
            r'\b([6-9]\d{4})[\s\-\.](\d{5})\b',    # 98765 43210
            r'\b([6-9]\d{2})[\s\-\.](\d{3})[\s\-\.](\d{4})\b',  # 987 654 3210
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                # Extract all digits
                digits = ''.join([g for g in match.groups() if g])
                
                # Validate: should be 10 digits and start with 6-9
                if len(digits) == 10 and digits[0] in '6789':
                    full_phone = f"+91{digits}"
                    
                    return {
                        'phone': digits,
                        'full_phone': full_phone,
                        'country': 'India',
                        'country_code': '91',
                        'confidence': 'medium',
                        'method': 'indian_pattern',
                        'formatted': self._format_phone(full_phone, 'India')
                    }
        
        return None
    
    def extract_international(self, message: str) -> Optional[Dict]:
        """Extract international phone number with + prefix"""
        # Generic international pattern
        pattern = r'\+\s*(\d{1,3})[\s\-\.]?(\d[\d\s\-\.\(\)]{6,})'
        
        match = re.search(pattern, message)
        if match:
            country_code = match.group(1)
            local_part = re.sub(r'[^\d]', '', match.group(2))
            
            # Try to identify country from code
            country = self._identify_country_from_code(country_code)
            
            if country:
                config = self.PHONE_PATTERNS[country]
                
                # Validate local number
                if self._validate_local_number(local_part, config):
                    full_phone = f"+{country_code}{local_part}"
                    
                    return {
                        'phone': local_part,
                        'full_phone': full_phone,
                        'country': country,
                        'country_code': country_code,
                        'confidence': 'medium',
                        'method': 'international_pattern',
                        'formatted': self._format_phone(full_phone, country)
                    }
        
        return None
    
    def _extract_with_inference(self, message: str, context: Optional[Dict[str, Any]]) -> Optional[Dict]:
        """Extract phone and infer country from context"""
        # Try to extract Indian number first (most common)
        result = self.extract_indian(message)
        if result:
            return result
        
        # Try international pattern
        result = self.extract_international(message)
        if result:
            return result
        
        # If context has country, try country-specific patterns
        if context:
            country = self.extract_from_context('country', context) or \
                     self.extract_from_context('service_country', context)
            
            if country and country in self.PHONE_PATTERNS:
                result = self._extract_for_country(message, country)
                if result:
                    return result
        
        return None
    
    def _extract_for_country(self, message: str, country: str) -> Optional[Dict]:
        """Extract phone for specific country without country code"""
        if country not in self.PHONE_PATTERNS:
            return None
        
        config = self.PHONE_PATTERNS[country]
        local_length = config['local_length']
        
        # Look for number with appropriate length
        if isinstance(local_length, int):
            pattern = rf'\b(\d{{{local_length}}})\b'
        else:  # Range
            pattern = rf'\b(\d{{{local_length}}})\b'
        
        matches = re.finditer(pattern, message)
        
        for match in matches:
            digits = match.group(1)
            
            # Validate starting digit if specified
            if config['starts_with']:
                if digits[0] not in config['starts_with']:
                    continue
            
            # Build full phone
            full_phone = f"+{config['country_code']}{digits}"
            
            return {
                'phone': digits,
                'full_phone': full_phone,
                'country': country,
                'country_code': config['country_code'],
                'confidence': 'medium',
                'method': 'country_inferred',
                'formatted': self._format_phone(full_phone, country)
            }
        
        return None
    
    def _validate_local_number(self, local_number: str, config: Dict) -> bool:
        """Validate local phone number"""
        # Check length
        expected_length = config['local_length']
        if isinstance(expected_length, int):
            if len(local_number) != expected_length:
                return False
        else:  # Range
            min_len, max_len = expected_length
            if not (min_len <= len(local_number) <= max_len):
                return False
        
        # Check starting digit if specified
        if config['starts_with'] and local_number:
            if local_number[0] not in config['starts_with']:
                return False
        
        # All digits check
        if not local_number.isdigit():
            return False
        
        return True
    
    def _identify_country_from_code(self, country_code: str) -> Optional[str]:
        """Identify country from country code"""
        for country, config in self.PHONE_PATTERNS.items():
            if config['country_code'] == country_code:
                return country
        return None
    
    def _format_phone(self, full_phone: str, country: str) -> str:
        """Format phone number for display"""
        # Remove + for processing
        if full_phone.startswith('+'):
            digits = full_phone[1:]
        else:
            digits = full_phone
        
        config = self.PHONE_PATTERNS.get(country)
        if not config:
            return full_phone
        
        country_code = config['country_code']
        local_number = digits[len(country_code):]
        
        # Format based on country
        if country == 'India':
            # +91 98765 43210
            if len(local_number) == 10:
                return f"+91 {local_number[:5]} {local_number[5:]}"
        elif country == 'Nepal':
            # +977 985 1234567
            if len(local_number) >= 9:
                return f"+977 {local_number[:3]} {local_number[3:]}"
        elif country == 'Pakistan':
            # +92 300 1234567
            if len(local_number) == 10:
                return f"+92 {local_number[:3]} {local_number[3:]}"
        elif country == 'Bangladesh':
            # +880 17 12345678
            if len(local_number) == 10:
                return f"+880 {local_number[:2]} {local_number[2:]}"
        elif country == 'Dubai':
            # +971 50 1234567
            if len(local_number) == 9:
                return f"+971 {local_number[:2]} {local_number[2:]}"
        elif country == 'USA':
            # +1 (202) 555-1234
            if len(local_number) == 10:
                return f"+1 ({local_number[:3]}) {local_number[3:6]}-{local_number[6:]}"
        
        # Default format
        return f"+{country_code} {local_number}"
    
    def _clean_phone_number(self, phone: str) -> str:
        """Clean phone number (remove all non-digits except +)"""
        if phone.startswith('+'):
            return '+' + re.sub(r'\D', '', phone[1:])
        return re.sub(r'\D', '', phone)
    
    def validate_phone(self, phone: str, country: Optional[str] = None) -> Dict:
        """
        Validate phone number
        
        Returns:
            Dict with 'valid' boolean and optional 'error' message
        """
        phone = self._clean_phone_number(phone)
        
        # Must start with +
        if not phone.startswith('+'):
            return {
                'valid': False,
                'error': 'Phone must start with country code (e.g., +91)'
            }
        
        # Extract digits
        digits = phone[1:]
        
        # Minimum length check
        if len(digits) < 10:
            return {
                'valid': False,
                'error': 'Phone number too short'
            }
        
        # If country specified, validate for that country
        if country and country in self.PHONE_PATTERNS:
            config = self.PHONE_PATTERNS[country]
            country_code = config['country_code']
            
            if not digits.startswith(country_code):
                return {
                    'valid': False,
                    'error': f'Country code should be +{country_code} for {country}'
                }
            
            local_number = digits[len(country_code):]
            if not self._validate_local_number(local_number, config):
                return {
                    'valid': False,
                    'error': f'Invalid {config["name"]} phone number format'
                }
        
        return {'valid': True}
    
    def get_country_from_phone(self, phone: str) -> Optional[str]:
        """Get country from phone number"""
        phone = self._clean_phone_number(phone)
        
        if not phone.startswith('+'):
            return None
        
        digits = phone[1:]
        
        # Try to match country code
        for country, config in self.PHONE_PATTERNS.items():
            country_code = config['country_code']
            if digits.startswith(country_code):
                return country
        
        return None