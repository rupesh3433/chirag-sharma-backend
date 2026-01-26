"""
Country Extractor - Robust country detection logic
FIXED: Added "jhapa" to Nepal cities list
"""

import re
from typing import Optional, Dict, Any, List
from .base_extractor import BaseExtractor


class CountryExtractor(BaseExtractor):
    """Extract country information from messages with battle-tested logic"""
    
    # Supported countries with comprehensive patterns
    COUNTRY_PATTERNS = {
        'India': {
            'keywords': ['india', 'indian', 'भारत', 'भारतीय', 'hindustan'],
            'cities': [
                'mumbai', 'delhi', 'bangalore', 'bengaluru', 'hyderabad',
                'ahmedabad', 'chennai', 'kolkata', 'surat', 'pune', 'jaipur',
                'lucknow', 'kanpur', 'nagpur', 'indore', 'thane', 'bhopal',
                'visakhapatnam', 'pimpri', 'patna', 'vadodara', 'ghaziabad',
                'ludhiana', 'agra', 'nashik', 'faridabad', 'meerut', 'rajkot',
                'kalyan', 'vasai', 'varanasi', 'srinagar', 'aurangabad',
                'dhanbad', 'amritsar', 'navi mumbai', 'allahabad', 'prayagraj',
                'ranchi', 'howrah', 'coimbatore', 'jabalpur', 'gwalior',
                'vijayawada', 'jodhpur', 'madurai', 'raipur', 'kota',
                'chandigarh', 'guwahati', 'solapur', 'hubli', 'mysore',
                'tiruchirappalli', 'bareilly', 'aligarh', 'tiruppur', 'moradabad'
            ],
            'states': [
                'maharashtra', 'karnataka', 'tamil nadu', 'uttar pradesh',
                'gujarat', 'rajasthan', 'punjab', 'haryana', 'kerala', 'bihar',
                'west bengal', 'madhya pradesh', 'mp', 'andhra pradesh', 'ap',
                'telangana', 'odisha', 'jharkhand', 'chhattisgarh', 'assam',
                'uttarakhand', 'himachal pradesh', 'hp', 'goa', 'jammu',
                'kashmir', 'ladakh', 'manipur', 'meghalaya', 'mizoram',
                'nagaland', 'sikkim', 'tripura', 'arunachal pradesh'
            ],
            'phone_codes': ['91'],
            'pincode_length': 6
        },
        'Nepal': {
            'keywords': ['nepal', 'nepali', 'nepalese', 'नेपाल', 'नेपाली'],
            'cities': [
                'kathmandu', 'pokhara', 'lalitpur', 'patan', 'bhaktapur',
                'biratnagar', 'birgunj', 'dharan', 'bharatpur', 'hetauda',
                'janakpur', 'butwal', 'dhangadhi', 'nepalgunj', 'itahari',
                'kalaiya', 'bhimdatta', 'gulariya', 'tulsipur', 'rajbiraj',
                'jhapa'  # ✅ ADDED JHAPA HERE - CRITICAL FIX
            ],
            'states': [
                'bagmati', 'gandaki', 'lumbini', 'karnali', 'sudurpashchim',
                'province 1', 'madhesh', 'koshi'
            ],
            'phone_codes': ['977'],
            'pincode_length': 5
        },
        'Pakistan': {
            'keywords': ['pakistan', 'pakistani', 'پاکستان'],
            'cities': [
                'karachi', 'lahore', 'islamabad', 'rawalpindi', 'faisalabad',
                'multan', 'peshawar', 'quetta', 'sialkot', 'gujranwala',
                'hyderabad', 'bahawalpur', 'sargodha', 'sukkur', 'larkana',
                'sheikhupura', 'jhang', 'rahim yar khan', 'gujrat', 'mardan',
                'kasur', 'mingora', 'dera ghazi khan', 'sahiwal', 'nawabshah',
                'okara', 'gilgit', 'chiniot', 'sadiqabad', 'burewala'
            ],
            'states': [
                'punjab', 'sindh', 'khyber pakhtunkhwa', 'kpk', 'balochistan',
                'gilgit-baltistan', 'azad kashmir', 'islamabad capital territory'
            ],
            'phone_codes': ['92'],
            'pincode_length': 5
        },
        'Bangladesh': {
            'keywords': ['bangladesh', 'bangladeshi', 'বাংলাদেশ'],
            'cities': [
                'dhaka', 'chittagong', 'khulna', 'rajshahi', 'sylhet',
                'barisal', 'rangpur', 'comilla', 'gazipur', 'narayanganj',
                'mymensingh', 'cox\'s bazar', 'bogra', 'jessore', 'dinajpur',
                'tangail', 'kushtia', 'pabna', 'jamalpur', 'brahmanbaria'
            ],
            'states': [
                'dhaka division', 'chittagong division', 'khulna division',
                'rajshahi division', 'sylhet division', 'barisal division',
                'rangpur division', 'mymensingh division'
            ],
            'phone_codes': ['880'],
            'pincode_length': 4
        },
        'Dubai': {
            'keywords': ['dubai', 'uae', 'united arab emirates', 'emirates', 'دبي'],
            'cities': [
                'dubai', 'abu dhabi', 'sharjah', 'ajman', 'fujairah',
                'ras al khaimah', 'umm al quwain', 'al ain', 'khor fakkan',
                'dibba', 'jebel ali', 'deira', 'bur dubai', 'jumeirah'
            ],
            'states': [
                'dubai', 'abu dhabi', 'sharjah', 'ajman', 'fujairah',
                'ras al khaimah', 'umm al quwain'
            ],
            'phone_codes': ['971'],
            'pincode_length': 5
        }
    }
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract country from message"""
        message = self.clean_message(message).lower()
        
        # Try direct country mention first
        country = self._extract_direct_mention(message)
        if country:
            return {
                'country': country,
                'confidence': 'high',
                'method': 'direct_mention'
            }
        
        # Try to infer from cities/locations
        country = self._infer_from_locations(message)
        if country:
            return {
                'country': country,
                'confidence': 'high',
                'method': 'location_based'
            }
        
        # Try to infer from context
        if context:
            # From phone number
            phone = context.get('phone')
            if phone:
                country = self.infer_from_phone(phone)
                if country:
                    return {
                        'country': country,
                        'confidence': 'high',
                        'method': 'phone_based'
                    }
            
            # From address/pincode
            address = context.get('address')
            pincode = context.get('pincode')
            if address or pincode:
                country = self.infer_from_location(address, pincode)
                if country:
                    return {
                        'country': country,
                        'confidence': 'medium',
                        'method': 'address_based'
                    }
        
        return None
    
    def _extract_direct_mention(self, message: str) -> Optional[str]:
        """Extract country from direct mention"""
        msg_lower = message.lower()
        
        # Check each country's keywords
        for country, patterns in self.COUNTRY_PATTERNS.items():
            for keyword in patterns['keywords']:
                if keyword in msg_lower:
                    return country
        
        return None
    
    def _infer_from_locations(self, message: str) -> Optional[str]:
        """Infer country from city/state names"""
        msg_lower = message.lower()
        
        # Score for each country based on location matches
        country_scores = {country: 0 for country in self.COUNTRY_PATTERNS.keys()}
        
        for country, patterns in self.COUNTRY_PATTERNS.items():
            # Check cities
            for city in patterns['cities']:
                if city in msg_lower:
                    country_scores[country] += 2  # Cities get higher weight
            
            # Check states
            for state in patterns['states']:
                if state in msg_lower:
                    country_scores[country] += 1
        
        # Return country with highest score
        max_score = max(country_scores.values())
        if max_score > 0:
            for country, score in country_scores.items():
                if score == max_score:
                    return country
        
        return None
    
    def infer_from_location(self, address: Optional[str], pincode: Optional[str]) -> Optional[str]:
        """Infer country from address and pincode"""
        # First try pincode
        if pincode:
            country = self._infer_from_pincode(pincode)
            if country:
                return country
        
        # Then try address
        if address:
            country = self._infer_from_locations(address.lower())
            if country:
                return country
        
        return None
    
    def infer_from_phone(self, phone) -> Optional[str]:
        """
        Infer country from phone number
        Handles both dict and string phone objects
        """
        if not phone:
            return None
        
        # Extract phone string from dict if needed
        phone_str = phone
        if isinstance(phone, dict):
            # Try different keys to get the phone string
            phone_str = (phone.get('full_phone') or 
                        phone.get('phone') or 
                        phone.get('formatted') or 
                        str(phone))
        
        # Ensure it's a string
        if not isinstance(phone_str, str):
            phone_str = str(phone_str)
        
        # Clean phone number - remove all non-digit and non-plus characters
        phone_clean = re.sub(r'[^\d+]', '', phone_str)
        
        if not phone_clean:
            return None
        
        # Extract country code and match
        if phone_clean.startswith('+'):
            # Try to match country codes
            for country, patterns in self.COUNTRY_PATTERNS.items():
                for code in patterns['phone_codes']:
                    if phone_clean.startswith(f'+{code}'):
                        return country
        else:
            # Try without + prefix
            for country, patterns in self.COUNTRY_PATTERNS.items():
                for code in patterns['phone_codes']:
                    if phone_clean.startswith(code):
                        return country
        
        return None
    
    def _infer_from_pincode(self, pincode: str) -> Optional[str]:
        """Infer country from pincode pattern"""
        if not pincode:
            return None
        
        # Ensure pincode is string
        pincode_str = str(pincode) if not isinstance(pincode, str) else pincode
        
        length = len(pincode_str)
        
        if length == 6:
            # Could be India
            if pincode_str[0] in '12345678':
                return 'India'
        elif length == 5:
            # Could be Nepal, Pakistan, or Dubai
            # Need additional context to determine
            # For now, default to most common (India uses 6, so Nepal is next)
            return 'Nepal'
        elif length == 4:
            # Bangladesh
            return 'Bangladesh'
        
        return None
    
    def _get_country_patterns(self) -> Dict[str, list]:
        """Get country detection patterns"""
        patterns = {}
        
        for country, data in self.COUNTRY_PATTERNS.items():
            country_patterns = []
            
            # Add keyword patterns
            country_patterns.extend(data['keywords'])
            
            # Add city patterns (top 10 cities)
            country_patterns.extend(data['cities'][:10])
            
            # Add state patterns (top 5 states)
            country_patterns.extend(data['states'][:5])
            
            patterns[country] = country_patterns
        
        return patterns
    
    def get_supported_countries(self) -> List[str]:
        """Get list of supported countries"""
        return list(self.COUNTRY_PATTERNS.keys())
    
    def get_country_info(self, country: str) -> Optional[Dict]:
        """Get information about a specific country"""
        if country in self.COUNTRY_PATTERNS:
            info = self.COUNTRY_PATTERNS[country].copy()
            return {
                'country': country,
                'phone_codes': info['phone_codes'],
                'pincode_length': info['pincode_length'],
                'major_cities': info['cities'][:10],
                'states': info['states'][:5]
            }
        return None
    
    def validate_country_context(self, country: str, phone: Optional[str] = None, 
                                 pincode: Optional[str] = None, address: Optional[str] = None) -> Dict:
        """Validate if country matches with other context (phone, pincode, address)"""
        if country not in self.COUNTRY_PATTERNS:
            return {
                'valid': False,
                'error': 'Unsupported country'
            }
        
        country_info = self.COUNTRY_PATTERNS[country]
        conflicts = []
        
        # Validate phone
        if phone:
            inferred_from_phone = self.infer_from_phone(phone)
            if inferred_from_phone and inferred_from_phone != country:
                conflicts.append(f"Phone number suggests {inferred_from_phone}")
        
        # Validate pincode
        if pincode:
            pincode_str = str(pincode) if not isinstance(pincode, str) else pincode
            if len(pincode_str) != country_info['pincode_length']:
                conflicts.append(f"Pincode length should be {country_info['pincode_length']}")
        
        # Validate address
        if address:
            inferred_from_address = self._infer_from_locations(address.lower())
            if inferred_from_address and inferred_from_address != country:
                conflicts.append(f"Address suggests {inferred_from_address}")
        
        if conflicts:
            return {
                'valid': False,
                'conflicts': conflicts,
                'confidence': 'low'
            }
        
        return {
            'valid': True,
            'confidence': 'high'
        }