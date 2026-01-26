"""
LLM-Powered Address Extractor - FIXED VALIDATION VERSION (Python 3.8 Compatible)
CRITICAL FIX: Accept ANY location names for booking context, not just known cities
"""

import logging
import json
import re
import os
import requests
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class LLMAddressExtractor:
    """Use Groq LLM to extract addresses with PROPER validation for booking context"""
    
    def __init__(self, api_key: str = None, model: str = "llama-3.1-8b-instant"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ No Groq API key provided")
        
        self.model = model
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        logger.info(f"🤖 Groq LLM Address Extractor initialized with model: {model}")
    
    def extract_address(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract address from message using Groq LLM with ENHANCED validation"""
        try:
            if not self.api_key:
                logger.error("❌ No Groq API key available")
                return None
            
            logger.info(f"🤖 Using Groq LLM ({self.model}) to extract address from: '{message[:100]}...'")
            
            context_str = ""
            if context:
                extracted_fields = []
                for field, value in context.items():
                    if field not in ['address', 'original_message', '_debug'] and value:
                        extracted_fields.append(f"{field}: {value}")
                
                if extracted_fields:
                    context_str = f"\n\nAlready extracted fields (DO NOT include): {', '.join(extracted_fields)}"
            
            system_prompt = """You are an address extraction specialist for a BOOKING SYSTEM.

CRITICAL RULES for BOOKING CONTEXT:
1. Extract ANY location name mentioned - villages, towns, cities, areas, districts
2. For booking, even "Lahalgardz, Mainali" is a valid address
3. Preserve the FULL location name as provided
4. DO NOT include: names, phone numbers, emails, dates, PIN codes
5. Remove numeric PIN/postal codes if attached to address
6. Look for location indicators: "at", "in", "address", "location", "place"

EXAMPLES TO EXTRACT (YES for booking):
- "Kathmandu, Nepal" → "Kathmandu, Nepal"
- "Delhi" → "Delhi"
- "lahalgardz, mainali" → "Lahalgardz, Mainali" (YES! for booking context)
- "harakpur, jamai" → "Harakpur, Jamai" (YES! for booking context)
- "baner road pune" → "Baner Road, Pune"
- "my village is kathmandu" → "Kathmandu"
- "i live in kailali" → "Kailali"

EXAMPLES TO REJECT (NO):
- "Ramesh Kumar" (name)
- "ramesh@email.com" (email)
- "+919876543210" (phone)
- "April 15, 2025" (date)
- "110001" (pincode only)

Return JSON:
{
  "found": true,
  "address": "extracted address",
  "confidence": "high"
}

OR if no address:
{
  "found": false
}"""
            
            user_prompt = f"""Text: "{message}"{context_str}

Extract ONLY the location/address if present.

CRITICAL FOR BOOKING:
✅ Accept ANY location name (village, town, city, area)
✅ Keep the FULL name as provided
✅ Capitalize properly

Example responses:
- Input: "lahalgardz, mainali" → "Lahalgardz, Mainali" (YES!)
- Input: "harakpur, jamai" → "Harakpur, Jamai" (YES!)
- Input: "kathmandu nepal" → "Kathmandu, Nepal" (YES!)

JSON OUTPUT:"""
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.01,
                "max_tokens": 200,
                "response_format": {"type": "json_object"}
            }
            
            logger.info(f"🔍 [LLM DEBUG] Calling API with message: '{message[:150]}...'")
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Groq API error: {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            response_text = data["choices"][0]["message"]["content"]
            logger.info(f"🤖 LLM raw response: {response_text}")
            
            result = self._parse_llm_response(response_text)
            
            if result:
                if result.get('found'):
                    address = result.get('address', '').strip()
                    
                    # Clean up but preserve the location name
                    address = re.sub(r'\b\d{5,6}\b', '', address).strip()
                    address = re.sub(r'\s+', ' ', address)
                    
                    if len(address) >= 2 and not address.isdigit():
                        # CRITICAL FIX: Use the new VALIDATION that accepts ANY location name
                        validation_result, reason = self._validate_extracted_address(address, message)
                        
                        if validation_result:
                            logger.info(f"✅ LLM found address: {address}")
                            return {
                                'address': address,
                                'confidence': result.get('confidence', 'medium'),
                                'method': 'llm',
                                'found': True,
                                'model': self.model
                            }
                        else:
                            logger.warning(f"⚠️ LLM extracted but validation failed: '{address}' - {reason}")
                            # Even if validation fails, we might still use it for booking context
                            # Check if it looks like a location anyway
                            if self._is_plausible_location_for_booking(address, message):
                                logger.info(f"✅ Accepting as plausible location for booking: '{address}'")
                                return {
                                    'address': address,
                                    'confidence': 'low',
                                    'method': 'llm_with_fallback',
                                    'found': True,
                                    'model': self.model
                                }
                            return {
                                'found': False,
                                'reason': f'Failed validation: {reason}',
                                'method': 'llm'
                            }
                    else:
                        logger.warning(f"⚠️ LLM returned invalid address: '{address}'")
                        return {
                            'found': False,
                            'reason': 'Address invalid after cleanup',
                            'method': 'llm'
                        }
                else:
                    reason = result.get('reason', 'No address found')
                    logger.info(f"❌ LLM: No address found - {reason}")
                    return {
                        'found': False,
                        'reason': reason,
                        'method': 'llm'
                    }
            else:
                logger.error(f"❌ Failed to parse LLM response")
                return None
            
        except requests.exceptions.Timeout:
            logger.error(f"⏱️ Groq API timeout for model: {self.model}")
            return None
        except Exception as e:
            logger.error(f"❌ LLM address extraction error: {e}", exc_info=True)
            return None
    
    def _parse_llm_response(self, response_text: str) -> Optional[Dict]:
        """Parse LLM JSON response"""
        try:
            cleaned = response_text.strip()
            if cleaned.startswith('```'):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'```\s*$', '', cleaned)
            
            result = json.loads(cleaned.strip())
            return result
        
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse LLM JSON: {e}")
            
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except:
                    pass
            
            # Try to extract address directly
            match = re.search(r'"address":\s*"([^"]+)"', response_text)
            if match:
                return {
                    'found': True,
                    'address': match.group(1),
                    'confidence': 'medium'
                }
            
            # Check for address in text
            if 'address' in response_text.lower():
                lines = response_text.split('\n')
                for line in lines:
                    if 'address' in line.lower() and ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) > 1:
                            address = parts[1].strip().strip('"\'')
                            if address:
                                return {
                                    'found': True,
                                    'address': address,
                                    'confidence': 'low'
                                }
            
            return None
    
    def _validate_extracted_address(self, address: str, original_message: str) -> Tuple[bool, str]:
        """FIXED: Validate extracted address - ACCEPT ANY location name for booking context"""
        
        if len(address) < 2:
            return False, "Address too short"
        
        address_lower = address.lower().strip()
        
        # CRITICAL FIX: EXTENDED list of known locations across South Asia
        # This is now just for reference, not for strict validation
        known_locations = [
            # India - Major cities
            'delhi', 'mumbai', 'pune', 'bangalore', 'bengaluru', 'kolkata', 'chennai',
            'hyderabad', 'ahmedabad', 'surat', 'jaipur', 'lucknow', 'kanpur',
            'nagpur', 'indore', 'bhopal', 'visakhapatnam', 'patna', 'vadodara',
            
            # Nepal - Cities and districts
            'kathmandu', 'pokhara', 'lalitpur', 'patan', 'bharatpur', 'biratnagar',
            'birgunj', 'dharan', 'hetauda', 'janakpur', 'butwal', 'nepalgunj',
            'dhangadhi', 'tulsipur', 'kailali', 'kanchanpur', 'makwanpur',
            
            # Common location suffixes
            'nagar', 'colony', 'road', 'street', 'lane', 'avenue', 'society',
            'village', 'town', 'city', 'district', 'state', 'country'
        ]
        
        # Check for KNOWN non-address patterns (REJECT)
        non_address_patterns = [
            r'^\d{10}$',  # Phone number (10 digits)
            r'^\+\d{11,15}$',  # International phone
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',  # Email
            r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$',  # Date
            r'^\d{5,6}$',  # Pincode only
            r'^\d+$',  # Any number only
        ]
        
        for pattern in non_address_patterns:
            if re.match(pattern, address):
                logger.info(f"❌ [VALIDATION] Rejected - matches non-address pattern: {address}")
                return False, f"Matches non-address pattern: {pattern}"
        
        # Check for month names (likely date)
        month_patterns = [
            r'\bjanuary\b', r'\bfebruary\b', r'\bmarch\b', r'\bapril\b', r'\bmay\b',
            r'\bjune\b', r'\bjuly\b', r'\baugust\b', r'\bseptember\b', r'\boctober\b',
            r'\bnovember\b', r'\bdecember\b', r'\bjan\b', r'\bfeb\b', r'\bmar\b',
            r'\bapr\b', r'\bjun\b', r'\bjul\b', r'\baug\b', r'\bsep\b', r'\boct\b',
            r'\bnov\b', r'\bdec\b'
        ]
        
        for pattern in month_patterns:
            if re.search(pattern, address_lower):
                # But check if it's part of a location name (e.g., "March Town")
                if not any(loc in address_lower for loc in ['town', 'city', 'road', 'street', 'colony']):
                    logger.info(f"❌ [VALIDATION] Rejected - contains month name: {address}")
                    return False, "Contains month name (likely date)"
        
        # For booking context, be VERY LENIENT
        # Accept if it looks like a plausible location
        
        # 1. Check if it contains location indicators
        location_indicators = [
            'road', 'street', 'lane', 'avenue', 'boulevard', 'nagar', 'colony',
            'society', 'apartment', 'flat', 'house', 'building', 'sector', 'block',
            'phase', 'city', 'town', 'village', 'district', 'state', 'country',
            'marg', 'gali', 'chowk', 'bazar', 'market', 'cross', 'circle', 'pur',
            'garh', 'bad', 'nagar', 'ganj'
        ]
        
        has_location_word = any(indicator in address_lower for indicator in location_indicators)
        
        # 2. Check for comma (multi-part address)
        has_comma = ',' in address
        
        # 3. Check original message for address keywords
        original_lower = original_message.lower()
        has_address_keyword = any(keyword in original_lower for keyword in 
                                 ['address', 'at ', 'location', 'in ', 'place', 'city', 'town', 'village', 'area'])
        
        # 4. Check if mostly alphabetic
        alpha_chars = sum(c.isalpha() or c.isspace() or c in ',.-' for c in address)
        alpha_ratio = alpha_chars / len(address) if len(address) > 0 else 0
        
        # 5. Check if it's in known locations (bonus, not required)
        is_known_location = any(loc in address_lower for loc in known_locations)
        
        # ACCEPTANCE CRITERIA for booking context:
        # Accept if ANY of these are true:
        accept = (
            has_location_word or
            has_comma or
            has_address_keyword or
            is_known_location or
            (len(address.split()) >= 2) or  # Multiple words
            (',' in address and len(address) >= 5) or  # Comma-separated with length
            (alpha_ratio > 0.7 and len(address) >= 3)  # Mostly text, reasonable length
        )
        
        if accept:
            logger.info(f"✅ [VALIDATION] Accepted for booking: {address}")
            logger.info(f"   Has location word: {has_location_word}")
            logger.info(f"   Has comma: {has_comma}")
            logger.info(f"   Has address keyword: {has_address_keyword}")
            logger.info(f"   Is known location: {is_known_location}")
            logger.info(f"   Alpha ratio: {alpha_ratio:.2f}")
            logger.info(f"   Length: {len(address)}")
            return True, ""
        else:
            logger.info(f"❌ [VALIDATION] Rejected: {address}")
            return False, "Does not appear to be a valid location"
    
    def _is_plausible_location_for_booking(self, address: str, original_message: str) -> bool:
        """
        LAST RESORT: Check if this could be a location for booking context
        Very lenient - accepts almost anything that's not clearly wrong
        """
        address_lower = address.lower().strip()
        
        # REJECT if clearly wrong
        clear_reject_patterns = [
            r'^\d{10}$',  # Phone
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',  # Email
            r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$',  # Date
            r'^\d{5,6}$',  # Pincode
            r'^\d+$',  # Numbers only
        ]
        
        for pattern in clear_reject_patterns:
            if re.match(pattern, address):
                return False
        
        # Check if it contains common location suffixes
        location_suffixes = ['pur', 'garh', 'bad', 'nagar', 'ganj', 'village', 'town', 'city']
        has_suffix = any(address_lower.endswith(suffix) for suffix in location_suffixes)
        
        # Check if contains location words
        location_words = ['road', 'street', 'lane', 'colony', 'society']
        has_location_word = any(word in address_lower for word in location_words)
        
        # For booking, accept if:
        # 1. Not clearly wrong AND
        # 2. (Has location suffix OR has location word OR contains comma OR multiple words)
        if len(address) >= 3:
            conditions = [
                has_suffix,
                has_location_word,
                ',' in address,
                len(address.split()) >= 2,
                any(c.isupper() for c in address)  # Has capital letters
            ]
            
            if any(conditions):
                logger.info(f"✅ [FALLBACK VALIDATION] Accepting as plausible location for booking: {address}")
                return True
        
        return False


def extract_address_with_llm(message: str, context: Optional[Dict] = None,
                            api_key: str = None, model: str = "llama-3.1-8b-instant") -> Optional[Dict]:
    """Simple function to extract address using Groq LLM"""
    extractor = LLMAddressExtractor(api_key=api_key, model=model)
    return extractor.extract_address(message, context)