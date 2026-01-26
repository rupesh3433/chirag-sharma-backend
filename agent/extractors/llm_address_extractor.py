"""
LLM-Powered Address Extractor
Uses Groq API to intelligently extract addresses from messages
Simple and reliable version
"""

import logging
import json
import re
import os
import requests
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMAddressExtractor:
    """
    Use Groq LLM to extract addresses from complex messages
    Simple synchronous implementation like your KnowledgeBaseService
    """
    
    def __init__(self, api_key: str = None, model: str = "llama-3.1-8b-instant"):
        """
        Initialize Groq LLM extractor
        
        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model: Model to use (llama-3.1-8b-instant, mixtral-8x7b-32768, etc.)
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ No Groq API key provided. Set GROQ_API_KEY environment variable.")
        
        self.model = model
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        logger.info(f"🤖 Groq LLM Address Extractor initialized with model: {model}")
    
    def extract_address(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract address from message using Groq LLM"""
        try:
            if not self.api_key:
                logger.error("❌ No Groq API key available")
                return None
            
            logger.info(f"🤖 Using Groq LLM ({self.model}) to extract address from: '{message[:100]}...'")
            
            # Build context string
            context_str = ""
            if context:
                extracted_fields = []
                for field, value in context.items():
                    if field not in ['address', 'original_message'] and value:
                        extracted_fields.append(f"{field}: {value}")
                
                if extracted_fields:
                    context_str = f"\n\nAlready extracted fields (DO NOT include these in address): {', '.join(extracted_fields)}"
            
            # STRICT PROMPT - NO ASSUMPTIONS
            system_prompt = """You are an address extraction specialist. Your ONLY job is to extract physical addresses or locations from text.

    CRITICAL RULE: Only extract if there is an EXPLICIT address/location mentioned. If you're not sure, return found: false.

    STRICT RULES:
    1. Extract ONLY if there's a clear physical address/location/area/city
    2. DO NOT assume or guess locations
    3. DO NOT include: names, phone numbers, emails, dates, or PIN codes
    4. Remove any numeric PIN/postal codes from the address
    5. If there's NO explicit address keyword (like "address", "at", "location", "in", city name), return found: false

    Return EXACTLY this JSON format:

    {
    "found": true,
    "address": "extracted address here",
    "confidence": "high"
    }

    OR if no address found or unsure:

    {
    "found": false,
    "address": "",
    "confidence": "low"
    }"""
            
            user_prompt = f"""Text to analyze: "{message}"{context_str}

    TASK: Extract the physical address or location ONLY if EXPLICITLY mentioned.

    JSON OUTPUT TEMPLATE (copy this structure exactly):
    {{
    "found": true or false,
    "address": "the physical location/address",
    "confidence": "high" or "medium" or "low"
    }}

    CRITICAL REMINDERS:
    - Only return found: true if there's a CLEAR location indicator (address, at, location, in, city name)
    - If uncertain or no clear address → found: false
    - Remove PIN codes (5-6 digit numbers) from the address
    - Remove phone numbers, emails, names, dates
    - Keep only: area names, locality, city, landmark
    - Return ONLY valid JSON, no extra text
    - DO NOT GUESS OR ASSUME

    Now extract the address (or return found: false if no clear address):"""

            # Call Groq API
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
                "temperature": 0.05,  # Very low temperature - no creativity
                "max_tokens": 200,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Groq API error: {response.status_code} - {response.text}")
                return None
            
            # Extract response
            data = response.json()
            response_text = data["choices"][0]["message"]["content"]
            logger.info(f"🤖 LLM raw response: {response_text}")
            
            # Parse JSON response
            result = self._parse_llm_response(response_text)
            
            if result:
                if result.get('found'):
                    address = result.get('address', '').strip()
                    
                    # Additional cleanup: remove any remaining PIN codes
                    address = re.sub(r'\b\d{5,6}\b', '', address).strip()
                    address = re.sub(r'\s+', ' ', address)  # Clean multiple spaces
                    
                    # Validation: address must be at least 3 chars and not just numbers
                    if len(address) >= 3 and not address.isdigit():
                        logger.info(f"✅ LLM found address: {address}")
                        return {
                            'address': address,
                            'confidence': result.get('confidence', 'medium'),
                            'method': 'llm',
                            'found': True,
                            'model': self.model
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
            # Remove markdown code blocks if present
            cleaned = response_text.strip()
            if cleaned.startswith('```'):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'```\s*$', '', cleaned)
            
            # Parse JSON
            result = json.loads(cleaned.strip())
            return result
        
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse LLM JSON response: {e}")
            logger.error(f"Response was: {response_text}")
            
            # Try to extract JSON using regex
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except:
                    pass
            
            # Try to find address in quotes
            match = re.search(r'"address":\s*"([^"]+)"', response_text)
            if match:
                return {
                    'found': True,
                    'address': match.group(1),
                    'confidence': 'medium'
                }
            
            return None


# Simple synchronous function
def extract_address_with_llm(message: str, context: Optional[Dict] = None,
                            api_key: str = None, model: str = "llama-3.1-8b-instant") -> Optional[Dict]:
    """
    Simple function to extract address using Groq LLM
    
    Usage:
        result = extract_address_with_llm(message)
        if result and result.get('found'):
            address = result['address']
        else:
            print(result.get('reason', 'No address found'))
    """
    extractor = LLMAddressExtractor(api_key=api_key, model=model)
    return extractor.extract_address(message, context)


# Integration with your existing FieldExtractors
def integrate_with_field_extractor():
    """
    How to integrate with your existing FieldExtractors class
    
    In your FieldExtractors._extract_address_ultimate method:
    """
    pass


# Test the extractor
if __name__ == "__main__":
    # Test with sample messages
    test_messages = [
        "I want to book at Baner, Pune",
        "My address is 123 MG Road, Bangalore",
        "I live in Mumbai",
        "At Delhi for the booking",
        "Name is John, phone 9876543210, email john@test.com"
    ]
    
    extractor = LLMAddressExtractor()
    
    for msg in test_messages:
        print(f"\n📝 Message: {msg}")
        result = extractor.extract_address(msg)
        if result and result.get('found'):
            print(f"✅ Address: {result['address']} (Confidence: {result.get('confidence')})")
        else:
            print(f"❌ No address found: {result.get('reason', 'Unknown error') if result else 'No result'}")