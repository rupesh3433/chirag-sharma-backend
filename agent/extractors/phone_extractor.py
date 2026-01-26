"""
Phone Number Extractor - Comprehensive phone extraction with country code validation
ENHANCED VERSION - FIXED
"""

import re
from typing import Optional, Dict, Any, List, Tuple
from .base_extractor import BaseExtractor


class PhoneExtractor(BaseExtractor):
    """Extract phone numbers from messages with strict country code validation - ENHANCED"""
    
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
        """Extract phone number with country code - ENHANCED"""
        message = self.clean_message(message)
        
        # Use comprehensive extraction that handles all formats
        result = self.extract_comprehensive(message, context)
        
        if result:
            self.log_extraction('phone', True, result.get('method', 'comprehensive'))
            return result
        
        # Try history if context provided
        if context:
            history = self.get_conversation_history(context)
            result = self.search_in_history(history, lambda msg: self.extract_comprehensive(msg, context))
            if result:
                self.log_extraction('phone', True, 'history')
                return result
        
        self.log_extraction('phone', False)
        return None
    
    def extract_comprehensive(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Comprehensive phone extraction handling all formats"""
        # Try extraction methods in order of confidence
        extraction_methods = [
            ('strict_with_country_code', self.extract_strict),  # With + country code
            ('indian_with_91_prefix', self.extract_indian_with_91_prefix),  # 919876543210
            ('indian_10digit', self.extract_indian_10digit),  # 9876543210
            ('international', self.extract_international),  # With + but other country
            ('context_inferred', lambda msg: self._extract_with_context(msg, context)),  # Using context
            ('last_resort', self.extract_last_resort),  # Any 10-12 digit number
        ]
        
        for method_name, method in extraction_methods:
            try:
                result = method(message) if method_name != 'context_inferred' else method(message)
                if result and self._validate_phone_result(result):
                    result['method'] = method_name
                    return result
            except Exception:
                continue
        
        return None
    
    def extract_strict(self, message: str) -> Optional[Dict]:
        """Extract phone with strict validation (must have country code with +)"""
        for country, config in self.PHONE_PATTERNS.items():
            for pattern in config['patterns']:
                match = re.search(pattern, message)
                if match:
                    matched_text = match.group(0)
                    digits = re.sub(r'\D', '', matched_text)
                    
                    country_code = config['country_code']
                    if digits.startswith(country_code):
                        local_number = digits[len(country_code):]
                        
                        if self._validate_local_number(local_number, config):
                            full_phone = f"+{country_code}{local_number}"
                            
                            return {
                                'phone': local_number,
                                'full_phone': full_phone,
                                'country': country,
                                'country_code': country_code,
                                'confidence': 'very_high',
                                'formatted': self._format_phone(full_phone, country)
                            }
        
        return None
    
    def extract_indian_with_91_prefix(self, message: str) -> Optional[Dict]:
        """Extract numbers like '919876543210' (91 prefix without +)"""
        patterns = [
            # 12 digits starting with 91
            r'\b(91\d{10})\b',
            # 91 followed by groups
            r'\b(91[\s\-\.]?\d{5}[\s\-\.]?\d{5})\b',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, message)
            for match in matches:
                matched_text = match.group(1)
                digits = re.sub(r'\D', '', matched_text)
                
                if len(digits) == 12 and digits.startswith('91'):
                    local_number = digits[2:]  # Remove 91
                    
                    # Validate Indian number
                    if len(local_number) == 10 and local_number[0] in '6789':
                        full_phone = f"+{digits}"
                        return {
                            'phone': local_number,
                            'full_phone': full_phone,
                            'country': 'India',
                            'country_code': '91',
                            'confidence': 'high',
                            'formatted': f"+91 {local_number[:5]} {local_number[5:]}"
                        }
        
        return None
    
    def extract_indian_10digit(self, message: str) -> Optional[Dict]:
        """Extract 10-digit Indian numbers starting with 6-9"""
        patterns = [
            # 10 digits starting with 6-9
            r'\b([6-9]\d{9})\b',
            # With separators
            r'\b([6-9]\d{4})[\.\s\-](\d{5})\b',
            r'\b([6-9]\d{2})[\.\s\-](\d{3})[\.\s\-](\d{4})\b',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, message)
            for match in matches:
                # Combine all groups
                groups = [g for g in match.groups() if g]
                digits = ''.join(groups)
                
                if len(digits) == 10 and digits[0] in '6789':
                    full_phone = f"+91{digits}"
                    return {
                        'phone': digits,
                        'full_phone': full_phone,
                        'country': 'India',
                        'country_code': '91',
                        'confidence': 'high',
                        'formatted': f"+91 {digits[:5]} {digits[5:]}"
                    }
        
        return None
    
    def extract_international(self, message: str) -> Optional[Dict]:
        """Extract international phone number with + prefix"""
        # Match + followed by country code and number
        pattern = r'\+\s*(\d{1,4})[\s\-\.]?([\d\s\-\.\(\)]{8,})'
        
        match = re.search(pattern, message)
        if match:
            country_code = match.group(1)
            local_part_raw = match.group(2)
            local_part = re.sub(r'[^\d]', '', local_part_raw)
            
            # Try to identify country
            country = self._identify_country_from_code(country_code)
            
            if country:
                config = self.PHONE_PATTERNS.get(country)
                if config and self._validate_local_number(local_part, config):
                    full_phone = f"+{country_code}{local_part}"
                    return {
                        'phone': local_part,
                        'full_phone': full_phone,
                        'country': country,
                        'country_code': country_code,
                        'confidence': 'medium',
                        'formatted': self._format_phone(full_phone, country)
                    }
            else:
                # Unknown country but valid format
                full_phone = f"+{country_code}{local_part}"
                if len(local_part) >= 7:  # Minimum local number length
                    return {
                        'phone': local_part,
                        'full_phone': full_phone,
                        'country': 'Unknown',
                        'country_code': country_code,
                        'confidence': 'low',
                        'formatted': full_phone
                    }
        
        return None
    
    def _extract_with_context(self, message: str, context: Optional[Dict[str, Any]]) -> Optional[Dict]:
        """Extract phone using context (country from conversation)"""
        if not context:
            return None
        
        # Try to get country from context
        country = None
        
        # Check for country in extracted fields
        if isinstance(context, dict):
            if 'service_country' in context:
                country = context['service_country']
            elif 'country' in context:
                country = context['country']
        
        # Also check country extractor if available
        if hasattr(self, 'country_extractor') and self.country_extractor:
            country_data = self.country_extractor.extract(message)
            if country_data:
                country = country_data.get('country')
        
        if country and country in self.PHONE_PATTERNS:
            return self._extract_for_specific_country(message, country)
        
        return None
    
    def _extract_for_specific_country(self, message: str, country: str) -> Optional[Dict]:
        """Extract phone for specific country pattern - FIXED SYNTAX"""
        config = self.PHONE_PATTERNS[country]
        country_code = config['country_code']
        local_length = config['local_length']
        
        # Build pattern based on starting digits
        if config['starts_with']:
            # Create character class from starting digits
            starts_class = ''.join(config['starts_with'])
            pattern = fr'\b([{starts_class}]\d{{{local_length-1}}})\b'
        else:
            # No starting digit requirement
            pattern = fr'\b(\d{{{local_length}}})\b'
        
        match = re.search(pattern, message)
        if match:
            local_number = match.group(1)
            
            if self._validate_local_number(local_number, config):
                full_phone = f"+{country_code}{local_number}"
                return {
                    'phone': local_number,
                    'full_phone': full_phone,
                    'country': country,
                    'country_code': country_code,
                    'confidence': 'medium',
                    'formatted': self._format_phone(full_phone, country)
                }
        
        return None
    
    def extract_last_resort(self, message: str) -> Optional[Dict]:
        """Last resort: extract any 10-12 digit number"""
        # Find all 10-12 digit sequences
        pattern = r'\b(\d{10,12})\b'
        
        matches = re.findall(pattern, message)
        for digits in matches:
            # Try to interpret as Indian number (most common)
            if len(digits) == 10 and digits[0] in '6789':
                full_phone = f"+91{digits}"
                return {
                    'phone': digits,
                    'full_phone': full_phone,
                    'country': 'India',
                    'country_code': '91',
                    'confidence': 'low',
                    'formatted': f"+91 {digits[:5]} {digits[5:]}",
                    'note': 'Assumed Indian number (10 digits starting with 6-9)'
                }
            elif len(digits) == 12 and digits.startswith('91') and digits[2] in '6789':
                local_number = digits[2:]
                full_phone = f"+{digits}"
                return {
                    'phone': local_number,
                    'full_phone': full_phone,
                    'country': 'India',
                    'country_code': '91',
                    'confidence': 'low',
                    'formatted': f"+91 {local_number[:5]} {local_number[5:]}",
                    'note': 'Assumed Indian number (12 digits starting with 91)'
                }
        
        return None
    
    def _validate_phone_result(self, result: Dict) -> bool:
        """Validate extracted phone result"""
        if not result or 'full_phone' not in result:
            return False
        
        # Basic validation
        phone = result.get('full_phone', '')
        
        # Must start with +
        if not phone.startswith('+'):
            return False
        
        # Get digits after +
        digits = phone[1:]
        
        # Must have reasonable length
        if len(digits) < 10 or len(digits) > 15:
            return False
        
        # Must be all digits
        if not digits.isdigit():
            return False
        
        # For Indian numbers, validate starting digit
        if result.get('country') == 'India':
            local_number = result.get('phone', '')
            if local_number and local_number[0] not in '6789':
                return False
        
        return True
    
    def _validate_local_number(self, local_number: str, config: Dict) -> bool:
        """Validate local phone number"""
        # Check length
        expected_length = config['local_length']
        if isinstance(expected_length, int):
            if len(local_number) != expected_length:
                return False
        elif isinstance(expected_length, tuple):  # Range
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
        if not full_phone.startswith('+'):
            return full_phone
        
        digits = full_phone[1:]
        config = self.PHONE_PATTERNS.get(country)
        
        if not config:
            return full_phone
        
        country_code = config['country_code']
        
        # Ensure digits start with country code
        if not digits.startswith(country_code):
            return full_phone
        
        local_number = digits[len(country_code):]
        
        # Format based on country
        if country == 'India' and len(local_number) == 10:
            return f"+91 {local_number[:5]} {local_number[5:]}"
        elif country == 'Nepal' and len(local_number) >= 9:
            return f"+977 {local_number[:3]} {local_number[3:]}"
        elif country == 'Pakistan' and len(local_number) == 10:
            return f"+92 {local_number[:3]} {local_number[3:]}"
        elif country == 'Bangladesh' and len(local_number) == 10:
            return f"+880 {local_number[:2]} {local_number[2:]}"
        elif country == 'Dubai' and len(local_number) == 9:
            return f"+971 {local_number[:2]} {local_number[2:]}"
        elif country == 'USA' and len(local_number) == 10:
            return f"+1 ({local_number[:3]}) {local_number[3:6]}-{local_number[6:]}"
        
        # Default format
        return f"+{country_code} {local_number}"
    
    def _clean_phone_number(self, phone: str) -> str:
        """Clean phone number (remove all non-digits except +)"""
        if not phone:
            return phone
        
        if phone.startswith('+'):
            return '+' + re.sub(r'\D', '', phone[1:])
        return re.sub(r'\D', '', phone)
    
    def validate_phone(self, phone: str, country: Optional[str] = None) -> Dict:
        """
        Validate phone number
        
        Returns:
            Dict with 'valid' boolean and optional 'error' message
        """
        if not phone:
            return {'valid': False, 'error': 'Phone number is required'}
        
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
                'error': 'Phone number too short (minimum 10 digits after country code)'
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
        
        if not phone or not phone.startswith('+'):
            return None
        
        digits = phone[1:]
        
        # Try to match country code
        for country, config in self.PHONE_PATTERNS.items():
            country_code = config['country_code']
            if digits.startswith(country_code):
                return country
        
        return None
    
    def extract_all_possible(self, message: str) -> List[Dict]:
        """Extract all possible phone numbers from message"""
        results = []
        seen = set()
        
        # Try all extraction methods
        methods = [
            self.extract_strict,
            self.extract_indian_with_91_prefix,
            self.extract_indian_10digit,
            self.extract_international,
            self.extract_last_resort,
        ]
        
        for method in methods:
            result = method(message)
            if result and result.get('full_phone') not in seen:
                results.append(result)
                seen.add(result.get('full_phone'))
        
        return results