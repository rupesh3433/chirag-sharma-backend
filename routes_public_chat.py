# routes_public_chat.py
# ============================================================
# PUBLIC CHAT ROUTES
# ============================================================
# AI chatbot functionality separated from booking routes
# ============================================================

from fastapi import APIRouter, HTTPException
from datetime import datetime
import requests
import logging
import time

from models import ChatRequest
from config import GROQ_API_KEY, LANGUAGE_MAP
from prompts import get_base_system_prompt, get_language_reset_prompt
from rate_limiter import rate_limiter

router = APIRouter(prefix="/chat", tags=["Public Chat"])
logger = logging.getLogger(__name__)


# ============================================================
# CHAT ENDPOINT
# ============================================================

@router.post("")
async def chat(req: ChatRequest):
    """
    Public chatbot endpoint with retry logic.
    
    Supports multiple languages: English, Nepali, Hindi, Marathi
    Includes rate limiting and GROQ API retry mechanism
    """
    
    # Validate language
    language_name = LANGUAGE_MAP.get(req.language)
    if not language_name:
        raise HTTPException(400, "Unsupported language")
    
    # Rate limiting - use hash of first user message as key
    rate_limit_key = "chat_" + str(hash(str(req.messages[0].content if req.messages else "anon")))[:10]
    if not rate_limiter.check_rate_limit(rate_limit_key):
        remaining_time = int(rate_limiter.get_reset_time(rate_limit_key))
        raise HTTPException(
            429, 
            f"Too many requests. Please wait {remaining_time} seconds."
        )

    # Get prompts
    language_reset_prompt = get_language_reset_prompt(req.language)
    base_prompt = get_base_system_prompt(req.language)
    
    # Build messages for AI
    messages_for_ai = [
        {"role": "system", "content": base_prompt},
        {"role": "system", "content": language_reset_prompt},
    ]

    for msg in req.messages:
        messages_for_ai.append(msg.dict())

    # Retry logic for GROQ rate limits
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": messages_for_ai,
                    "temperature": 0.4,
                    "max_tokens": 250,
                },
                timeout=20,
            )
            
            # Handle rate limiting
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(f"GROQ rate limit hit, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"GROQ API rate limit after {max_retries} retries")
                    raise HTTPException(
                        429, 
                        "AI service is busy. Please try again in a few seconds."
                    )
            
            # Handle other errors
            if response.status_code != 200:
                logger.error(f"GROQ API error {response.status_code}: {response.text}")
                raise HTTPException(500, "AI service temporarily unavailable")
            
            # Parse response
            data = response.json()
            
            # Validate response structure
            if "choices" not in data or not data["choices"]:
                logger.error(f"GROQ API invalid response: {data}")
                raise HTTPException(500, "AI service returned invalid response")
            
            return {
                "reply": data["choices"][0]["message"]["content"]
            }
            
        except requests.exceptions.Timeout:
            logger.error("GROQ API timeout")
            if attempt < max_retries - 1:
                continue
            raise HTTPException(504, "AI service timeout")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"GROQ API request failed: {e}")
            if attempt < max_retries - 1:
                continue
            raise HTTPException(500, "AI service unavailable")
            
        except HTTPException:
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error in chat: {e}")
            raise HTTPException(500, "Internal server error")
    
    # Should not reach here
    raise HTTPException(500, "Failed after retries")


# ============================================================
# HEALTH CHECK
# ============================================================

@router.get("/health")
async def chat_health():
    """Health check for chat service"""
    return {
        "status": "healthy",
        "service": "chat",
        "timestamp": datetime.utcnow().isoformat(),
        "supported_languages": list(LANGUAGE_MAP.keys())
    }