# agent/extractors/address_extractor_llm.py
"""
LLM-enhanced Address Extractor - Uses LLM for better address extraction
"""

import re
import json
from typing import Optional, Dict, Any, List
from .base_extractor import BaseExtractor


class LLMAddressExtractor(BaseExtractor):
    """Uses LLM to extract addresses more accurately"""
    
    def __init__(self, llm_service=None):
        self.llm_service = llm_service
        super().__init__()
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract address using LLM if available, otherwise fallback to rule-based"""
        # First clean the message
        cleaned = self._clean_message(message)
        
        # Try LLM extraction if available
        if self.llm_service:
            llm_result = self._extract_with_llm(cleaned, context)
            if llm_result:
                return llm_result
        
        # Fallback to rule-based extraction
        return self._extract_rule_based(cleaned, context)
    
    def _extract_with_llm(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """Extract address using LLM"""
        try:
            # Build prompt for LLM
            prompt = self._build_llm_prompt(message, context)
            
            # Call LLM (this is a placeholder - implement based on your LLM service)
            llm_response = self.llm_service.extract_address(prompt)
            
            if llm_response and 'address' in llm_response:
                return {
                    'address': llm_response['address'],
                    'confidence': 'high',
                    'method': 'llm',
                    'components': llm_response.get('components', {})
                }
        
        except Exception as e:
            print(f"LLM extraction failed: {e}")
        
        return None
    
    def _build_llm_prompt(self, message: str, context: Optional[Dict] = None) -> str:
        """Build prompt for LLM address extraction"""
        prompt = f"""
        Extract the complete address from the following message. 
        Return ONLY a JSON object with this structure:
        {{
          "address": "full address string",
          "components": {{
            "street": "street address",
            "city": "city",
            "state": "state/province",
            "country": "country",
            "pincode": "postal code (if available)"
          }},
          "confidence": "high/medium/low"
        }}
        
        Message: "{message}"
        
        Additional context: {json.dumps(context or {})}
        
        Important rules:
        1. DO NOT include any other text in response
        2. If no address found, return null
        3. If uncertain, set confidence to "low"
        4. Preserve original formatting as much as possible
        """
        
        return prompt
    
    def _extract_rule_based(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """Rule-based address extraction as fallback"""
        # Your existing rule-based logic here
        # This would be similar to your current AddressExtractor
        
        # Simplified version:
        address_indicators = ['street', 'road', 'avenue', 'lane', 'city', 'town', 'state', 'country']
        
        msg_lower = message.lower()
        
        # Check if message contains address indicators
        has_indicators = any(indicator in msg_lower for indicator in address_indicators)
        
        if not has_indicators:
            return None
        
        # Extract potential address parts
        # This is simplified - you should use your full rule-based logic
        parts = message.split(',')
        if len(parts) >= 2:
            # Join with commas for address
            address = ', '.join([p.strip() for p in parts[:3]])
            
            return {
                'address': address,
                'confidence': 'medium',
                'method': 'rule_based'
            }
        
        return None