# agent/services/knowledge_base_service.py
"""
Knowledge Base Service - Handles knowledge base queries with Groq LLM
"""

import logging
import os
from typing import Optional, Dict, Any
import requests
from config import GROQ_API_KEY

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """Service for querying knowledge base with Groq LLM"""
    
    def __init__(self, knowledge_collection=None):
        """Initialize knowledge base service"""
        self.knowledge_collection = knowledge_collection
        self.groq_api_key = GROQ_API_KEY
        
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not found in environment")
        
        logger.info("KnowledgeBaseService initialized")
    
    def load_knowledge_from_db(self, language: str) -> str:
        """Load knowledge base content from database for specific language"""
        try:
            if self.knowledge_collection is None:
                logger.warning("No knowledge collection configured")
                return ""
            
            # Get all active knowledge entries for the specified language
            knowledge_entries = list(self.knowledge_collection.find({
                "language": language,
                "is_active": True
            }).sort("created_at", -1))
            
            if not knowledge_entries:
                logger.warning(f"⚠️ No knowledge entries found for language: {language}")
                return ""
            
            # Combine all content
            content_blocks = []
            for entry in knowledge_entries:
                content = entry.get("content", "")
                category = entry.get("category", "")
                
                if content:  # Only add if content exists
                    if category:
                        content_blocks.append(f"[{category}]\n{content}")
                    else:
                        content_blocks.append(content)
            
            combined_content = "\n\n---\n\n".join(content_blocks)
            
            if combined_content:
                logger.info(f"✅ Loaded {len(content_blocks)} knowledge entries for language: {language}")
            
            return combined_content
            
        except Exception as e:
            logger.error(f"❌ Error loading knowledge from database: {e}", exc_info=True)
            return ""
    
    async def get_answer(self, question: str, language: str, context: Optional[str] = None) -> str:
        """Get answer from knowledge base using Groq LLM"""
        try:
            # Load knowledge base
            knowledge_base = self.load_knowledge_from_db(language)
            
            if not knowledge_base:
                logger.info(f"⚠️ No knowledge base found for language: {language}, using LLM general knowledge")
                return await self._get_answer_from_llm(question, language, context)
            
            # Build system prompt
            system_prompt = self._build_system_prompt(language, knowledge_base, context)
            
            # Prepare messages for Groq API
            messages_for_ai = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
            
            # Call Groq API
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": messages_for_ai,
                    "temperature": 0.3,
                    "max_tokens": 150,
                },
                timeout=10,
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Groq API error: {response.status_code} - {response.text}")
                return await self._get_answer_from_llm(question, language, context)
            
            # Extract answer
            result = response.json()
            answer = result["choices"][0]["message"]["content"].strip()
            
            # Clean up the answer
            answer = self._clean_answer(answer)
            
            logger.info(f"✅ Knowledge base answered: '{question[:40]}...' in {language}")
            
            return answer
            
        except requests.exceptions.Timeout:
            logger.error("⏱️ Groq API timeout")
            return self._get_minimal_fallback(language)
        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 Groq API request error: {e}")
            return self._get_minimal_fallback(language)
        except Exception as e:
            logger.error(f"❌ Error getting answer from knowledge base: {e}", exc_info=True)
            return self._get_minimal_fallback(language)
    
    async def _get_answer_from_llm(self, question: str, language: str, context: Optional[str] = None) -> str:
        """Get answer directly from LLM when knowledge base is empty"""
        try:
            # Build general system prompt
            system_prompt = self._build_general_prompt(language, context)
            
            messages_for_ai = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
            
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": messages_for_ai,
                    "temperature": 0.3,
                    "max_tokens": 120,
                },
                timeout=10,
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result["choices"][0]["message"]["content"].strip()
                return self._clean_answer(answer)
            else:
                return self._get_minimal_fallback(language)
                
        except Exception:
            return self._get_minimal_fallback(language)
    
    def _build_system_prompt(self, language: str, knowledge_base: str, context: Optional[str] = None) -> str:
        """Build system prompt with knowledge base"""
        
        language_instructions = {
            "en": "Answer in English naturally and concisely. Keep it short (2-3 sentences max).",
            "hi": "Answer in Hindi (Devanagari script) naturally and concisely. Keep it short (2-3 sentences max).",
            "ne": "Answer in Nepali (Devanagari script) naturally and concisely. Keep it short (2-3 sentences max).",
            "mr": "Answer in Marathi (Devanagari script) naturally and concisely. Keep it short (2-3 sentences max)."
        }
        
        lang_config = language_instructions.get(language, language_instructions["en"])
        
        prompt = f"""You are a helpful assistant for Chirag Sharma's celebrity makeup artist booking service.

{lang_config}

IMPORTANT: Keep your answer VERY SHORT - 2-3 sentences maximum.
Answer naturally and conversationally.

KNOWLEDGE BASE:
{knowledge_base}

{f"CONTEXT: {context}" if context else ""}

Answer the question based on the knowledge above."""

        return prompt
    
    def _build_general_prompt(self, language: str, context: Optional[str] = None) -> str:
        """Build general prompt without knowledge base"""
        
        language_instructions = {
            "en": "Answer in English naturally and concisely. Keep it short (2-3 sentences max).",
            "hi": "Answer in Hindi (Devanagari script) naturally and concisely. Keep it short (2-3 sentences max).",
            "ne": "Answer in Nepali (Devanagari script) naturally and concisely. Keep it short (2-3 sentences max).",
            "mr": "Answer in Marathi (Devanagari script) naturally and concisely. Keep it short (2-3 sentences max)."
        }
        
        lang_config = language_instructions.get(language, language_instructions["en"])
        
        prompt = f"""You are a helpful assistant for Chirag Sharma's celebrity makeup artist booking service.

{lang_config}

{f"CONTEXT: {context}" if context else ""}

Answer the question concisely and helpfully."""

        return prompt
    
    def _clean_answer(self, answer: str) -> str:
        """Clean up AI-generated answer"""
        answer = answer.strip()
        
        # Remove unwanted prefixes
        unwanted_prefixes = [
            "According to the knowledge base",
            "Based on the information",
            "As per the knowledge base",
            "The knowledge base states",
            "From the knowledge base",
            "According to",
            "Based on"
        ]
        
        for prefix in unwanted_prefixes:
            if answer.lower().startswith(prefix.lower()):
                answer = answer[len(prefix):].strip()
                if answer.startswith(("," or ":")):
                    answer = answer[1:].strip()
                if answer:
                    answer = answer[0].upper() + answer[1:]
        
        return answer
    
    def _get_minimal_fallback(self, language: str) -> str:
        """Provide minimal fallback when everything fails"""
        
        fallback_messages = {
            "en": "Please continue with your booking for more information.",
            "hi": "अधिक जानकारी के लिए कृपया अपनी बुकिंग जारी रखें।",
            "ne": "थप जानकारीको लागि कृपया आफ्नो बुकिङ जारी राख्नुहोस्।",
            "mr": "अधिक माहितीसाठी कृपया तुमची बुकिंग सुरू ठेवा."
        }
        
        return fallback_messages.get(language, fallback_messages["en"])