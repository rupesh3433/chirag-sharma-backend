# agent/extractors/address_extractor.py
"""
Ultra-Enhanced Address Extractor - Removes all other fields FIRST
"""

import re
from typing import Optional, Dict, Any, List
from .base_extractor import BaseExtractor


class AddressExtractor(BaseExtractor):
    """Extract addresses with comprehensive field removal"""
    
    # Address indicators
    ADDRESS_INDICATORS = [
        'street', 'st', 'road', 'rd', 'avenue', 'ave', 'lane', 'ln',
        'block', 'sector', 'phase', 'society', 'colony', 'nagar',
        'apartment', 'apt', 'flat', 'house', 'building', 'tower',
        'floor', 'plot', 'area', 'layout', 'extension', 'ext',
        'cross', 'main', 'near', 'opposite', 'opp', 'behind', 'beside',
        'park', 'market', 'bazar', 'bazaar', 'mall', 'plaza',
        'town', 'city', 'village', 'district', 'state', 'province'
    ]
    
    # Indian specific
    INDIAN_KEYWORDS = [
        'colony', 'nagar', 'puram', 'bagh', 'ganj', 'mohalla',
        'chowk', 'marg', 'vihar', 'enclave', 'kunj', 'peth',
        'layout', 'extension', 'stage', 'cross', 'circle'
    ]
    
    # Major cities/locations
    LOCATION_NAMES = [
        'delhi', 'mumbai', 'bangalore', 'chennai', 'kolkata', 'hyderabad',
        'pune', 'ahmedabad', 'jaipur', 'lucknow', 'kanpur', 'nagpur',
        'indore', 'thane', 'bhopal', 'visakhapatnam', 'pimpri', 'patna',
        'vadodara', 'ghaziabad', 'ludhiana', 'agra', 'nashik', 'faridabad',
        'meerut', 'rajkot', 'kalyan', 'vasai', 'varanasi', 'srinagar',
        'kathmandu', 'pokhara', 'lalitpur', 'biratnagar', 'bharatpur',
        'dharan', 'butwal', 'hetauda', 'pokhara', 'birgunj',
        'karachi', 'lahore', 'islamabad', 'rawalpindi', 'faisalabad',
        'dhaka', 'chittagong', 'sylhet', 'khulna', 'rajshahi',
        'dubai', 'abu dhabi', 'sharjah', 'ajman', 'fujairah'
    ]
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """
        Extract address with aggressive field removal
        """
        if not message or len(message.strip()) == 0:
            return None
        
        original_message = message
        
        # Step 1: AGGRESSIVELY remove all other fields
        cleaned = self._remove_all_non_address_fields(message, context)
        
        # Step 2: If nothing left, return None
        if not cleaned or len(cleaned.strip()) < 3:
            return None
        
        # Step 3: Validate remaining text looks like address
        if not self._looks_like_address(cleaned):
            return None
        
        # Step 4: Extract and format address
        address_result = self._extract_and_format_address(cleaned, original_message)
        
        return address_result
    
    def _remove_all_non_address_fields(self, message: str, context: Optional[Dict] = None) -> str:
        """
        AGGRESSIVELY remove ALL non-address fields
        """
        cleaned = message
        
        # ========================================
        # 1. REMOVE PHONE NUMBERS (ALL FORMATS)
        # ========================================
        phone_patterns = [
            r'\+\d{1,4}[-\s]?\d{6,15}',           # +91-9876543210, +91 9876543210
            r'\+\d{10,15}',                        # +919876543210
            r'\(\d{2,4}\)[-\s]?\d{6,15}',         # (91)-9876543210
            r'\b\d{10,15}\b',                      # 9876543210
            r'\d{3}[-\s]?\d{3}[-\s]?\d{4}',       # 123-456-7890
            r'\(\d{3}\)\s?\d{3}[-\s]?\d{4}',      # (123) 456-7890
        ]
        for pattern in phone_patterns:
            cleaned = re.sub(pattern, ' ', cleaned)
        
        # ========================================
        # 2. REMOVE EMAIL ADDRESSES
        # ========================================
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        cleaned = re.sub(email_pattern, ' ', cleaned)
        
        # ========================================
        # 3. REMOVE DATES (COMPREHENSIVE)
        # ========================================
        date_patterns = [
            # ISO format: 2025-04-15, 2025/04/15
            r'\b\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}\b',
            
            # Numeric: 15/04/2025, 15-04-2025, 15.04.2025
            r'\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\b',
            
            # Month names: April 15, 2025 / 15 April 2025 / April 15 2025
            r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{4}\b',
            r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*,?\s*\d{4}\b',
            
            # Compact: 2feb2026, 2 feb 2026, 15march2025
            r'\b\d{1,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*\d{4}\b',
            
            # Partial dates: 15 April, April 15, 2feb
            r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?\b',
            r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b',
            r'\b\d{1,2}(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b',
            
            # Written: "15th of April", "the 25th of June"
            r'\b\d{1,2}(?:st|nd|rd|th)?\s+of\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b',
            r'\bthe\s+\d{1,2}(?:st|nd|rd|th)?\s+of\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b',
            
            # Relative: tomorrow, next week, last month, etc.
            r'\b(?:today|tomorrow|yesterday)\b',
            r'\b(?:this|next|last)\s+(?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            r'\b(?:next|last)\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\b',
        ]
        
        for pattern in date_patterns:
            cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
        
        # ========================================
        # 4. REMOVE PIN CODES / POSTAL CODES
        # ========================================
        # Be smart: only remove if clearly separated (not part of address number)
        pincode_patterns = [
            r',\s*\d{5,6}\s*(?:,|$)',             # , 110001, or , 110001 at end
            r'^\s*\d{5,6}\s*,',                    # 110001, at start
            r'\b(?:pin|pincode|postal|zip)[\s:-]*\d{5,6}\b',  # PIN: 110001
            r'(?<=\s)\d{6}(?=\s*(?:,|$))',       # Space 110001 at end
        ]
        
        for pattern in pincode_patterns:
            cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
        
        # ========================================
        # 5. REMOVE PERSON NAMES (from context or patterns)
        # ========================================
        if context:
            # Remove name from context
            if 'name' in context and context['name']:
                name = str(context['name']).strip()
                # Remove full name
                cleaned = re.sub(re.escape(name), ' ', cleaned, flags=re.IGNORECASE)
                # Remove name parts
                for name_part in name.split():
                    if len(name_part) > 2:  # Avoid single letters
                        cleaned = re.sub(rf'\b{re.escape(name_part)}\b', ' ', cleaned, flags=re.IGNORECASE)
        
        # Remove common name patterns (at start or surrounded by commas)
        name_patterns = [
            r'^[A-Z][a-z]+\s+[A-Z][a-z]+\s*,',     # Ramesh Kumar,
            r',\s*[A-Z][a-z]+\s+[A-Z][a-z]+\s*,',  # , Ramesh Kumar,
            r',\s*[A-Z][a-z]+\s+[A-Z][a-z]+\s*$',  # , Ramesh Kumar
        ]
        
        for pattern in name_patterns:
            cleaned = re.sub(pattern, ', ', cleaned)
        
        # ========================================
        # 6. REMOVE COUNTRY NAMES (if standalone)
        # ========================================
        countries = [
            'india', 'nepal', 'pakistan', 'bangladesh', 'sri lanka',
            'dubai', 'uae', 'united arab emirates',
            'usa', 'united states', 'uk', 'united kingdom',
            'canada', 'australia', 'singapore', 'malaysia'
        ]
        
        for country in countries:
            # Only remove if at end or clearly separated
            cleaned = re.sub(rf',\s*{country}\s*(?:,|$)', ', ', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(rf'\b{country}\s*(?:,|$)', ' ', cleaned, flags=re.IGNORECASE)
        
        # ========================================
        # 7. REMOVE COMMON NON-ADDRESS PHRASES
        # ========================================
        remove_phrases = [
            r'\bmy name is\b',
            r'\bname is\b',
            r'\bemail is\b',
            r'\bphone is\b',
            r'\bphone number is\b',
            r'\bcontact is\b',
            r'\bcontact number is\b',
            r'\bdate is\b',
            r'\bevent date is\b',
            r'\bevent on\b',
            r'\bscheduled for\b',
            r'\bon the\b(?=\s+\d)',  # "on the 15th" (date context)
        ]
        
        for phrase in remove_phrases:
            cleaned = re.sub(phrase, ' ', cleaned, flags=re.IGNORECASE)
        
        # ========================================
        # 8. CLEANUP: Remove extra commas, spaces
        # ========================================
        # Remove multiple commas
        cleaned = re.sub(r',\s*,+', ',', cleaned)
        # Remove leading/trailing commas
        cleaned = re.sub(r'^\s*,+\s*|\s*,+\s*$', '', cleaned)
        # Remove multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)
        # Final trim
        cleaned = cleaned.strip()
        
        return cleaned
    
    def _looks_like_address(self, text: str) -> bool:
        """
        Check if remaining text looks like an address
        """
        if not text or len(text.strip()) < 3:
            return False
        
        text_lower = text.lower()
        
        # Check for address keywords
        for keyword in self.ADDRESS_INDICATORS + self.INDIAN_KEYWORDS:
            if keyword in text_lower:
                return True
        
        # Check for location names
        for location in self.LOCATION_NAMES:
            if location in text_lower:
                return True
        
        # Check for patterns: "123 Something", "Flat 45", "Block A"
        if re.search(r'\b(?:flat|apartment|apt|house|plot|block)\s+\w+', text_lower):
            return True
        
        if re.search(r'\b\d+\s+\w+', text):  # Number followed by text
            return True
        
        # If text has 2+ words and at least one comma, might be address
        if ',' in text and len(text.split()) >= 2:
            return True
        
        return False
    
    def _extract_and_format_address(self, cleaned: str, original: str) -> Optional[Dict]:
        """
        Extract and format the address from cleaned text
        """
        if not cleaned or len(cleaned.strip()) < 3:
            return None
        
        # Remove leading/trailing commas and spaces
        address = cleaned.strip().strip(',').strip()
        
        # If address is too short, return None
        if len(address) < 5:
            return None
        
        # Split by comma and clean parts
        parts = [p.strip() for p in address.split(',') if p.strip()]
        
        # If only one part and it's short, might not be valid
        if len(parts) == 1 and len(parts[0]) < 10:
            # Check if it's a known city
            if parts[0].lower() not in self.LOCATION_NAMES:
                return None
        
        # Rejoin cleaned parts
        final_address = ', '.join(parts)
        
        # Determine confidence
        confidence = self._determine_confidence(final_address)
        
        return {
            'address': final_address,
            'confidence': confidence,
            'method': 'field_removal',
            'original': original,
            'parts': parts
        }
    
    def _determine_confidence(self, address: str) -> str:
        """
        Determine confidence level of extracted address
        """
        address_lower = address.lower()
        score = 0
        
        # Check for address keywords
        for keyword in self.ADDRESS_INDICATORS[:10]:  # Top indicators
            if keyword in address_lower:
                score += 2
        
        # Check for location names
        for location in self.LOCATION_NAMES[:30]:  # Major cities
            if location in address_lower:
                score += 3
        
        # Check for Indian keywords
        for keyword in self.INDIAN_KEYWORDS:
            if keyword in address_lower:
                score += 2
        
        # Check for number patterns
        if re.search(r'\b\d+\b', address):
            score += 1
        
        # Check for multiple parts (commas)
        comma_count = address.count(',')
        if comma_count >= 1:
            score += comma_count
        
        # Determine confidence
        if score >= 8:
            return 'high'
        elif score >= 4:
            return 'medium'
        else:
            return 'low'
    
    def clean_message(self, message: str) -> str:
        """Basic message cleaning"""
        message = ' '.join(message.split())
        return message