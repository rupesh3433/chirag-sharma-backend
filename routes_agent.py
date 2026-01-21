from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Tuple, Dict, Any
import logging
import re
import requests
from datetime import datetime, timedelta
from random import randint
import secrets

from config import LANGUAGE_MAP, TWILIO_WHATSAPP_FROM, GROQ_API_KEY, COUNTRY_CODES
from agent_models import ConversationMemory, AgentResponse
from agent_service import generate_agent_response, get_missing_fields, format_phone_with_country_code
from memory_store import create_session, get_memory, update_memory, delete_memory
from services import twilio_client
from database import booking_collection
from prompts import get_base_system_prompt, get_language_reset_prompt

router = APIRouter(prefix="/agent", tags=["Agent Chat"])
logger = logging.getLogger(__name__)

# Temporary OTP storage for agent bookings
AGENT_BOOKING_OTPS = {}

# ==========================================================
# REQUEST/RESPONSE MODELS
# ==========================================================

class AgentChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    language: str  # en | ne | hi | mr

class AgentChatResponse(BaseModel):
    reply: str
    session_id: str
    stage: str
    action: str
    missing_fields: List[str]
    booking_id: Optional[str] = None
    chat_mode: str = "agent"  # Add this field

# ==========================================================
# HELPER: Normal Chat (Reusing routes_public.py logic)
# ==========================================================

def get_normal_chat_response(messages: List[Dict], language: str) -> str:
    """Reuse the normal chat logic from routes_public.py"""
    
    language_reset_prompt = get_language_reset_prompt(language)
    base_prompt = get_base_system_prompt(language)
    
    messages_for_ai = [
        {"role": "system", "content": base_prompt},
        {"role": "system", "content": language_reset_prompt},
    ]
    
    for msg in messages:
        messages_for_ai.append(msg)
    
    max_retries = 2
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
                    "max_tokens": 500
                },
                timeout=15,
            )
            
            if response.status_code == 429:
                wait_time = 2 ** (attempt + 1)
                import time
                time.sleep(wait_time)
                continue
            elif response.status_code != 200:
                return "I'm having trouble connecting. Please try again."
            
            data = response.json()
            
            if "choices" not in data or len(data["choices"]) == 0:
                return "I'm having trouble processing that. Please try again."
            
            return data["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"Normal chat attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                return "Sorry, I'm having technical difficulties. Please try again."
    
    return "Sorry, I'm having technical difficulties. Please try again."

# ==========================================================
# AGENT ROUTES
# ==========================================================

@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(req: AgentChatRequest):
    """
    Intelligent chatbot that switches between normal chat and booking mode
    """
    
    # Validate language
    if req.language not in LANGUAGE_MAP:
        raise HTTPException(status_code=400, detail="Unsupported language")
    
    # Get or create session
    session_id = req.session_id
    memory = None
    
    if session_id:
        memory = get_memory(session_id)
    
    if not memory:
        # Create new session
        session_id = create_session(req.language)
        memory = get_memory(session_id)
    
    msg_lower = req.message.lower().strip()
    
    # Detect if user wants to exit booking mode
    exit_keywords = [
        "cancel", "stop", "exit", "quit", "go back", "normal chat", 
        "normal mode", "don't want to book", "dont want to book",
        "i don't want", "i dont want", "no booking", "forget it",
        "nevermind", "never mind", "not interested"
    ]
    
    if any(keyword in msg_lower for keyword in exit_keywords):
        # Reset to normal chat mode
        delete_memory(session_id)
        session_id = create_session(req.language)
        memory = get_memory(session_id)
        
        # Use normal chat
        chat_messages = [{"role": "user", "content": "I want to just chat, not book anything."}]
        reply = get_normal_chat_response(chat_messages, req.language)
        
        return AgentChatResponse(
            reply=reply,
            session_id=session_id,
            stage="greeting",
            action="continue",
            missing_fields=[],
            booking_id=None,
            chat_mode="normal"
        )
    
    # Check if user wants to restart booking
    restart_keywords = ["start over", "restart", "reset", "begin again", "do from start", "book again", "new booking"]
    if any(keyword in msg_lower for keyword in restart_keywords):
        # Reset session
        delete_memory(session_id)
        session_id = create_session(req.language)
        memory = get_memory(session_id)
        memory.stage = "collecting_info"
        update_memory(session_id, memory)
        
        service_options = (
            "Let's start fresh! Please select a service:\n"
            "1. Bridal Makeup Services\n"
            "2. Party Makeup Services\n"
            "3. Engagement & Pre-Wedding Makeup\n"
            "4. Henna (Mehendi) Services"
        )
        
        return AgentChatResponse(
            reply=service_options,
            session_id=session_id,
            stage="collecting_info",
            action="continue",
            missing_fields=get_missing_fields(memory.intent),
            booking_id=None,
            chat_mode="agent"
        )
    
    # Detect booking intent
    booking_keywords = [
        "book", "booking", "appointment", "schedule", "reserve",
        "i want", "i need", "looking for", "interested in", "would like",
        "bridal", "party", "engagement", "henna", "mehendi", "makeup", "service"
    ]
    
    has_booking_intent = any(keyword in msg_lower for keyword in booking_keywords)
    
    # Special: If user says "My details are:" or similar, treat as booking
    if "my details" in msg_lower or "details are" in msg_lower:
        has_booking_intent = True
    
    # If in greeting stage and no booking intent, use normal chat
    if memory.stage == "greeting" and not has_booking_intent:
        # Build conversation history for normal chat
        chat_messages = []
        for msg in memory.conversation_history[-4:]:
            chat_messages.append(msg)
        chat_messages.append({"role": "user", "content": req.message})
        
        reply = get_normal_chat_response(chat_messages, req.language)
        
        # Update memory
        memory.conversation_history.append({"role": "user", "content": req.message})
        memory.conversation_history.append({"role": "assistant", "content": reply})
        update_memory(session_id, memory)
        
        return AgentChatResponse(
            reply=reply,
            session_id=session_id,
            stage="greeting",
            action="continue",
            missing_fields=[],
            booking_id=None,
            chat_mode="normal"
        )
    
    # User has booking intent or already in booking flow
    if has_booking_intent and memory.stage == "greeting":
        memory.stage = "collecting_info"
        update_memory(session_id, memory)
    
    # Generate agent response for booking
    reply, updated_memory, action = generate_agent_response(
        req.message,
        memory,
        req.language
    )
    
    # Handle actions
    booking_id = None
    
    if action == "send_otp":
        # All information collected, send OTP
        booking_id, otp_reply = await send_otp_to_user(updated_memory, req.language)
        if booking_id:
            updated_memory.booking_id = booking_id
            reply = f"{reply}\n\n{otp_reply}"
            # Clear conversation history to keep it clean
            updated_memory.conversation_history = []
        else:
            # Failed to send OTP
            updated_memory.stage = "collecting_info"
            action = "continue"
    
    elif action == "verify_otp":
        # User provided OTP, verify it
        otp_match = re.search(r'\b\d{6}\b', req.message)
        if otp_match:
            otp = otp_match.group(0)
            verification_result = await verify_user_otp(
                updated_memory.booking_id,
                otp,
                updated_memory,
                req.language
            )
            
            if verification_result["success"]:
                reply = verification_result["message"]
                updated_memory.stage = "confirmed"
                action = "booking_confirmed"
                # Clean up memory after successful booking
                delete_memory(session_id)
            else:
                reply = verification_result["message"]
                updated_memory.otp_attempts += 1
                
                # Allow max 3 attempts
                if updated_memory.otp_attempts >= 3:
                    reply += "\n\n" + get_max_attempts_message(req.language)
                    updated_memory.stage = "collecting_info"
                    updated_memory.booking_id = None
                    updated_memory.otp_attempts = 0
        else:
            reply = "Please provide a valid 6-digit OTP."
    
    # Update memory
    update_memory(session_id, updated_memory)
    
    # Get missing fields
    missing_fields = get_missing_fields(updated_memory.intent)
    
    # Determine chat mode based on stage
    chat_mode = "agent" if updated_memory.stage != "greeting" else "normal"
    
    return AgentChatResponse(
        reply=reply,
        session_id=session_id,
        stage=updated_memory.stage,
        action=action,
        missing_fields=missing_fields,
        booking_id=booking_id,
        chat_mode=chat_mode
    )

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================

async def send_otp_to_user(memory: ConversationMemory, language: str) -> Tuple[Optional[str], str]:
    """Send OTP to user's WhatsApp"""
    
    intent = memory.intent
    
    # Validate required fields
    if not intent.phone:
        return None, "Phone number is required."
    
    # Format phone with country code
    phone = format_phone_with_country_code(intent.phone, intent.phone_country)
    
    # Validate phone format
    if not re.match(r"^\+\d{10,15}$", phone):
        return None, get_invalid_phone_message(language)
    
    # Generate OTP
    otp = str(randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    
    # Create booking ID
    booking_id = secrets.token_urlsafe(16)
    
    # Store OTP and booking data
    AGENT_BOOKING_OTPS[booking_id] = {
        "otp": otp,
        "expires_at": expires_at,
        "booking_data": {
            "service": intent.service,
            "package": intent.package,
            "name": intent.name,
            "email": intent.email,
            "phone": phone,
            "phone_country": intent.phone_country,
            "service_country": intent.service_country,
            "address": intent.address,
            "pincode": intent.pincode,
            "date": intent.date,
            "message": intent.message,
            "language": memory.language
        }
    }
    
    # Send OTP via WhatsApp
    if not twilio_client:
        logger.error("Twilio client not initialized")
        AGENT_BOOKING_OTPS.pop(booking_id, None)
        return None, get_otp_failed_message(language)
    
    try:
        # Send OTP message
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{phone}",
            body=f"Your JinniChirag booking OTP is {otp}"
        )
        
        logger.info(f"OTP sent to {phone} for agent booking {booking_id}")
        return booking_id, get_otp_sent_message(language)
        
    except Exception as e:
        logger.error(f"Failed to send OTP to {phone}: {e}")
        AGENT_BOOKING_OTPS.pop(booking_id, None)
        return None, get_otp_failed_message(language)

async def verify_user_otp(
    booking_id: str,
    otp: str,
    memory: ConversationMemory,
    language: str
) -> Dict[str, Any]:
    """Verify OTP and create booking"""
    
    if not booking_id:
        return {
            "success": False,
            "message": get_invalid_booking_message(language)
        }
    
    temp = AGENT_BOOKING_OTPS.get(booking_id)
    
    if not temp:
        return {
            "success": False,
            "message": get_invalid_booking_message(language)
        }
    
    if datetime.utcnow() > temp["expires_at"]:
        AGENT_BOOKING_OTPS.pop(booking_id, None)
        return {
            "success": False,
            "message": get_otp_expired_message(language)
        }
    
    if otp != temp["otp"]:
        return {
            "success": False,
            "message": get_invalid_otp_message(language)
        }
    
    # ✅ OTP VERIFIED → SAVE TO DB
    booking_data = temp["booking_data"]
    booking_data.update({
        "status": "pending",
        "otp_verified": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "source": "agent_chat",
        "session_id": memory.session_id
    })
    
    try:
        result = booking_collection.insert_one(booking_data)
        AGENT_BOOKING_OTPS.pop(booking_id, None)
        
        logger.info(f"Agent booking confirmed: {result.inserted_id}")
        
        return {
            "success": True,
            "message": get_booking_confirmed_message(language, memory.intent.name)
        }
    except Exception as e:
        logger.error(f"Failed to save booking: {e}")
        return {
            "success": False,
            "message": "Failed to save booking. Please try again."
        }

# ==========================================================
# LOCALIZED MESSAGES
# ==========================================================

def get_otp_sent_message(language: str) -> str:
    messages = {
        "en": "✅ I've sent a 6-digit OTP to your WhatsApp. Please share it here to confirm.",
        "ne": "✅ मैले तपाईंको व्हाट्सएपमा ६-अङ्कको OTP पठाएको छु। कृपया यहाँ साझा गर्नुहोस्।",
        "hi": "✅ मैंने आपके व्हाट्सएप पर 6-अंकों का OTP भेजा है। कृपया यहाँ शेयर करें।",
        "mr": "✅ मी तुमच्या व्हाट्सअॅपवर 6-अंकी OTP पाठवला आहे. कृपया येथे शेअर करा."
    }
    return messages.get(language, messages["en"])

def get_invalid_phone_message(language: str) -> str:
    messages = {
        "en": "❌ Invalid phone format. Please provide a valid number with country code.",
        "ne": "❌ अवैध फोन ढाँचा। कृपया देश कोडसहित मान्य नम्बर प्रदान गर्नुहोस्।",
        "hi": "❌ अमान्य फ़ोन फॉर्मेट। कृपया देश कोड के साथ मान्य नंबर प्रदान करें।",
        "mr": "❌ अवैध फोन फॉरमॅट. कृपया देश कोडसह वैध नंबर प्रदान करा."
    }
    return messages.get(language, messages["en"])

def get_otp_failed_message(language: str) -> str:
    messages = {
        "en": "❌ Couldn't send OTP. Please check your phone number.",
        "ne": "❌ OTP पठाउन सकिएन। कृपया आफ्नो फोन नम्बर जाँच गर्नुहोस्।",
        "hi": "❌ OTP नहीं भेज सका। कृपया अपना फ़ोन नंबर जाँचें।",
        "mr": "❌ OTP पाठवू शकलो नाही. कृपया तुमचा फोन नंबर तपासा."
    }
    return messages.get(language, messages["en"])

def get_invalid_booking_message(language: str) -> str:
    messages = {
        "en": "❌ Invalid or expired booking. Please start over.",
        "ne": "❌ अवैध वा म्याद सकिएको बुकिङ। कृपया फेरि सुरु गर्नुहोस्।",
        "hi": "❌ अमान्य या समाप्त बुकिंग। कृपया फिर से शुरू करें।",
        "mr": "❌ अवैध किंवा कालबाह्य बुकिंग. कृपया पुन्हा सुरू करा."
    }
    return messages.get(language, messages["en"])

def get_otp_expired_message(language: str) -> str:
    messages = {
        "en": "❌ OTP expired. Please request a new one.",
        "ne": "❌ OTP को म्याद समाप्त भयो। कृपया नयाँ अनुरोध गर्नुहोस्।",
        "hi": "❌ OTP समाप्त हो गया। कृपया नया अनुरोध करें।",
        "mr": "❌ OTP कालबाह्य झाला. कृपया नवीन विनंती करा."
    }
    return messages.get(language, messages["en"])

def get_invalid_otp_message(language: str) -> str:
    messages = {
        "en": "❌ Invalid OTP. Please try again.",
        "ne": "❌ अवैध OTP। कृपया पुन: प्रयास गर्नुहोस्।",
        "hi": "❌ अमान्य OTP। कृपया पुनः प्रयास करें।",
        "mr": "❌ अवैध OTP. कृपया पुन्हा प्रयत्न करा."
    }
    return messages.get(language, messages["en"])

def get_max_attempts_message(language: str) -> str:
    messages = {
        "en": "Maximum attempts exceeded. Let's start fresh!",
        "ne": "अधिकतम प्रयास पार भयो। नयाँ सुरु गरौं!",
        "hi": "अधिकतम प्रयास पार हो गए। नए सिरे से शुरू करें!",
        "mr": "जास्तीत जास्त प्रयत्न पार झाले. नव्याने सुरुवात करूया!"
    }
    return messages.get(language, messages["en"])

def get_booking_confirmed_message(language: str, name: str) -> str:
    messages = {
        "en": f"🎉 Congratulations {name}! Your booking request is submitted!\n\n📋 Our admin will review and send WhatsApp confirmation once approved.\n\nThank you for choosing JinniChirag! 💄✨",
        "ne": f"🎉 बधाई छ {name}! तपाईंको बुकिङ अनुरोध पेश गरिएको छ!\n\n📋 प्रशासकले समीक्षा गर्नेछ र स्वीकृत भएपछि व्हाट्सएप पुष्टि पठाउनेछ।\n\nJinniChirag छनोट गर्नुभएकोमा धन्यवाद! 💄✨",
        "hi": f"🎉 बधाई हो {name}! आपका बुकिंग अनुरोध सबमिट हुआ!\n\n📋 एडमिन समीक्षा करेगा और स्वीकृत होने पर व्हाट्सएप पुष्टि भेजेगा।\n\nJinniChirag चुनने के लिए धन्यवाद! 💄✨",
        "mr": f"🎉 अभिनंदन {name}! तुमची बुकिंग विनंती सबमिट झाली!\n\n📋 अॅडमिन पुनरावलोकन करेल आणि मंजूर झाल्यावर व्हाट्सअॅप पुष्टी पाठवेल।\n\nJinniChirag निवडल्याबद्दल धन्यवाद! 💄✨"
    }
    return messages.get(language, messages["en"])