"""
Pincode Validator - Enhanced with comprehensive validation
"""

import re
from typing import Dict, Optional


class PincodeValidator:
    """Validate PIN/postal codes for different countries"""
    
    def __init__(self):
        """Initialize pincode validator"""
        # Country-specific pincode rules
        self.country_rules = {
            'India': {
                'length': 6,
                'pattern': r'^[1-9]\d{5}$',
                'format': '6 digits starting with 1-9',
                'example': '400001'
            },
            'Nepal': {
                'length': 5,
                'pattern': r'^\d{5}$',
                'format': '5 digits',
                'example': '44600'
            },
            'Pakistan': {
                'length': 5,
                'pattern': r'^\d{5}$',
                'format': '5 digits',
                'example': '75500'
            },
            'Bangladesh': {
                'length': 4,
                'pattern': r'^\d{4}$',
                'format': '4 digits',
                'example': '1000'
            },
            'Dubai': {
                'length': 5,
                'pattern': r'^\d{5}$',
                'format': '5 digits',
                'example': '00000'
            }
        }
        
        # Region validation for India (first digit indicates region)
        self.india_regions = {
            '1': 'Delhi, Haryana, Punjab',
            '2': 'Himachal Pradesh, Jammu & Kashmir',
            '3': 'Rajasthan, Punjab',
            '4': 'Maharashtra, Goa',
            '5': 'Karnataka, Andhra Pradesh',
            '6': 'Tamil Nadu, Kerala',
            '7': 'West Bengal, Odisha',
            '8': 'Bihar, Jharkhand',
            '9': 'Uttar Pradesh, Uttarakhand'
        }
    
    def validate(self, pincode: str, country: str) -> Dict:
        """
        Validate pincode for given country
        
        Returns:
            {
                'valid': bool,
                'pincode': str (cleaned),
                'country': str,
                'error': str (if invalid),
                'region': str (for India),
                'format': str
            }
        """
        if not pincode:
            return {
                'valid': False,
                'error': 'PIN/postal code is required',
                'pincode': ''
            }
        
        if not country:
            return {
                'valid': False,
                'error': 'Country is required to validate PIN code',
                'pincode': pincode
            }
        
        # Clean pincode
        cleaned = self._clean_pincode(pincode)
        
        # Check if country is supported
        if country not in self.country_rules:
            return {
                'valid': False,
                'error': f'PIN code validation not supported for {country}',
                'pincode': pincode,
                'country': country
            }
        
        # Get country-specific rules
        rules = self.country_rules[country]
        
        # Validate length
        if len(cleaned) != rules['length']:
            return {
                'valid': False,
                'error': f"{country} PIN codes must be {rules['length']} digits",
                'suggestion': f"Format: {rules['format']} (Example: {rules['example']})",
                'pincode': pincode,
                'country': country
            }
        
        # Validate pattern
        if not re.match(rules['pattern'], cleaned):
            return {
                'valid': False,
                'error': f"Invalid {country} PIN code format",
                'suggestion': f"Format: {rules['format']} (Example: {rules['example']})",
                'pincode': pincode,
                'country': country
            }
        
        # Country-specific validations
        if country == 'India':
            return self._validate_indian_pincode(cleaned)
        elif country == 'Nepal':
            return self._validate_nepali_pincode(cleaned)
        else:
            # Generic success for other countries
            return {
                'valid': True,
                'pincode': cleaned,
                'country': country,
                'format': rules['format']
            }
    
    def validate_indian(self, pincode: str) -> bool:
        """Validate Indian pincode (returns bool for backward compatibility)"""
        result = self._validate_indian_pincode(pincode)
        return result['valid']
    
    def validate_nepali(self, pincode: str) -> bool:
        """Validate Nepali pincode (returns bool for backward compatibility)"""
        result = self._validate_nepali_pincode(pincode)
        return result['valid']
    
    def get_validation_error(self, pincode: str, country: str) -> str:
        """Get validation error message"""
        result = self.validate(pincode, country)
        
        if result['valid']:
            return ""
        
        return result.get('error', 'Invalid PIN code')
    
    def _clean_pincode(self, pincode: str) -> str:
        """Clean pincode - keep only digits"""
        if not pincode:
            return ""
        
        # Remove all non-digit characters
        cleaned = re.sub(r'\D', '', pincode.strip())
        
        return cleaned
    
    def _validate_indian_pincode(self, pincode: str) -> Dict:
        """Validate Indian pincode with region detection"""
        cleaned = self._clean_pincode(pincode)
        
        # Must be 6 digits
        if len(cleaned) != 6:
            return {
                'valid': False,
                'error': 'Indian PIN codes must be 6 digits',
                'suggestion': 'Example: 400001 (Mumbai)',
                'pincode': pincode
            }
        
        # Must start with 1-9 (not 0)
        if cleaned[0] == '0':
            return {
                'valid': False,
                'error': 'Indian PIN codes cannot start with 0',
                'suggestion': 'Example: 400001, 110001, 560001',
                'pincode': pincode
            }
        
        # Get region from first digit
        first_digit = cleaned[0]
        region = self.india_regions.get(first_digit, 'Unknown region')
        
        return {
            'valid': True,
            'pincode': cleaned,
            'country': 'India',
            'region': region,
            'format': '6 digits'
        }
    
    def _validate_nepali_pincode(self, pincode: str) -> Dict:
        """Validate Nepali pincode"""
        cleaned = self._clean_pincode(pincode)
        
        # Must be 5 digits
        if len(cleaned) != 5:
            return {
                'valid': False,
                'error': 'Nepali postal codes must be 5 digits',
                'suggestion': 'Example: 44600 (Kathmandu)',
                'pincode': pincode
            }
        
        # All digits (0-9 allowed)
        if not cleaned.isdigit():
            return {
                'valid': False,
                'error': 'Nepali postal codes must contain only digits',
                'pincode': pincode
            }
        
        # Region detection for Nepal (basic)
        region = self._get_nepali_region(cleaned)
        
        return {
            'valid': True,
            'pincode': cleaned,
            'country': 'Nepal',
            'region': region,
            'format': '5 digits'
        }
    
    def _get_nepali_region(self, pincode: str) -> str:
        """Get region from Nepali pincode (basic mapping)"""
        if not pincode or len(pincode) != 5:
            return 'Unknown'
        
        # Basic region mapping (first 2 digits)
        prefix = pincode[:2]
        
        nepal_regions = {
            '44': 'Kathmandu Valley',
            '33': 'Pokhara',
            '56': 'Biratnagar',
            '10': 'Far Western Region',
            '21': 'Mid Western Region',
            '45': 'Lalitpur',
            '46': 'Bhaktapur'
        }
        
        return nepal_regions.get(prefix, 'Nepal')
    
    def infer_country_from_pincode(self, pincode: str) -> Optional[str]:
        """Infer country from pincode length and format"""
        if not pincode:
            return None
        
        cleaned = self._clean_pincode(pincode)
        length = len(cleaned)
        
        # Try to infer based on length and pattern
        if length == 6 and cleaned[0] != '0':
            # Likely India
            return 'India'
        elif length == 5:
            # Could be Nepal, Pakistan, or Dubai
            # Default to Nepal if no other info
            return 'Nepal'
        elif length == 4:
            # Likely Bangladesh
            return 'Bangladesh'
        
        return None