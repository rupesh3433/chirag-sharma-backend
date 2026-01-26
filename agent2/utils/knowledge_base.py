"""
Knowledge Base Service for handling off-topic queries
"""

import logging
import re
from typing import Dict, List, Optional, Any
from datetime import datetime

import aiohttp
from cachetools import TTLCache

from ..config.config import (
    GROQ_CONFIG,
    AGENT_SETTINGS,
    SERVICES,
    get_service_keywords,
    validate_language,
    KB_UNWANTED_PREFIXES
)
from ..prompts.templates import (
    build_kb_system_prompt,
    build_service_info_response,
    build_pricing_overview
)

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """Knowledge base service for handling off-topic queries"""
    
    def __init__(self):
        self.api_key = GROQ_CONFIG.get("api_key")
        self.model = GROQ_CONFIG.get("model", "llama-3.1-8b-instant")
        self.api_url = GROQ_CONFIG.get("api_url")
        self.enabled = GROQ_CONFIG.get("enabled", False)
        
        # Cache for responses
        self.cache_ttl = AGENT_SETTINGS.get("kb_cache_ttl_minutes", 30)
        self.cache = TTLCache(maxsize=1000, ttl=self.cache_ttl * 60)
        
        logger.info(f"✅ KnowledgeBaseService initialized")
    
    def _get_cache_key(self, query: str, language: str) -> str:
        """Generate cache key"""
        return f"{language}:{query[:100]}"
    
    def _is_service_query(self, query: str) -> bool:
        """Check if query is about services"""
        query_lower = query.lower()
        
        # Check service keywords
        for service_name, service_data in SERVICES.items():
            keywords = get_service_keywords(service_name)
            if any(keyword in query_lower for keyword in keywords):
                return True
        
        # Check price keywords
        price_keywords = ['price', 'cost', 'how much', '₹', 'charge', 'fee']
        if any(keyword in query_lower for keyword in price_keywords):
            return True
        
        return False
    
    def _get_service_response(self, query: str, language: str) -> Optional[str]:
        """Get structured response for service queries"""
        query_lower = query.lower()
        
        # Check for specific service
        for service_name, service_data in SERVICES.items():
            keywords = get_service_keywords(service_name)
            if any(keyword in query_lower for keyword in keywords):
                return build_service_info_response(service_name, language)
        
        # Check for pricing
        if any(word in query_lower for word in ['price', 'cost', 'how much']):
            return build_pricing_overview(language)
        
        return None
    
    async def answer_query(self, query: str, language: str = "en",
                          state: str = None, booking_info: Dict = None) -> Dict[str, Any]:
        """
        Answer user query
        """
        language = validate_language(language)
        
        # Check cache
        cache_key = self._get_cache_key(query, language)
        if cache_key in self.cache:
            logger.debug(f"Cache hit for: {query[:50]}...")
            return self.cache[cache_key]
        
        # Check for service query first
        if self._is_service_query(query):
            response = self._get_service_response(query, language)
            if response:
                result = {
                    "response": response,
                    "is_service_related": True,
                    "source": "structured"
                }
                self.cache[cache_key] = result
                return result
        
        # Use LLM for other queries
        if self.enabled and self.api_key:
            response = await self._call_llm(query, language, state, booking_info)
            if response:
                result = {
                    "response": response,
                    "is_service_related": False,
                    "source": "llm"
                }
                self.cache[cache_key] = result
                return result
        
        # Fallback
        result = {
            "response": self._get_fallback_response(language),
            "is_service_related": False,
            "source": "fallback"
        }
        return result
    
    async def _call_llm(self, query: str, language: str, state: str, booking_info: Dict) -> Optional[str]:
        """Call LLM API"""
        try:
            system_prompt = build_kb_system_prompt(language, state, booking_info)
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                "max_tokens": 150,
                "temperature": 0.4
            }
            
            timeout = AGENT_SETTINGS.get("kb_response_timeout", 10)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        return self._clean_response(content)
                    else:
                        logger.error(f"LLM API error: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"LLM call failed: {str(e)}")
            return None
    
    def _clean_response(self, response: str) -> str:
        """Clean LLM response"""
        if not response:
            return response
        
        # Remove unwanted prefixes
        for prefix in KB_UNWANTED_PREFIXES:
            if response.lower().startswith(prefix.lower()):
                response = response[len(prefix):].strip()
        
        # Remove any "Answer:" type prefixes
        unwanted_starts = ["Answer:", "Response:", "Reply:", "A:"]
        for start in unwanted_starts:
            if response.startswith(start):
                response = response[len(start):].strip()
        
        return response.strip()
    
    def _get_fallback_response(self, language: str) -> str:
        """Get fallback response"""
        from ..config.config import PROMPT_TEMPLATES
        
        fallbacks = {
            "en": "I'm here to help with Chirag Sharma's makeup services. Would you like information about our services or to start a booking?",
            "hi": "मैं चिराग शर्मा की मेकअप सेवाओं में आपकी मदद करने के लिए यहां हूं। क्या आप हमारी सेवाओं के बारे में जानकारी चाहेंगे या बुकिंग शुरू करना चाहेंगे?",
            "ne": "म चिराग शर्माका मेकअप सेवाहरूमा तपाईंलाई मद्दत गर्न यहाँ छु। के तपाईं हाम्रो सेवाहरूको बारेमा जानकारी चाहनुहुन्छ वा बुकिङ सुरु गर्न चाहनुहुन्छ?",
            "mr": "मी चिराग शर्माच्या मेकअप सेवांमध्ये तुमची मदत करण्यासाठी येथे आहे. तुम्हाला आमच्या सेवांबद्दल माहिती हवी आहे की बुकिंग सुरू करायची आहे?"
        }
        
        return fallbacks.get(language, fallbacks["en"])
    
    def clear_cache(self):
        """Clear response cache"""
        self.cache.clear()
        logger.info("Knowledge base cache cleared")