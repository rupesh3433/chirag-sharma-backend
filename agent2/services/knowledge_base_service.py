# agent/services/knowledge_base_service.py
"""
Enhanced Knowledge Base Service - Always uses LLM for intelligent responses
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
    validate_language
)

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """LLM-powered knowledge base for all intelligent responses"""
    
    def __init__(self):
        self.api_key = GROQ_CONFIG.get("api_key")
        self.model = GROQ_CONFIG.get("model", "llama-3.1-8b-instant")
        self.api_url = GROQ_CONFIG.get("api_url")
        self.enabled = GROQ_CONFIG.get("enabled", True)  # Always enabled
        
        # Cache for responses
        self.cache_ttl = AGENT_SETTINGS.get("kb_cache_ttl_minutes", 30)
        self.cache = TTLCache(maxsize=1000, ttl=self.cache_ttl * 60)
        
        logger.info(f"✅ KnowledgeBaseService initialized (LLM: {self.enabled})")
    
    def _get_cache_key(self, query: str, language: str, context: str = "") -> str:
        """Generate cache key"""
        return f"{language}:{context}:{query[:100]}"
    
    def _build_system_prompt(self, language: str, state: str, booking_info: Dict) -> str:
        """Build system prompt for LLM"""
        # Get booking context
        context_parts = []
        if booking_info:
            if booking_info.get('service'):
                context_parts.append(f"Service: {booking_info['service']}")
            if booking_info.get('package'):
                context_parts.append(f"Package: {booking_info['package']}")
            if booking_info.get('missing_fields'):
                context_parts.append(f"Missing: {', '.join(booking_info['missing_fields'])}")
        
        context = " | ".join(context_parts) if context_parts else "New conversation"
        
        # Language-specific instructions
        language_instructions = {
            "en": "Respond in English. Be helpful, brief, and professional.",
            "hi": "हिंदी में जवाब दें। सहायक, संक्षिप्त और पेशेवर रहें।",
            "ne": "नेपालीमा जवाब दिनुहोस्। सहायक, संक्षिप्त र पेशेवर रहनुहोस्।",
            "mr": "मराठीत उत्तर द्या. मदतगार, थोडक्यात आणि व्यावसायिक रहा."
        }
        
        lang_instruction = language_instructions.get(language, language_instructions["en"])
        
        prompt = f"""You are Chirag Sharma's booking assistant. 

Context: User is {context}. Current state: {state}.

Instructions:
1. {lang_instruction}
2. Answer questions helpfully but briefly
3. If user asks about services or pricing, provide accurate information
4. If user asks about social media, provide appropriate links
5. Always guide user back to booking process gently

Available Services:
"""
        
        # Add services info
        for service_name, service_data in SERVICES.items():
            packages = service_data.get("packages", {})
            package_lines = [f"  - {name}: {price}" for name, price in packages.items()]
            prompt += f"\n{service_name}:"
            prompt += "\n" + "\n".join(package_lines)
        
        prompt += "\n\nRespond naturally and helpfully."
        
        return prompt
    
    async def get_answer(self, query: str, language: str, context: str = "") -> str:
        """Get answer from knowledge base (LLM)"""
        language = validate_language(language)
        
        # Check cache
        cache_key = self._get_cache_key(query, language, context)
        if cache_key in self.cache:
            logger.debug(f"Cache hit for: {query[:50]}")
            return self.cache[cache_key]
        
        # Always use LLM if enabled
        if self.enabled and self.api_key:
            try:
                response = await self._call_llm(query, language, context)
                if response:
                    self.cache[cache_key] = response
                    return response
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
        
        # Fallback responses
        fallbacks = {
            "en": "I'm here to help with makeup service bookings. How can I assist you?",
            "hi": "मैं मेकअप सेवा बुकिंग में मदद के लिए यहां हूं। मैं आपकी कैसे मदद कर सकता हूं?",
            "ne": "म मेकअप सेवा बुकिङमा मद्दत गर्न यहाँ छु। म तपाईंलाई कसरी मद्दत गर्न सक्छु?",
            "mr": "मी मेकअप सेवा बुकिंगमध्ये मदत करण्यासाठी येथे आहे. मी तुम्हाला कशी मदत करू शकतो?"
        }
        
        fallback = fallbacks.get(language, fallbacks["en"])
        self.cache[cache_key] = fallback
        return fallback
    
    async def answer_query(self, query: str, language: str = "en",
                          state: str = None, booking_info: Dict = None) -> Dict[str, Any]:
        """Answer query with context"""
        language = validate_language(language)
        
        # Get answer from LLM
        answer = await self.get_answer(query, language, str(booking_info or {}))
        
        return {
            "response": answer,
            "source": "llm",
            "language": language
        }
    
    async def _call_llm(self, query: str, language: str, context: str) -> Optional[str]:
        """Call LLM API"""
        try:
            system_prompt = self._build_system_prompt(language, "conversation", {})
            
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
                "max_tokens": 200,
                "temperature": 0.3,
                "top_p": 0.9
            }
            
            timeout = AGENT_SETTINGS.get("kb_response_timeout", 15)
            
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
        unwanted = [
            "According to", "Based on", "As per", "The knowledge base states",
            "I understand", "Let me", "As an AI", "I'm an AI"
        ]
        
        for prefix in unwanted:
            if response.startswith(prefix):
                response = response[len(prefix):].strip()
        
        # Clean up
        response = response.strip()
        if response.endswith('.'):
            response = response[:-1]
        
        return response
    
    def clear_cache(self):
        """Clear cache"""
        self.cache.clear()
        logger.info("Knowledge base cache cleared")