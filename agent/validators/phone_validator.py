"""
Phone Validator - Enhanced with comprehensive validation
"""

import re
from typing import Dict, Optional


class PhoneValidator:
    """Validate phone numbers with country code support"""
    
    def __init__(self):
        """Initialize phone validator"""
        # Country code patterns and rules
        self.country_rules = {
            '91': {
                'name': 'India',
                'length': 10,
                'pattern': r'^[6-9]\d{9}$',
                'format': '+91-XXXXXXXXXX'
            },
            '977': {
                'name': 'Nepal',
                'length': 10,
                'pattern': r'^9[678]\d{8}$',
                'format': '+977-XXXXXXXXXX'
            },
            '92': {
                'name': 'Pakistan',
                'length': 10,
                'pattern': r'^3\d{9}$',
                'format': '+92-3XXXXXXXXX'
            },
            '880': {
                'name': 'Bangladesh',
                'length': 10,
                'pattern': r'^1[3-9]\d{8}$',
                'format': '+880-1XXXXXXXXX'
            },
            '971': {
                'name': 'Dubai',
                'length': 9,
                'pattern': r'^5[024568]\d{7}$',
                'format': '+971-5XXXXXXXX'
            },
            '1': {
                'name': 'USA/Canada',
                'length': 10,
                'pattern': r'^[2-9]\d{9}$',
                'format': '+1-XXXXXXXXXX'
            }
        }
    
    def validate(self, phone: str) -> Dict:
        """
        Validate phone number
        
        Returns:
            {
                'valid': bool,
                'phone': str (cleaned),
                'country': str,
                'country_code': str,
                'error': str (if invalid),
                'suggestion': str (if invalid)
            }
        """
        if not phone:
            return {
                'valid': False,
                'error': 'Phone number is required',
                'suggestion': 'Please provide your WhatsApp number with country code (e.g., +91-9876543210)'
            }
        
        # Clean phone number
        cleaned = self._clean_phone(phone)
        
        # Must start with +
        if not cleaned.startswith('+'):
            return {
                'valid': False,
                'error': 'Phone number must include country code starting with +',
                'suggestion': 'Format: +91-9876543210 (India), +977-9851234567 (Nepal), etc.',
                'phone': phone
            }
        
        # Extract country code and number
        result = self._extract_country_and_number(cleaned)
        if not result:
            return {
                'valid': False,
                'error': 'Invalid phone number format',
                'suggestion': 'Please provide in format: +[country code]-[number]',
                'phone': phone
            }
        
        country_code, number = result
        
        # Validate with country code
        return self.validate_with_country_code(f"+{country_code}{number}")
    
    def validate_indian(self, phone: str) -> Dict:
        """Validate Indian phone number"""
        cleaned = self._clean_phone(phone)
        
        # Extract digits only
        digits = re.sub(r'\D', '', cleaned)
        
        # Check if it has +91
        if cleaned.startswith('+91'):
            digits = digits[2:]  # Remove 91
        elif len(digits) == 10:
            # Assume India if 10 digits
            pass
        else:
            return {
                'valid': False,
                'error': 'Indian number must be 10 digits',
                'suggestion': 'Format: +91-9876543210',
                'phone': phone
            }
        
        # Validate Indian mobile pattern
        if not re.match(r'^[6-9]\d{9}$', digits):
            return {
                'valid': False,
                'error': 'Indian mobile numbers must start with 6, 7, 8, or 9',
                'suggestion': 'Format: +91-9876543210 (10 digits starting with 6-9)',
                'phone': phone
            }
        
        return {
            'valid': True,
            'phone': f"+91{digits}",
            'country': 'India',
            'country_code': '91',
            'formatted': f"+91-{digits[:5]} {digits[5:]}"
        }
    
    def validate_international(self, phone: str) -> Dict:
        """Validate international phone number"""
        cleaned = self._clean_phone(phone)
        
        if not cleaned.startswith('+'):
            return {
                'valid': False,
                'error': 'International number must start with + and country code',
                'suggestion': 'Format: +[country code]-[number]',
                'phone': phone
            }
        
        return self.validate_with_country_code(cleaned)
    
    def validate_with_country_code(self, phone: str) -> Dict:
        """
        Validate phone has proper country code and format
        
        This is the MAIN validation method used by FSM
        """
        if not phone:
            return {
                'valid': False,
                'error': 'Phone number is required',
                'suggestion': 'Provide WhatsApp number with country code',
                'phone': phone
            }
        
        cleaned = self._clean_phone(phone)
        
        # Must start with +
        if not cleaned.startswith('+'):
            return {
                'valid': False,
                'error': 'Must include country code (starting with +)',
                'suggestion': 'Format: +91-9876543210 (India), +977-9851234567 (Nepal)',
                'phone': phone
            }
        
        # Extract country code and number
        result = self._extract_country_and_number(cleaned)
        if not result:
            return {
                'valid': False,
                'error': 'Invalid phone number format',
                'suggestion': 'Format: +[country code]-[number]',
                'phone': phone
            }
        
        country_code, number = result
        
        # Check if we support this country
        if country_code not in self.country_rules:
            return {
                'valid': False,
                'error': f'Country code +{country_code} not supported',
                'suggestion': 'Supported: India (+91), Nepal (+977), Pakistan (+92), Bangladesh (+880), Dubai (+971)',
                'phone': phone
            }
        
        # Get country rules
        rules = self.country_rules[country_code]
        
        # Validate length
        if len(number) != rules['length']:
            return {
                'valid': False,
                'error': f"{rules['name']} numbers must be {rules['length']} digits",
                'suggestion': f"Format: {rules['format']}",
                'phone': phone
            }
        
        # Validate pattern
        if not re.match(rules['pattern'], number):
            return {
                'valid': False,
                'error': f"Invalid {rules['name']} number format",
                'suggestion': f"Format: {rules['format']}",
                'phone': phone
            }
        
        # All validations passed
        return {
            'valid': True,
            'phone': f"+{country_code}{number}",
            'country': rules['name'],
            'country_code': country_code,
            'formatted': self._format_phone_display(f"+{country_code}{number}")
        }
    
    def get_validation_error(self, phone: str) -> str:
        """Get validation error message"""
        result = self.validate(phone)
        if result['valid']:
            return ""
        return result.get('error', 'Invalid phone number')
    
    def suggest_correction(self, phone: str) -> str:
        """Suggest phone number correction"""
        result = self.validate(phone)
        if result['valid']:
            return ""
        return result.get('suggestion', 'Please provide valid phone number with country code')
    
    def _clean_phone(self, phone: str) -> str:
        """Clean phone number - keep + and digits only"""
        if not phone:
            return ""
        
        # Keep + at start and all digits
        cleaned = phone.strip()
        
        # Remove common separators but keep + at start
        if cleaned.startswith('+'):
            # Keep the +, remove everything except digits after it
            prefix = '+'
            rest = re.sub(r'[^\d]', '', cleaned[1:])
            return prefix + rest
        else:
            # Just digits
            return re.sub(r'\D', '', cleaned)
    
    def _extract_country_and_number(self, phone: str) -> Optional[tuple]:
        """
        Extract country code and number from phone
        
        Returns: (country_code, number) or None
        """
        if not phone or not phone.startswith('+'):
            return None
        
        # Remove +
        digits = phone[1:]
        
        # Try to match known country codes (1-3 digits)
        for length in [3, 2, 1]:
            if len(digits) > length:
                potential_code = digits[:length]
                if potential_code in self.country_rules:
                    number = digits[length:]
                    return (potential_code, number)
        
        return None
    
    def _format_phone_display(self, phone: str) -> str:
        """Format phone for display"""
        if not phone or not phone.startswith('+'):
            return phone
        
        result = self._extract_country_and_number(phone)
        if not result:
            return phone
        
        country_code, number = result
        
        # Format based on country
        if country_code == '91':  # India
            return f"+91-{number[:5]} {number[5:]}"
        elif country_code == '977':  # Nepal
            return f"+977-{number[:3]} {number[3:6]} {number[6:]}"
        elif country_code == '92':  # Pakistan
            return f"+92-{number[:3]} {number[3:]}"
        elif country_code == '880':  # Bangladesh
            return f"+880-{number[:4]} {number[4:]}"
        elif country_code == '971':  # Dubai
            return f"+971-{number[:2]} {number[2:5]} {number[5:]}"
        elif country_code == '1':  # USA/Canada
            return f"+1-{number[:3]} {number[3:6]} {number[6:]}"
        else:
            return f"+{country_code}-{number}"