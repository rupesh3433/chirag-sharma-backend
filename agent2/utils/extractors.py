"""
Enhanced Field Extractor
Uses config patterns for robust extraction with question detection
"""

import re
import logging
import sys
from typing import Dict, Optional, List, Tuple
from datetime import datetime

# Increase recursion limit to prevent infinite recursion errors
sys.setrecursionlimit(10000)

from ..config.config import (
    PHONE_PATTERNS,
    EMAIL_PATTERNS,
    DATE_EXTRACTION_PATTERNS,
    PINCODE_PATTERNS,
    ADDRESS_INDICATORS,
    ADDRESS_COMPONENTS,
    CITY_NAMES,
    NAME_PATTERNS,
    COUNTRIES,
    OBFUSCATED_EMAIL_PATTERNS,
    VALIDATION_PATTERNS,
    SERVICES
)

from ..utils.question_detector import QuestionDetector

logger = logging.getLogger(__name__)


class FieldExtractor:
    """Enhanced field extractor using config patterns with question detection"""
    
    def __init__(self, question_detector=None):
        """Initialize with config patterns"""
        self.services = SERVICES
        self.city_names = CITY_NAMES
        self.question_detector = question_detector
        
        # Compile patterns
        self.email_regexes = self._compile_pattern_list(EMAIL_PATTERNS)
        self.obfuscated_email_regexes = self._compile_pattern_list(OBFUSCATED_EMAIL_PATTERNS)
        self.pincode_regex = self._compile_primary_pattern(PINCODE_PATTERNS, r'\b([1-9][0-9]{3,5})\b')
        self.pincode_regexes = self._compile_pattern_list(PINCODE_PATTERNS)
        self.phone_regexes = self._compile_phone_patterns(PHONE_PATTERNS)
        self.date_regexes = self._compile_pattern_list(DATE_EXTRACTION_PATTERNS)
        self.name_regexes = self._compile_pattern_list(NAME_PATTERNS)
        
        logger.info(f"✅ FieldExtractor initialized")
    
    def _compile_pattern_list(self, patterns: List[str]) -> List[re.Pattern]:
        """Safely compile a list of regex patterns"""
        compiled = []
        if patterns:
            for pattern in patterns:
                try:
                    cleaned = ' '.join(pattern.split())
                    compiled.append(re.compile(cleaned, re.IGNORECASE))
                except re.error as e:
                    logger.debug(f"Invalid pattern skipped: {pattern[:50]}... Error: {e}")
        return compiled
    
    def _compile_primary_pattern(self, patterns: List[str], fallback: str) -> re.Pattern:
        """Compile primary pattern with fallback"""
        if patterns:
            try:
                primary = patterns[0]
                cleaned = ' '.join(primary.split())
                return re.compile(cleaned, re.IGNORECASE)
            except re.error as e:
                logger.warning(f"Failed to compile primary pattern: {e}")
        return re.compile(fallback, re.IGNORECASE)
    
    def _compile_phone_patterns(self, patterns_dict: Dict) -> Dict[str, re.Pattern]:
        """Compile phone patterns dictionary"""
        compiled = {}
        if patterns_dict:
            for name, pattern in patterns_dict.items():
                try:
                    if isinstance(pattern, str):
                        lines = pattern.strip().split('\n')
                        cleaned_lines = []
                        for line in lines:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                cleaned_lines.append(line)
                        cleaned = ' '.join(cleaned_lines)
                        compiled[name] = re.compile(cleaned, re.IGNORECASE | re.VERBOSE)
                except re.error as e:
                    logger.debug(f"Phone pattern '{name}' skipped: {e}")
        return compiled
    
    def _clean_field(self, field_type: str, value: str) -> str:
        """Clean extracted field"""
        if not value:
            return value
        
        # Basic cleaning patterns
        cleaning_patterns = {
            'email': [(r'\s+', ''), (r'[<>]', '')],
            'phone': [(r'\s+', ''), (r'[()\-]', '')],
            'name': [(r'\s+', ' '), (r'[^\w\s\.\-]', '')],
            'address': [(r'\s+', ' '), (r',\s*,', ',')],
            'pincode': [(r'\s+', ''), (r'[^\d]', '')]
        }
        
        patterns = cleaning_patterns.get(field_type, [])
        cleaned = value
        
        for pattern, replacement in patterns:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        
        return cleaned.strip()
    
    def extract_email(self, text: str) -> Optional[str]:
        """Extract email from text"""
        # Skip if it's a question
        if self.question_detector and self.question_detector.is_question_during_booking(text, "COLLECTING_DETAILS"):
            return None
        
        # Simple email pattern first
        simple_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        if simple_match:
            email = simple_match.group(0).lower()
            logger.debug(f"📧 Simple email extracted: {email}")
            return self._clean_field('email', email)
        
        # Try obfuscated patterns
        for regex in self.obfuscated_email_regexes:
            match = regex.search(text, re.IGNORECASE)
            if match and match.groups():
                parts = [g for g in match.groups() if g]
                if len(parts) >= 3:
                    username = parts[0].replace(' ', '')
                    domain = parts[1].replace(' ', '')
                    tld = parts[2].replace(' ', '')
                    email = f"{username}@{domain}.{tld}".lower()
                    logger.debug(f"📧 Obfuscated email reconstructed: {email}")
                    return self._clean_field('email', email)
        
        # Try all email patterns
        for i, regex in enumerate(self.email_regexes):
            match = regex.search(text)
            if match:
                if match.groups():
                    for group in match.groups():
                        if group and '@' in group:
                            email = group.lower()
                            logger.debug(f"📧 Email extracted (pattern {i}, group): {email}")
                            return self._clean_field('email', email)
                
                email = match.group(0).lower()
                if '@' in email:
                    logger.debug(f"📧 Email extracted (pattern {i}, full): {email}")
                    return self._clean_field('email', email)
        
        return None
    
    def extract_phone(self, text: str) -> Optional[str]:
        """Extract phone number from text"""
        # Skip if it's a question
        if self.question_detector and self.question_detector.is_question_during_booking(text, "COLLECTING_DETAILS"):
            return None
        
        # Try all phone patterns
        for pattern_name, regex in self.phone_regexes.items():
            match = regex.search(text)
            if match:
                phone = None
                if match.groups():
                    for group in match.groups():
                        if group:
                            phone = group
                            break
                
                if not phone:
                    phone = match.group(0)
                
                if phone:
                    cleaned = self._clean_field('phone', phone)
                    
                    # Validate and format
                    if len(re.sub(r'\D', '', cleaned)) >= 10:
                        if not cleaned.startswith('+'):
                            digits = re.sub(r'\D', '', cleaned)
                            if len(digits) == 10 and digits[0] in '6789':
                                cleaned = f"+91{digits}"
                            elif len(digits) > 10:
                                cleaned = f"+91{digits[-10:]}"
                        
                        logger.debug(f"📞 Phone extracted ({pattern_name}): {cleaned}")
                        return cleaned
        
        # Fallback
        phone_match = re.search(r'(\+?\d[\d\s\-\(\)]{9,}\d)', text)
        if phone_match:
            phone = phone_match.group(1)
            cleaned = self._clean_field('phone', phone)
            if len(re.sub(r'\D', '', cleaned)) >= 10:
                logger.debug(f"📞 Phone extracted (fallback): {cleaned}")
                return cleaned
        
        return None
    
    def extract_pincode(self, text: str) -> Optional[str]:
        """Extract pincode from text"""
        # Skip if it's a question
        if self.question_detector and self.question_detector.is_question_during_booking(text, "COLLECTING_DETAILS"):
            return None
        
        # Try primary pattern
        match = self.pincode_regex.search(text)
        if match:
            pincode = match.group(1) if match.groups() else match.group(0)
            if pincode and 4 <= len(pincode) <= 6 and pincode.isdigit():
                logger.debug(f"📮 Pincode extracted: {pincode}")
                return pincode
        
        # Try all patterns
        for regex in self.pincode_regexes:
            match = regex.search(text)
            if match:
                pincode = match.group(1) if match.groups() else match.group(0)
                if pincode and 4 <= len(pincode) <= 6 and pincode.isdigit():
                    logger.debug(f"📮 Pincode extracted (alternative): {pincode}")
                    return pincode
        
        return None
    
    def extract_name(self, text: str) -> Optional[str]:
        """Extract name from text - SIMPLIFIED to avoid recursion"""
        # Skip if too short
        if len(text) < 2:
            return None
        
        text = text.strip()
        text_lower = text.lower()
        
        # Skip obvious locations and questions
        skip_indicators = [
            'pune', 'mumbai', 'delhi', 'bangalore', 'hyderabad',
            'maharashtra', 'gujarat', 'rajasthan', 'what', 'how',
            'where', 'when', 'why', 'which', 'address', 'location',
            'city', 'state', 'country', 'pin', 'pincode', 'zip'
        ]
        
        if any(indicator in text_lower for indicator in skip_indicators):
            return None
        
        # Check for email or phone patterns
        if '@' in text or re.search(r'\b\d{10}\b', text):
            return None
        
        # Check if text contains digits (likely not a name)
        if any(c.isdigit() for c in text):
            return None
        
        # Simple name pattern: Capitalized words, no digits, 2-4 words
        if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}$', text):
            # Additional validation - not a known city
            if text.title() not in self.city_names:
                return text
        
        # Try config patterns for more complex names
        for regex in self.name_regexes:
            match = regex.search(text)
            if match:
                name = match.group(1) if match.groups() else match.group(0)
                if name and self._is_valid_name(name):
                    logger.debug(f"👤 Name extracted (pattern): {name}")
                    return self._clean_field('name', name)
        
        return None
    
    def _is_valid_name(self, text: str) -> bool:
        """Check if text looks like a valid name"""
        if not text or len(text) < 2:
            return False
        
        text_lower = text.lower()
        
        # Skip if it's a known city
        if text_lower in self.city_names:
            return False
        
        # Skip location words
        location_words = ['road', 'street', 'lane', 'avenue', 'colony', 'sector',
                         'nagar', 'marg', 'gali', 'chowk', 'area', 'city', 'town',
                         'village', 'district', 'state', 'country']
        
        if any(word in text_lower for word in location_words):
            return False
        
        # Skip questions
        question_starters = ['what', 'how', 'where', 'when', 'why', 'can', 'could']
        if any(text_lower.startswith(starter) for starter in question_starters):
            return False
        
        # Check for email or phone
        if '@' in text or '+' in text or any(c.isdigit() for c in text):
            return False
        
        # Must have alphabetic characters
        if not any(c.isalpha() for c in text):
            return False
        
        # Check name pattern
        name_pattern = VALIDATION_PATTERNS.get('name')
        if name_pattern and not re.match(name_pattern, text):
            return False
        
        # Check word capitalization (for multi-word names)
        words = text.split()
        if len(words) > 1:
            for word in words:
                if word and not word[0].isalpha():
                    return False
        
        return True
    
    def extract_date(self, text: str) -> Optional[str]:
        """Extract date from text with better pattern matching"""
        # Skip if it's off-topic
        if self.question_detector and self.question_detector.is_off_topic(text, "COLLECTING_DETAILS"):
            return None
        
        # Try config patterns first
        for regex in self.date_regexes:
            match = regex.search(text)
            if match:
                date_str = match.group(1) if match.groups() else match.group(0)
                logger.debug(f"📅 Date extracted (pattern): {date_str}")
                return date_str
        
        # Additional date patterns for common formats
        additional_patterns = [
            # "25 th nov 2026" pattern
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{4})',
            # "november 25 2026" pattern  
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s*(\d{4})',
            # "25-11-2026" pattern
            r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})'
        ]
        
        for pattern in additional_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    # Format the date
                    if len(match.groups()) == 3:
                        groups = match.groups()
                        # Handle different pattern orders
                        if groups[0].isdigit() and len(groups[0]) <= 2:
                            # "25 nov 2026" format
                            day = groups[0].zfill(2)
                            month = groups[1][:3].lower()
                            year = groups[2]
                        elif groups[1].isdigit() and len(groups[1]) <= 2:
                            # "nov 25 2026" format
                            month = groups[0][:3].lower()
                            day = groups[1].zfill(2)
                            year = groups[2]
                        else:
                            # "25-11-2026" format
                            day = groups[0].zfill(2)
                            month_num = int(groups[1])
                            month_names = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 
                                         'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
                            month = month_names[month_num-1] if 1 <= month_num <= 12 else 'jan'
                            year = groups[2]
                        
                        # Convert month name to number
                        month_map = {
                            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                        }
                        month_num = month_map.get(month, '01')
                        
                        date_str = f"{year}-{month_num}-{day}"
                        logger.debug(f"📅 Date extracted (additional pattern): {date_str}")
                        return date_str
                except Exception as e:
                    logger.debug(f"Date parsing error: {e}")
        
        # Look for year-only patterns when user says they already provided date
        if any(word in text.lower() for word in ['date', 'already', 'gave', 'provided']):
            year_match = re.search(r'\b(20[2-9][0-9])\b', text)
            if year_match:
                year = year_match.group(1)
                # Use current date with provided year
                today = datetime.now()
                date_str = f"{year}-{today.month:02d}-{today.day:02d}"
                logger.debug(f"📅 Year extracted from context: {date_str}")
                return date_str
        
        return None
    
    def extract_address(self, text: str) -> Optional[str]:
        """Extract address from text - IMPROVED"""
        # Skip if it's off-topic
        if self.question_detector and self.question_detector.is_off_topic(text, "COLLECTING_DETAILS"):
            logger.debug(f"⚠️ Skipping address extraction for off-topic: {text[:50]}")
            return None
        
        text_lower = text.lower()
        
        # Skip social media
        social_keywords = ['instagram', 'facebook', 'twitter', 'youtube', 'link', 'profile']
        if any(keyword in text_lower for keyword in social_keywords):
            return None
        
        # Skip question starters
        question_starters = ['what', 'how', 'where', 'when', 'why', 'can', 'could']
        if any(text_lower.startswith(starter) for starter in question_starters):
            return None
        
        # Check for common city names (even without "address" keyword)
        common_cities = [
            'pune', 'mumbai', 'delhi', 'bangalore', 'hyderabad', 'chennai',
            'kolkata', 'ahmedabad', 'jaipur', 'lucknow', 'nagpur', 'indore',
            'thane', 'bhopal', 'visakhapatnam', 'patna', 'vadodara'
        ]
        
        found_cities = []
        for city in common_cities:
            if city in text_lower:
                found_cities.append(city.title())
        
        if found_cities:
            # Check if there's more context (state, area, etc.)
            state_patterns = [
                'maharastra', 'maharashtra', 'up', 'uttar pradesh', 'delhi',
                'karnataka', 'tamil nadu', 'west bengal', 'gujarat', 'rajasthan'
            ]
            
            found_states = []
            for state in state_patterns:
                if state in text_lower:
                    found_states.append(state.title())
            
            # Build address
            address_parts = []
            if found_cities:
                address_parts.extend(found_cities)
            if found_states:
                address_parts.extend(found_states)
            
            if address_parts:
                address = ', '.join(address_parts)
                logger.debug(f"📍 City/state extracted: {address}")
                return address
        
        # Check for address indicators
        if any(indicator in text_lower for indicator in ADDRESS_INDICATORS):
            for indicator in ADDRESS_INDICATORS:
                pattern = fr'{indicator}\s*[:=\-]?\s*([^,.\n]{{10,}})'
                match = re.search(pattern, text_lower)
                if match:
                    address = match.group(1).strip()
                    if len(address) >= 10:
                        logger.debug(f"📍 Address extracted (indicator): {address}")
                        return address
        
        # Check for comma-separated location
        if ',' in text and len(text) > 10:
            parts = [p.strip() for p in text.split(',')]
            if len(parts) >= 2:
                valid_parts = []
                for part in parts:
                    if self._looks_like_location_component(part):
                        valid_parts.append(part)
                
                if len(valid_parts) >= 2:
                    address = ', '.join(valid_parts)
                    logger.debug(f"📍 Address extracted (comma): {address}")
                    return address
        
        # Check if text looks like a standalone location
        if self._looks_like_location_component(text):
            logger.debug(f"📍 Standalone location: {text}")
            return text
        
        return None
    
    def _looks_like_location_component(self, text: str) -> bool:
        """Check if text looks like a location component - FIXED to avoid recursion"""
        if not text or len(text) < 3:
            return False
        
        text_lower = text.lower()
        
    # Check for digits first (pincodes, etc.)
        if text.isdigit() and 4 <= len(text) <= 6:
            return True
        
        # Skip obvious booking details using direct patterns (not recursive)
        if re.search(r'\b\d{10}\b', text) or '@' in text_lower:
            return False
        
        # Check city names
        if text_lower in self.city_names or any(city in text_lower for city in self.city_names):
            return True
        
        # Check address components
        if any(component in text_lower for component in ADDRESS_COMPONENTS):
            return True
        
        # Check for common location words
        location_words = [
            'road', 'street', 'lane', 'avenue', 'colony', 'sector',
            'nagar', 'marg', 'gali', 'chowk', 'area', 'city', 'town',
            'village', 'district', 'state', 'country', 'pune', 'mumbai'
        ]
        
        if any(word in text_lower for word in location_words):
            return True
        
        # Check for mixed case (e.g., "Pune Maharashtra")
        words = text.split()
        if len(words) > 1:
            if any(word and word[0].isupper() for word in words):
                return True
        
        return False
    
    def extract_country(self, text: str) -> Optional[str]:
        """Extract country from text - IMPROVED"""
        # Skip if it's off-topic
        if self.question_detector and self.question_detector.is_off_topic(text, "COLLECTING_DETAILS"):
            return None
        
        text_lower = text.lower()
        
        # Extended country list with variations
        country_map = {
            'india': 'India',
            'indian': 'India',
            'bharat': 'India',
            'nepal': 'Nepal',
            'nepali': 'Nepal',
            'dubai': 'Dubai',
            'uae': 'Dubai',
            'united arab emirates': 'Dubai',
            'pakistan': 'Pakistan',
            'pakistani': 'Pakistan',
            'bangladesh': 'Bangladesh',
            'bangladeshi': 'Bangladesh',
            'sri lanka': 'Sri Lanka',
            'srilanka': 'Sri Lanka'
        }
        
        # Check for country names
        for country_key, country_value in country_map.items():
            if country_key in text_lower:
                logger.debug(f"🌍 Country extracted: {country_value}")
                return country_value
        
        # Check for state names that imply India
        indian_states = [
            'maharashtra', 'maharastra', 'delhi', 'mumbai', 'pune',
            'bangalore', 'chennai', 'kolkata', 'hyderabad', 'gujarat',
            'rajasthan', 'uttar pradesh', 'up', 'tamil nadu'
        ]
        
        if any(state in text_lower for state in indian_states):
            logger.debug(f"🌍 Implied country (Indian state): India")
            return "India"
        
        return None
    
    def _contains_booking_details(self, text: str) -> bool:
        """Check if text contains booking details - FIXED to avoid recursion"""
        # Simple pattern checks without calling other extractors
        patterns = [
            # Phone patterns (10 digits, with/without +)
            r'\+\d{10,}',
            r'\b\d{10}\b',
            
            # Email pattern
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            
            # Pincode pattern
            r'\b\d{4,6}\b',
            
            # Obfuscated email patterns (simplified)
            r'[\w\s]+ at [\w\s]+ dot [a-z]{2,}',
            r'[\w\s]+\[at\][\w\s]+\[dot\][a-z]{2,}'
        ]
        
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        # Check for name-like patterns without recursion
        # Look for capitalized words that aren't locations
        if re.search(r'^[A-Z][a-z]+\s+[A-Z][a-z]+$', text):
            # Quick check if it's a known city name
            text_lower = text.lower()
            if not any(city in text_lower for city in self.city_names):
                return True
        
        return False
    
    def extract_all_fields(self, text: str) -> Dict[str, str]:
        """Extract all possible fields from text"""
        extracted = {}
        
        # Skip extraction if it's a question
        if self.question_detector and self.question_detector.is_question_during_booking(text, "COLLECTING_DETAILS"):
            logger.debug(f"⚠️ Skipping field extraction for question: {text[:50]}")
            return extracted
        
        # Extract in priority order
        phone = self.extract_phone(text)
        if phone:
            extracted['phone'] = phone
        
        email = self.extract_email(text)
        if email:
            extracted['email'] = email
        
        name = self.extract_name(text)
        if name:
            extracted['name'] = name
        
        pincode = self.extract_pincode(text)
        if pincode and (not phone or pincode not in phone):
            extracted['pincode'] = pincode
        
        date = self.extract_date(text)
        if date:
            extracted['date'] = date
        
        if not phone and not email:
            address = self.extract_address(text)
            if address:
                extracted['address'] = address
        
        country = self.extract_country(text)
        if country:
            extracted['service_country'] = country
        
        logger.debug(f"🔍 Extracted {len(extracted)} fields: {list(extracted.keys())}")
        return extracted

    def _looks_like_standalone_name(self, text: str) -> bool:
        """Check if text looks like a standalone name - UPDATED to avoid recursion"""
        # Skip if it's off-topic
        if self.question_detector and self.question_detector.is_off_topic(text, "COLLECTING_DETAILS"):
            return False
        
        # Check if it's actually a question about details
        question_keywords = ['what', 'which', 'how', 'when', 'where', 'why', 'details', 'information']
        if any(keyword in text.lower() for keyword in question_keywords):
            return False
        
        words = text.split()
        if not 2 <= len(words) <= 4:
            return False
        
        # Check capitalization
        if not all(word and word[0].isupper() for word in words if word.isalpha()):
            return False
        
        # Check for invalid characters
        if any(c.isdigit() for c in text) or '@' in text or '+' in text:
            return False
        
        # Check against services and cities
        if text in self.services:
            return False
        
        if any(word.lower() in self.city_names for word in words):
            return False
        
        # Valid name characters only
        if not re.match(r'^[A-Za-z\s\.\-]+$', text):
            return False
        
        return True


# Convenience functions

def extract_fields_smart(text: str, question_detector=None) -> Dict[str, str]:
    """
    Smart field extraction with question detection
    """
    extractor = FieldExtractor(question_detector)
    
    # Single word handling
    if len(text.split()) == 1:
        cleaned = text.strip()
        
        # Pincode check
        if cleaned.isdigit() and 4 <= len(cleaned) <= 6:
            return {'pincode': cleaned}
        
        # Name check (single word, capitalized, not digit)
        if cleaned[0].isupper() and len(cleaned) >= 2 and not cleaned.isdigit():
            # Check it's not a city
            if cleaned.lower() not in CITY_NAMES:
                return {'name': cleaned}
    
    return extractor.extract_all_fields(text)


def validate_extracted_fields(fields: Dict[str, str]) -> Tuple[bool, List[str]]:
    """Validate extracted fields"""
    errors = []
    
    if 'phone' in fields:
        phone = fields['phone']
        if not phone.startswith('+'):
            errors.append("Phone must include country code")
        elif len(re.sub(r'\D', '', phone)) < 10:
            errors.append("Phone number must be at least 10 digits")
    
    if 'email' in fields:
        email = fields['email']
        email_pattern = VALIDATION_PATTERNS.get('email')
        if email_pattern and not re.match(email_pattern, email):
            errors.append("Invalid email format")
    
    if 'name' in fields:
        name = fields['name']
        if len(name) < 2:
            errors.append("Name too short")
    
    if 'pincode' in fields:
        pincode = fields['pincode']
        if not pincode.isdigit():
            errors.append("Pincode must be numeric")
        elif not 4 <= len(pincode) <= 6:
            errors.append("Pincode must be 4-6 digits")
    
    return (len(errors) == 0, errors)