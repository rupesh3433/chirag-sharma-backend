from fastapi import APIRouter, HTTPException
import logging
import re
import requests
from datetime import datetime, timedelta
from random import randint
import secrets

from agent_models import AgentChatRequest, AgentChatResponse
from agent_service import (
    extract_intent_from_message,
    format_phone_for_api, 
    format_phone_display,
    create_booking_data,
    get_conversation_context
)
from agent_prompts import (
    get_welcome_message, 
    get_otp_sent_message, 
    get_booking_confirmed_message, 
    detect_booking_intent,
    get_package_options,
    get_agent_system_prompt,
    SERVICES
)
from prompts import get_base_system_prompt
from memory_store import memory_store
from database import booking_collection
from config import TWILIO_WHATSAPP_FROM, GROQ_API_KEY
from services import twilio_client

router = APIRouter(prefix="/agent", tags=["Agent Chat"])
logger = logging.getLogger(__name__)

TEMP_OTP_STORE = {}

@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(req: AgentChatRequest):
    """
    ENHANCED: Agent with knowledge base integration and smart extraction
    """
    
    if req.language not in ["en", "ne", "hi", "mr"]:
        raise HTTPException(400, "Unsupported language")
    
    # Get or create session
    memory = memory_store.get_memory(req.session_id) if req.session_id else None
    if not memory:
        session_id = memory_store.create_session(req.language)
        memory = memory_store.get_memory(session_id)
    
    msg_lower = req.message.lower().strip()
    
    # Handle special commands
    if any(word in msg_lower for word in ["exit", "cancel", "stop"]):
        if memory.stage != "greeting":
            memory_store.reset_memory(memory.session_id)
            memory = memory_store.get_memory(memory.session_id)
            return AgentChatResponse(
                reply="✅ Booking cancelled. How else can I help?",
                session_id=memory.session_id,
                stage=memory.stage,
                action="reset",
                missing_fields=[],
                collected_info={},
                chat_mode="normal"
            )
    
    if any(word in msg_lower for word in ["restart", "start over"]):
        memory_store.reset_memory(memory.session_id)
        memory = memory_store.get_memory(memory.session_id)
        memory.stage = "collecting_info"
        memory_store.update_memory(memory.session_id, memory)
        
        welcome = get_welcome_message(req.language, is_booking=True)
        memory.add_message("user", req.message)
        memory.add_message("assistant", welcome)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=welcome,
            session_id=memory.session_id,
            stage=memory.stage,
            action="continue",
            missing_fields=memory.intent.missing_fields(),
            collected_info=memory.intent.get_summary(),
            chat_mode="agent"
        )
    
    # Check if user wants to see collected info
    if "what information" in msg_lower or "what do you have" in msg_lower or "collected info" in msg_lower:
        summary = memory.intent.get_summary()
        missing = memory.intent.missing_fields()
        
        if summary:
            reply = "**Information I have collected:**\n\n"
            for key, value in summary.items():
                reply += f"• {key}: {value}\n"
            
            if missing:
                reply += f"\n**Still need:** {', '.join(missing)}"
        else:
            reply = "I haven't collected any information yet. Let's start booking!"
        
        memory.add_message("user", req.message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply,
            session_id=memory.session_id,
            stage=memory.stage,
            action="continue",
            missing_fields=missing,
            collected_info=summary,
            chat_mode="agent" if memory.stage != "greeting" else "normal"
        )
    
    # Detect booking intent in greeting stage
    if memory.stage == "greeting":
        if detect_booking_intent(req.message, req.language):
            memory.stage = "collecting_info"
            welcome = get_welcome_message(req.language, is_booking=True)
            
            memory.add_message("user", req.message)
            memory.add_message("assistant", welcome)
            memory_store.update_memory(memory.session_id, memory)
            
            return AgentChatResponse(
                reply=welcome,
                session_id=memory.session_id,
                stage=memory.stage,
                action="continue",
                missing_fields=memory.intent.missing_fields(),
                collected_info={},
                chat_mode="agent",
                next_expected="service"
            )
        else:
            # Use AI with knowledge base for general queries
            return await _handle_general_query(req.message, memory, req.language)
    
    # Handle OTP verification
    if memory.stage == "otp_sent":
        return await _handle_otp_verification(req.message, memory, req.language)
    
    # Build conversation context
    conv_context = get_conversation_context(memory)
    
    # Extract intent with context awareness
    memory.intent = extract_intent_from_message(
        req.message, 
        memory.intent, 
        memory.last_asked_field,
        conv_context
    )
    
    # Get missing fields
    missing = memory.intent.missing_fields()
    
    # If all info collected, send OTP
    if not missing and memory.stage == "collecting_info":
        return await _send_otp_to_user(memory, req.language)
    
    # Still collecting info - ask for next field
    if missing and memory.stage == "collecting_info":
        next_field = missing[0]
        reply = _get_field_question(next_field, memory.intent, req.language)
        
        memory.last_asked_field = _get_field_key(next_field)
        
        memory.add_message("user", req.message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply,
            session_id=memory.session_id,
            stage=memory.stage,
            action="continue",
            missing_fields=missing,
            collected_info=memory.intent.get_summary(),
            chat_mode="agent",
            next_expected=memory.last_asked_field
        )
    
    # Default fallback
    reply = get_welcome_message(req.language, is_booking=False)
    memory.add_message("user", req.message)
    memory.add_message("assistant", reply)
    memory_store.update_memory(memory.session_id, memory)
    
    return AgentChatResponse(
        reply=reply,
        session_id=memory.session_id,
        stage=memory.stage,
        action="continue",
        missing_fields=[],
        collected_info={},
        chat_mode="normal"
    )

async def _handle_general_query(message: str, memory, language: str) -> AgentChatResponse:
    """
    Handle general queries using AI with knowledge base
    """
    # Get knowledge base system prompt
    kb_prompt = get_base_system_prompt(language)
    
    # Build messages for AI
    messages = [
        {"role": "system", "content": kb_prompt},
        {"role": "system", "content": f"You are helpful and answer in {language.upper()}. Keep responses concise (2-3 sentences)."}
    ]
    
    # Add conversation history
    for msg in memory.conversation_history[-4:]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    # Add current message
    messages.append({"role": "user", "content": message})
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": messages,
                "temperature": 0.4,
                "max_tokens": 300
            },
            timeout=15,
        )
        
        if response.status_code == 200:
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
        else:
            reply = get_welcome_message(language, is_booking=False)
    
    except Exception as e:
        logger.error(f"AI query failed: {e}")
        reply = get_welcome_message(language, is_booking=False)
    
    memory.add_message("user", message)
    memory.add_message("assistant", reply)
    memory_store.update_memory(memory.session_id, memory)
    
    return AgentChatResponse(
        reply=reply,
        session_id=memory.session_id,
        stage=memory.stage,
        action="continue",
        missing_fields=[],
        collected_info={},
        chat_mode="normal"
    )

def _get_field_key(field_label: str) -> str:
    """Convert field label to key"""
    mapping = {
        "service type": "service",
        "package choice": "package",
        "your name": "name",
        "email address": "email",
        "phone number": "phone",
        "service country": "service_country",
        "service address": "address",
        "PIN/postal code": "pincode",
        "preferred date": "date"
    }
    return mapping.get(field_label, field_label.replace(" ", "_"))

def _get_field_question(field: str, intent, language: str) -> str:
    """Generate appropriate question for each field"""
    
    questions = {
        "en": {
            "service type": "What type of makeup service would you like?\n\n1️⃣ Bridal Makeup\n2️⃣ Party Makeup\n3️⃣ Engagement & Pre-Wedding\n4️⃣ Henna (Mehendi)\n\nReply with number or service name:",
            "package choice": lambda: get_package_options(intent.service, language),
            "your name": "What's your full name?",
            "email address": "What's your email address?",
            "phone number": "What's your phone number?\n(If different from service location, mention: 'I live in [country]' or use country code like +91, +977)",
            "service country": "Which country do you need the makeup service in?\n(India, Nepal, Pakistan, Bangladesh, or Dubai)",
            "service address": "What's the complete address where you need the service?",
            "PIN/postal code": "What's the PIN/postal code of your location?",
            "preferred date": "What's your preferred date?\n(Examples: '5th February 2026', '05-02-2026', 'February 5')"
        },
        "ne": {
            "service type": "कुन प्रकारको मेकअप सेवा चाहिन्छ?\n\n1️⃣ ब्राइडल मेकअप\n2️⃣ पार्टी मेकअप\n3️⃣ इन्गेजमेन्ट र प्री-वेडिंग\n4️⃣ हेन्ना (मेहेन्दी)",
            "package choice": lambda: get_package_options(intent.service, language),
            "your name": "तपाईंको पूरा नाम के हो?",
            "email address": "तपाईंको इमेल के हो?",
            "phone number": "तपाईंको फोन नम्बर?\n(यदि सेवा स्थानभन्दा फरक छ भने: 'म [देश] मा बस्छु' वा +977 जस्तो कोड प्रयोग गर्नुहोस्)",
            "service country": "कुन देशमा मेकअप सेवा चाहिन्छ?\n(भारत, नेपाल, पाकिस्तान, बंगलादेश, वा दुबई)",
            "service address": "सेवाको लागि पूरा ठेगाना?",
            "PIN/postal code": "तपाईंको PIN/postal कोड?",
            "preferred date": "मिति कहिले चाहिन्छ?\n(उदाहरण: '५ फेब्रुअरी २०२६', '०५-०२-२०२६')"
        }
    }
    
    lang_questions = questions.get(language, questions["en"])
    question = lang_questions.get(field)
    
    if callable(question):
        return question()
    
    return question or f"Please provide your {field}."

async def _send_otp_to_user(memory, language: str) -> AgentChatResponse:
    """Send OTP when all info is collected"""
    
    # Validate phone
    phone_country = memory.intent.phone_country or memory.intent.service_country or "India"
    phone = format_phone_for_api(memory.intent.phone, phone_country)
    
    if not phone or not phone.startswith("+"):
        return AgentChatResponse(
            reply="❌ Invalid phone number. Please provide a valid phone number with country code.",
            session_id=memory.session_id,
            stage=memory.stage,
            action="continue",
            missing_fields=["phone number"],
            collected_info=memory.intent.get_summary(),
            chat_mode="agent"
        )
    
    # Show summary with proper formatting
    phone_display = format_phone_display(memory.intent.phone, phone_country)
    summary = memory.intent.get_summary()
    
    confirmation = "✅ **Booking Summary:**\n\n"
    for key, value in summary.items():
        if key == "Phone":
            confirmation += f"📱 {key}: {phone_display}\n"
        elif key == "Phone Country":
            confirmation += f"📍 Phone Location: {value}\n"
        elif key == "Country":
            confirmation += f"🌍 Service Location: {value}\n"
        else:
            confirmation += f"• {key}: {value}\n"
    
    confirmation += "\n🔐 Sending OTP for verification..."
    
    # Generate OTP
    otp = str(randint(100000, 999999))
    booking_id = secrets.token_urlsafe(16)
    
    TEMP_OTP_STORE[booking_id] = {
        "otp": otp,
        "expires_at": datetime.utcnow() + timedelta(minutes=5),
        "booking_data": create_booking_data(memory),
        "session_id": memory.session_id
    }
    
    # Send WhatsApp
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{phone}",
            body=f"Your JinniChirag booking OTP is {otp}. Valid for 5 minutes."
        )
        
        memory.stage = "otp_sent"
        memory.booking_id = booking_id
        memory.last_asked_field = "otp"
        
        otp_msg = get_otp_sent_message(language, phone_display)
        reply = f"{confirmation}\n\n{otp_msg}"
        
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        logger.info(f"OTP sent to {phone} (phone_country: {phone_country}) for booking {booking_id[:8]}...")
        
        return AgentChatResponse(
            reply=reply,
            session_id=memory.session_id,
            stage=memory.stage,
            action="send_otp",
            missing_fields=[],
            collected_info=summary,
            booking_id=booking_id,
            chat_mode="agent",
            next_expected="otp"
        )
        
    except Exception as e:
        logger.error(f"Failed to send OTP: {e}")
        TEMP_OTP_STORE.pop(booking_id, None)
        
        return AgentChatResponse(
            reply="❌ Failed to send OTP. Please verify your phone number and try again.",
            session_id=memory.session_id,
            stage="collecting_info",
            action="continue",
            missing_fields=["phone number"],
            collected_info=summary,
            chat_mode="agent"
        )

async def _handle_otp_verification(otp_message: str, memory, language: str) -> AgentChatResponse:
    """Handle OTP verification"""
    
    otp_match = re.search(r'\b\d{6}\b', otp_message)
    
    if not otp_match:
        reply = "Please enter the 6-digit OTP sent to your WhatsApp."
        memory.add_message("user", otp_message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply,
            session_id=memory.session_id,
            stage=memory.stage,
            action="continue",
            missing_fields=[],
            collected_info=memory.intent.get_summary(),
            booking_id=memory.booking_id,
            chat_mode="agent"
        )
    
    otp = otp_match.group(0)
    temp_data = TEMP_OTP_STORE.get(memory.booking_id)
    
    if not temp_data:
        memory_store.delete_memory(memory.session_id)
        return AgentChatResponse(
            reply="❌ OTP expired or invalid. Please start a new booking.",
            session_id=memory_store.create_session(language),
            stage="greeting",
            action="reset",
            missing_fields=[],
            collected_info={},
            chat_mode="normal"
        )
    
    if datetime.utcnow() > temp_data["expires_at"]:
        TEMP_OTP_STORE.pop(memory.booking_id, None)
        memory_store.delete_memory(memory.session_id)
        
        return AgentChatResponse(
            reply="⏰ OTP expired (5 min limit). Please start a new booking.",
            session_id=memory_store.create_session(language),
            stage="greeting",
            action="reset",
            missing_fields=[],
            collected_info={},
            chat_mode="normal"
        )
    
    if otp != temp_data["otp"]:
        memory.otp_attempts += 1
        memory_store.update_memory(memory.session_id, memory)
        
        if memory.otp_attempts >= 3:
            TEMP_OTP_STORE.pop(memory.booking_id, None)
            memory_store.delete_memory(memory.session_id)
            
            return AgentChatResponse(
                reply="❌ Too many failed attempts. Please start a new booking.",
                session_id=memory_store.create_session(language),
                stage="greeting",
                action="reset",
                missing_fields=[],
                collected_info={},
                chat_mode="normal"
            )
        
        reply = f"❌ Invalid OTP. {3 - memory.otp_attempts} attempt(s) left."
        memory.add_message("user", otp_message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply,
            session_id=memory.session_id,
            stage=memory.stage,
            action="continue",
            missing_fields=[],
            collected_info=memory.intent.get_summary(),
            booking_id=memory.booking_id,
            chat_mode="agent"
        )
    
    # ✅ OTP VERIFIED
    booking_data = temp_data["booking_data"]
    booking_data["otp_verified"] = True
    booking_data["verified_at"] = datetime.utcnow()
    
    try:
        result = booking_collection.insert_one(booking_data)
        TEMP_OTP_STORE.pop(memory.booking_id, None)
        
        logger.info(f"✅ Booking confirmed: {result.inserted_id}")
        
        name = memory.intent.name or "Customer"
        success_msg = get_booking_confirmed_message(language, name)
        
        memory_store.delete_memory(memory.session_id)
        
        return AgentChatResponse(
            reply=success_msg,
            session_id=memory_store.create_session(language),
            stage="greeting",
            action="booking_confirmed",
            missing_fields=[],
            collected_info={},
            booking_id=str(result.inserted_id),
            chat_mode="normal"
        )
        
    except Exception as e:
        logger.error(f"Failed to save booking: {e}")
        
        return AgentChatResponse(
            reply="❌ Failed to save booking. Please contact support.",
            session_id=memory.session_id,
            stage=memory.stage,
            action="continue",
            missing_fields=[],
            collected_info=memory.intent.get_summary(),
            booking_id=memory.booking_id,
            chat_mode="agent"
        )

@router.get("/sessions")
async def get_session_stats():
    """Get session statistics"""
    stats = memory_store.get_stats()
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat(), **stats}

@router.post("/cleanup")
async def force_cleanup():
    """Force cleanup expired sessions"""
    cleaned = memory_store.cleanup_old_sessions()
    return {"status": "ok", "cleaned": cleaned}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete specific session"""
    deleted = memory_store.delete_memory(session_id)
    if deleted:
        return {"status": "ok", "message": "Session deleted"}
    raise HTTPException(404, "Session not found")