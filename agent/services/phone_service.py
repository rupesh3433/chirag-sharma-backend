"""
Phone number formatting and validation
"""

import re
import logging
from typing import Dict, Optional

from ..config.services_config import COUNTRY_CODES
from ..utils.patterns import PHONE_PATTERNS

logger = logging.getLogger(__name__)

class PhoneService:
    """Service for phone number operations"""
    
    def __init__(self):
        self.country_codes = COUNTRY_CODES
    
    def format_for_api(self, phone: str, country: str = "India") -> str:
        """
        Format phone for API (add country code if missing)
        Input: "+919876543210" or "9876543210"
        Output: "+919876543210"
        """
        if not phone:
            return ""
        
        if phone.startswith('+'):
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 10:
                return phone
            else:
                return ""
        
        digits = re.sub(r'\D', '', phone)
        
        if len(digits) < 10:
            return ""
        
        phone_number = digits[-10:]
        country_code = self.country_codes.get(country, "+91")
        
        if country_code.startswith('+'):
            clean_code = country_code[1:]
        else:
            clean_code = country_code
        
        return f"+{clean_code}{phone_number}"
    
    def format_for_display(self, phone: str, country: str = "India") -> str:
        """
        Format phone for display
        Input: "+919876543210"
        Output: "+91 98765 43210"
        """
        if not phone:
            return ""
        
        if phone.startswith('+'):
            digits = phone[1:]
            if len(digits) >= 10:
                country_part = digits[:2] if len(digits) > 10 else "91"
                number_part = digits[-10:] if len(digits) > 10 else digits
                
                if len(number_part) == 10:
                    return f"+{country_part} {number_part[:5]} {number_part[5:]}"
                else:
                    return phone
        else:
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 10:
                number_part = digits[-10:]
                return f"+91 {number_part[:5]} {number_part[5:]}"
        
        return phone
    
    def validate_with_country_code(self, phone: str) -> Dict:
        """Validate phone number with country code"""
        if not phone:
            return {"valid": False, "error": "Phone number is required"}
        
        phone = phone.strip()
        
        # Must start with +
        if not phone.startswith('+'):
            return {
                "valid": False, 
                "error": "Phone must start with country code (e.g., +91)",
                "suggestion": "Add country code like +91-9876543210"
            }
        
        # Extract digits after +
        digits = re.sub(r'\D', '', phone[1:])
        total_digits = len(digits)
        
        logger.info(f"Phone validation: {phone}, digits: {digits}, total: {total_digits}")
        
        # Check for Indian numbers specifically
        if phone.startswith('+91'):
            if total_digits != 12:
                return {
                    "valid": False,
                    "error": f"Indian number should have 10 digits after +91 (got {total_digits - 2})",
                    "suggestion": "Format: +91-9876543210"
                }
            
            number = digits[2:]
            if number[0] not in ['6', '7', '8', '9']:
                return {
                    "valid": False,
                    "error": "Indian mobile numbers start with 6,7,8, or 9",
                    "suggestion": "Provide a valid Indian mobile number"
                }
            
            return {
                "valid": True,
                "phone": phone,
                "country": "India",
                "formatted": f"+91-{number[:5]}-{number[5:]}"
            }
        
        # For other countries
        country_code = ""
        for i in range(1, 4):
            if i <= len(digits):
                country_code = digits[:i]
                break
        
        code_map = {
            '91': 'India', '977': 'Nepal', '92': 'Pakistan', 
            '880': 'Bangladesh', '971': 'Dubai', '1': 'USA'
        }
        
        country = code_map.get(country_code)
        
        if not country:
            return {
                "valid": False,
                "error": f"Unsupported country code: +{country_code}",
                "suggestion": "Use +91 (India), +977 (Nepal), +92 (Pakistan), +880 (Bangladesh), or +971 (Dubai)"
            }
        
        min_lengths = {
            'India': 10, 'Nepal': 7, 'Pakistan': 10,
            'Bangladesh': 10, 'Dubai': 9, 'USA': 10
        }
        
        min_required = min_lengths.get(country, 7)
        number_digits = total_digits - len(country_code)
        
        if number_digits < min_required:
            return {
                "valid": False,
                "error": f"{country} number needs at least {min_required} digits after country code (got {number_digits})",
                "suggestion": f"Provide full {country} number with +{country_code}"
            }
        
        return {
            "valid": True,
            "phone": phone,
            "country": country,
            "formatted": f"+{country_code}-{digits[len(country_code):]}"
        }
    
    def get_country_from_phone(self, phone: str) -> Optional[str]:
        """Extract country from phone code"""
        if not phone or not phone.startswith('+'):
            return None
        
        # Extract digits after +
        digits = re.sub(r'\D', '', phone[1:])
        
        code_map = {
            '91': 'India', '977': 'Nepal', '92': 'Pakistan', 
            '880': 'Bangladesh', '971': 'Dubai', '1': 'USA'
        }
        
        for i in range(1, 4):
            if i <= len(digits):
                code = digits[:i]
                if code in code_map:
                    return code_map[code]
        
        return None