"""
Address Extractor - Robust address extraction logic
"""

import re
from typing import Optional, Dict, Any, List
from .base_extractor import BaseExtractor


class AddressExtractor(BaseExtractor):
    """Extract addresses from messages with battle-tested logic"""
    
    # Address indicators/keywords
    ADDRESS_INDICATORS = [
        'street', 'st.', 'st', 'road', 'rd.', 'rd', 'lane', 'ln.', 'ln',
        'avenue', 'ave.', 'ave', 'boulevard', 'blvd.', 'blvd',
        'drive', 'dr.', 'dr', 'circle', 'cir.', 'court', 'ct.',
        'house', 'flat', 'apartment', 'apt.', 'apt', 'building', 'bldg.',
        'floor', 'fl.', 'room', 'rm.', 'suite', 'ste.', 'unit', 'block', 'blk.',
        'colony', 'sector', 'area', 'locality', 'village', 'town', 'city',
        'district', 'state', 'county', 'province', 'region', 'zone',
        'near', 'beside', 'opposite', 'behind', 'in front of', 'at', 'by',
        'no.', 'number', '#', 'plot', 'ward', 'mohalla', 'chowk', 'nagar',
        'marg', 'path', 'gali', 'cross', 'layout', 'phase', 'extension',
        'vihar', 'puram', 'niwas', 'kunj', 'enclave', 'residency'
    ]
    
    # Location/city names (comprehensive)
    LOCATION_NAMES = [
        # India - Major cities
        'mumbai', 'delhi', 'bangalore', 'bengaluru', 'hyderabad', 'ahmedabad',
        'chennai', 'kolkata', 'surat', 'pune', 'jaipur', 'lucknow', 'kanpur',
        'nagpur', 'indore', 'thane', 'bhopal', 'visakhapatnam', 'pimpri',
        'patna', 'vadodara', 'ghaziabad', 'ludhiana', 'agra', 'nashik',
        'faridabad', 'meerut', 'rajkot', 'kalyan', 'vasai', 'varanasi',
        'srinagar', 'aurangabad', 'dhanbad', 'amritsar', 'navi mumbai',
        'allahabad', 'ranchi', 'howrah', 'coimbatore', 'jabalpur', 'gwalior',
        'vijayawada', 'jodhpur', 'madurai', 'raipur', 'kota', 'chandigarh',
        
        # India - States
        'maharashtra', 'karnataka', 'tamil nadu', 'uttar pradesh', 'up',
        'gujarat', 'rajasthan', 'punjab', 'haryana', 'kerala', 'bihar',
        'west bengal', 'madhya pradesh', 'mp', 'andhra pradesh', 'ap',
        'telangana', 'odisha', 'jharkhand', 'chhattisgarh',
        
        # Nepal
        'kathmandu', 'pokhara', 'lalitpur', 'bhaktapur', 'biratnagar',
        'birgunj', 'dharan', 'bharatpur', 'hetauda', 'janakpur',
        
        # Pakistan
        'karachi', 'lahore', 'islamabad', 'rawalpindi', 'faisalabad',
        'multan', 'peshawar', 'quetta', 'sialkot', 'gujranwala',
        
        # Bangladesh
        'dhaka', 'chittagong', 'khulna', 'rajshahi', 'sylhet',
        'barisal', 'rangpur', 'comilla', 'narayanganj',
        
        # Dubai/UAE
        'dubai', 'abu dhabi', 'sharjah', 'ajman', 'fujairah', 'ras al khaimah',
        'umm al quwain', 'al ain'
    ]
    
    # Words that are NOT addresses
    EXCLUDED_PATTERNS = [
        r'\S+@\S+\.\S+',  # Email
        r'\+\d[\d\s\-\(\)]+',  # Phone with +
        r'\b\d{10,}\b',  # Long numbers (likely phone)
        r'\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',  # Dates
        r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}',  # Dates
    ]
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract address from message"""
        original_message = message
        message = self.clean_message(message)
        
        # Check if message contains address indicators
        if not self._find_address_indicators(message):
            # Try location-based extraction
            location_address = self._extract_location_based(message)
            if location_address:
                return {
                    'address': location_address,
                    'confidence': 'medium',
                    'method': 'location_based'
                }
            return None
        
        # Clean the message by removing non-address elements
        cleaned = self._clean_for_extraction(message)
        
        # Extract location parts
        location_parts = self._extract_location_parts(cleaned)
        
        # Build address from parts
        if location_parts:
            address = self._build_address(location_parts, cleaned)
            if address and self._validate_address(address):
                return {
                    'address': self._clean_address(address),
                    'confidence': 'high',
                    'method': 'structured',
                    'parts': location_parts
                }
        
        # Fallback: extract based on patterns
        pattern_address = self._extract_pattern_based(cleaned)
        if pattern_address and self._validate_address(pattern_address):
            return {
                'address': self._clean_address(pattern_address),
                'confidence': 'medium',
                'method': 'pattern'
            }
        
        return None
    
    def _find_address_indicators(self, message: str) -> bool:
        """Check if message contains address indicators"""
        msg_lower = message.lower()
        
        # Check for address keywords
        for indicator in self.ADDRESS_INDICATORS:
            if indicator in msg_lower:
                return True
        
        # Check for location names
        for location in self.LOCATION_NAMES:
            if location in msg_lower:
                return True
        
        # Check for address-like patterns (number + text)
        if re.search(r'\b\d+[,\s]+[A-Za-z]', message):
            return True
        
        return False
    
    def _clean_for_extraction(self, message: str) -> str:
        """Clean message for address extraction"""
        cleaned = message
        
        # Remove excluded patterns
        for pattern in self.EXCLUDED_PATTERNS:
            cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
        
        # Remove common name patterns (Title Case at start)
        name_pattern = r'^([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]*'
        cleaned = re.sub(name_pattern, ' ', cleaned)
        
        # Remove standalone numbers that look like PIN codes
        cleaned = re.sub(r'\b\d{5,6}\b', ' ', cleaned)
        
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _extract_location_parts(self, message: str) -> Dict[str, str]:
        """Extract location components (street, city, etc.)"""
        parts = {}
        msg_lower = message.lower()
        
        # Extract street/house number
        street_pattern = r'(?:no\.?\s*)?(\d+[a-z]?)\s+([A-Za-z\s]+(?:street|st|road|rd|lane|ln|avenue|ave))'
        street_match = re.search(street_pattern, message, re.IGNORECASE)
        if street_match:
            parts['street'] = f"{street_match.group(1)} {street_match.group(2).strip()}"
        
        # Extract area/locality
        area_pattern = r'(?:area|locality|colony|sector|zone|ward|mohalla|nagar)\s*[:\-]?\s*([A-Za-z0-9\s]+)'
        area_match = re.search(area_pattern, message, re.IGNORECASE)
        if area_match:
            parts['area'] = area_match.group(1).strip()
        
        # Extract city
        for city in self.LOCATION_NAMES:
            if city in msg_lower:
                # Find the actual case-preserved version
                city_pattern = re.compile(re.escape(city), re.IGNORECASE)
                city_match = city_pattern.search(message)
                if city_match:
                    parts['city'] = city_match.group(0)
                    break
        
        # Extract state/country (if mentioned after city)
        if 'city' in parts:
            city_pos = msg_lower.index(parts['city'].lower())
            after_city = message[city_pos + len(parts['city']):].strip()
            
            # Look for state/country names
            state_pattern = r'^[,\s]+([A-Za-z\s]+?)(?:[,\.\s]|$)'
            state_match = re.search(state_pattern, after_city)
            if state_match:
                potential_state = state_match.group(1).strip()
                if len(potential_state.split()) <= 3:  # Max 3 words for state
                    parts['state'] = potential_state
        
        return parts
    
    def _build_address(self, parts: Dict[str, str], full_message: str) -> str:
        """Build address from extracted parts"""
        address_components = []
        
        # Add components in order: street, area, city, state
        if 'street' in parts:
            address_components.append(parts['street'])
        
        if 'area' in parts:
            address_components.append(parts['area'])
        
        if 'city' in parts:
            address_components.append(parts['city'])
        
        if 'state' in parts:
            address_components.append(parts['state'])
        
        # If we have very few components, try to extract more from full message
        if len(address_components) < 2:
            # Look for comma-separated components
            comma_parts = [p.strip() for p in full_message.split(',') if len(p.strip()) > 3]
            
            # Filter out parts that look like names or other info
            valid_parts = []
            for part in comma_parts[:5]:  # Max 5 parts
                if not re.search(r'@|^\d{10}$|\+\d', part):  # Not email/phone
                    valid_parts.append(part)
            
            if len(valid_parts) > len(address_components):
                address_components = valid_parts
        
        return ', '.join(address_components) if address_components else ''
    
    def _extract_pattern_based(self, message: str) -> Optional[str]:
        """Extract address using pattern matching"""
        # Pattern: Multiple components separated by commas
        comma_separated = [p.strip() for p in message.split(',')]
        
        if len(comma_separated) >= 2:
            # Filter valid components
            valid_components = []
            for component in comma_separated[:6]:  # Max 6 components
                # Skip if too short or looks like other data
                if len(component) < 3:
                    continue
                if re.search(r'^\d{10}$|@\w+\.\w+', component):
                    continue
                valid_components.append(component)
            
            if len(valid_components) >= 2:
                return ', '.join(valid_components)
        
        # Pattern: Long text with location indicators
        if len(message) > 20 and any(ind in message.lower() for ind in self.ADDRESS_INDICATORS[:20]):
            # Extract everything as address
            return message
        
        return None
    
    def _extract_location_based(self, message: str) -> Optional[str]:
        """Extract address when location names are present"""
        msg_lower = message.lower()
        
        # Check for city names
        found_location = None
        for location in self.LOCATION_NAMES:
            if location in msg_lower:
                found_location = location
                break
        
        if not found_location:
            return None
        
        # Extract text around the location
        location_pos = msg_lower.index(found_location)
        
        # Get context before and after
        before = message[:location_pos].strip()
        after = message[location_pos + len(found_location):].strip()
        
        # Build address from context
        address_parts = []
        
        # Add before context if it looks like address
        if before and len(before) > 5 and not re.search(r'@|\d{10}', before):
            # Take last part before location (likely street/area)
            before_parts = before.split(',')
            if before_parts:
                address_parts.append(before_parts[-1].strip())
        
        # Add location
        address_parts.append(found_location.title())
        
        # Add after context if it looks like state/country
        if after:
            after_clean = re.sub(r'[,\.]', '', after).strip()
            after_words = after_clean.split()
            if len(after_words) <= 3 and not re.search(r'\d{5,}|@', after_clean):
                address_parts.append(after_words[0].title())
        
        if len(address_parts) >= 2:
            return ', '.join(address_parts)
        
        return None
    
    def _clean_address(self, address: str) -> str:
        """Clean and format address"""
        # Remove extra spaces
        address = re.sub(r'\s+', ' ', address).strip()
        
        # Remove trailing punctuation
        address = re.sub(r'[,\s\.]+$', '', address)
        
        # Remove leading punctuation
        address = re.sub(r'^[,\s\.]+', '', address)
        
        # Capitalize properly
        parts = address.split(',')
        formatted_parts = []
        for part in parts:
            part = part.strip()
            if part:
                # Capitalize first letter of each word (title case)
                formatted_parts.append(part.title())
        
        return ', '.join(formatted_parts)
    
    def _validate_address(self, address: str) -> bool:
        """Validate if string is likely an address - RELAXED for city names"""
        if not address or len(address) < 3:  # Reduced from 10 to 3
            return False
        
        addr_lower = address.lower()
        
        # ========================
        # EXCLUDE DATE PATTERNS
        # ========================
        # Month names (English)
        months = [
            'january', 'february', 'march', 'april', 'may', 'june',
            'july', 'august', 'september', 'october', 'november', 'december',
            'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'
        ]
        
        # Common date patterns
        date_patterns = [
            r'\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}',
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',
            r'\d{1,2}\s+\d{4}'  # "15 2025"
        ]
        
        # Check for date patterns
        for month in months:
            if month in addr_lower:
                # Check if it's a date format
                for pattern in date_patterns:
                    if re.search(pattern, addr_lower):
                        return False
        
        # Check for question patterns
        question_starters = [
            "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
            "can you", "could you", "would you", "will you",
            "tell me", "show me", "give me", "explain this",
            "i want to know", "i would like to know",
            "do you have", "do you offer", "do you provide",
        ]
        
        for starter in question_starters:
            if addr_lower.startswith(starter):
                return False
        
        # Check for social media patterns
        social_patterns = [
            'instagram', 'facebook', 'twitter', 'youtube', 'linkedin',
            'social media', 'follow', 'subscribe', 'channel',
            'link', 'website', 'web', 'site', 'online'
        ]
        
        for pattern in social_patterns:
            if pattern in addr_lower:
                return False
        
        # ========================
        # NEW: Special handling for city names
        # ========================
        # Check if it's a known city
        is_city = any(location in addr_lower for location in self.LOCATION_NAMES)
        
        if is_city:
            # For city names only, be more lenient
            # Check it's not just part of a longer invalid string
            words = address.split()
            if len(words) == 1:
                # Single word that's a city - accept it
                return True
            elif len(words) <= 3:
                # Short address (like "Delhi", "New Delhi", "South Delhi")
                # Check if it doesn't contain other invalid patterns
                invalid_patterns = [
                    r'\d{10}',  # Phone number
                    r'\S+@\S+\.\S+',  # Email
                    r'price|cost|how much|fee',  # Price keywords
                ]
                for pattern in invalid_patterns:
                    if re.search(pattern, addr_lower):
                        return False
                return True
        
        # ========================
        # For non-city addresses, apply stricter rules
        # ========================
        parts = [p.strip() for p in address.split(',')]
        
        # Check for address indicators
        has_indicator = False
        for indicator in self.ADDRESS_INDICATORS[:30]:
            if indicator in addr_lower:
                has_indicator = True
                break
        
        if not has_indicator:
            # Check for location names (already done above)
            if not is_city:
                return False
        
        # Check for reasonable length and content
        words = address.split()
        if len(words) < 1:  # Reduced from 3
            return False
        
        # Check for number + street pattern
        if not is_city and not has_indicator:
            if re.search(r'\d+[,\s]+\w+', address):
                has_indicator = True
            else:
                return False
        
        return True