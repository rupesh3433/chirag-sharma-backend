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
    SERVICES
)
from prompts import get_base_system_prompt
from memory_store import memory_store
from database import booking_collection
from config import TWILIO_WHATSAPP_FROM, GROQ_API_KEY
from services import twilio_client
from rate_limiter import rate_limiter

router = APIRouter(prefix="/agent", tags=["Agent Chat"])
logger = logging.getLogger(__name__)

TEMP_OTP_STORE = {}

@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(req: AgentChatRequest):
    """
    FIXED: Intelligent booking mode with better field extraction
    """
    
    if req.language not in ["en", "ne", "hi", "mr"]:
        raise HTTPException(400, "Unsupported language")
    
    # Rate limiting
    rate_limit_key = req.session_id or "anonymous"
    if not rate_limiter.check_rate_limit(rate_limit_key):
        remaining_time = int(rate_limiter.get_reset_time(rate_limit_key))
        raise HTTPException(
            429, 
            f"Too many requests. Please wait {remaining_time} seconds."
        )
    
    # Get or create session
    memory = memory_store.get_memory(req.session_id) if req.session_id else None
    if not memory:
        session_id = memory_store.create_session(req.language)
        memory = memory_store.get_memory(session_id)
    
    msg_lower = req.message.lower().strip()
    
    # EXPLICIT EXIT COMMANDS
    exit_keywords = ["exit booking", "cancel booking", "stop booking", "go to chat", 
                     "switch to chat", "chat mode", "exit agent", "cancel agent"]
    
    if any(keyword in msg_lower for keyword in exit_keywords):
        if memory.stage != "greeting":
            memory_store.reset_memory(memory.session_id)
            memory = memory_store.get_memory(memory.session_id)
            return AgentChatResponse(
                reply="✅ Booking cancelled. Switched to chat mode.",
                session_id=memory.session_id,
                stage=memory.stage,
                action="reset",
                missing_fields=[],
                collected_info={},
                chat_mode="normal"
            )
    
    # Restart booking
    if "restart" in msg_lower or "start over" in msg_lower:
        memory_store.reset_memory(memory.session_id)
        memory = memory_store.get_memory(memory.session_id)
        memory.stage = "collecting_info"
        memory_store.update_memory(memory.session_id, memory)
        
        reply = "🔄 Starting fresh! What service would you like? (Bridal/Party/Engagement/Henna)"
        memory.add_message("user", req.message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply,
            session_id=memory.session_id,
            stage=memory.stage,
            action="continue",
            missing_fields=memory.intent.missing_fields(),
            collected_info={},
            chat_mode="agent"
        )
    
    # BOOKING MODE: Once in, stay in unless explicitly exited
    if memory.stage == "collecting_info":
        return await _handle_booking_collection(req.message, memory, req.language)
    
    # OTP verification mode
    if memory.stage == "otp_sent":
        return await _handle_otp_verification(req.message, memory, req.language)
    
    # GREETING MODE: Detect booking intent
    if memory.stage == "greeting":
        if detect_booking_intent(req.message, req.language):
            memory.stage = "collecting_info"
            memory_store.update_memory(memory.session_id, memory)
            
            logger.info(f"🎯 Booking intent detected: '{req.message}'")
            
            # Try to extract from first message
            conv_context = get_conversation_context(memory)
            memory.intent = extract_intent_from_message(req.message, memory.intent, None, conv_context)
            
            # Check what we have
            missing = memory.intent.missing_fields()
            
            if memory.intent.service:
                # Has service, ask for package or next field
                if not memory.intent.package:
                    reply = get_package_options(memory.intent.service, req.language)
                    memory.last_asked_field = "package"
                else:
                    # Have service AND package, ask for next field
                    next_field = missing[0] if missing else None
                    reply = _get_short_question(next_field, memory.intent, req.language) if next_field else "Let me get your details."
                    memory.last_asked_field = _get_field_key(next_field) if next_field else None
            else:
                # No service yet, ask for it
                reply = "👋 Let's book! Which service?\n\n1. Bridal Makeup\n2. Party Makeup\n3. Engagement & Pre-Wedding\n4. Henna/Mehendi"
                memory.last_asked_field = "service"
            
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
                chat_mode="agent"
            )
        
        # General chat mode
        return await _handle_general_query(req.message, memory, req.language)

async def _handle_booking_collection(message: str, memory, language: str) -> AgentChatResponse:
    """
    FIXED: Better acknowledgment and field collection
    """
    
    msg_lower = message.lower().strip()
    
    # Build conversation context
    conv_context = get_conversation_context(memory)
    
    # Check if user is asking a question
    question_indicators = ["what", "which", "how much", "how many", "price", "cost", 
                          "tell me", "show me", "list", "available", "offer", "?",
                          "explain", "describe", "details", "include", "why"]
    is_question = any(ind in msg_lower for ind in question_indicators)
    
    # If it's a PURE question (no info mixed in), answer using AI
    if is_question and len(message.split()) <= 20:
        # Check if message also contains information
        has_info_patterns = [
            r'\b\d{10}\b',  # phone
            r'@\w+\.\w+',   # email
            r'\b\d{5,6}\b', # pincode
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'  # name pattern
        ]
        
        has_info = any(re.search(pattern, message) for pattern in has_info_patterns)
        
        if not has_info:
            # Pure question - answer it
            answer = await _answer_question_in_booking(message, memory, language)
            
            # After answering, continue asking for missing fields
            missing = memory.intent.missing_fields()
            if missing:
                next_field = missing[0]
                next_q = _get_short_question(next_field, memory.intent, language)
                reply = f"{answer}\n\n{next_q}"
            else:
                reply = answer
            
            memory.add_message("user", message)
            memory.add_message("assistant", reply)
            memory_store.update_memory(memory.session_id, memory)
            
            return AgentChatResponse(
                reply=reply,
                session_id=memory.session_id,
                stage=memory.stage,
                action="continue",
                missing_fields=missing,
                collected_info=memory.intent.get_summary(),
                chat_mode="agent"
            )
    
    # Extract information from message
    old_summary = memory.intent.get_summary()
    
    logger.info(f"🔍 Extracting from: '{message}'")
    logger.info(f"📋 Last asked field: {memory.last_asked_field}")
    
    memory.intent = extract_intent_from_message(
        message, 
        memory.intent, 
        memory.last_asked_field,
        conv_context
    )
    
    new_summary = memory.intent.get_summary()
    newly_collected = {k: v for k, v in new_summary.items() if k not in old_summary}
    
    logger.info(f"✅ Newly collected: {newly_collected}")
    
    # Get missing fields
    missing = memory.intent.missing_fields()
    
    logger.info(f"📝 Still missing: {missing}")
    
    # If all collected, send OTP
    if not missing:
        return await _send_otp_to_user(memory, language)
    
    # Build response with BETTER acknowledgment
    reply_parts = []
    
    # Acknowledge new fields with VALUES
    if newly_collected:
        ack_lines = []
        for field, value in newly_collected.items():
            if field == "Phone":
                # Show partial phone
                ack_lines.append(f"📱 {field}: {value[:4]}****{value[-2:]}")
            elif field == "Email":
                ack_lines.append(f"📧 {field}: {value}")
            elif field == "Name":
                ack_lines.append(f"👤 {field}: {value}")
            elif field == "Service":
                ack_lines.append(f"💄 {field}: {value}")
            elif field == "Package":
                ack_lines.append(f"📦 {field}: {value}")
            elif field == "Date":
                ack_lines.append(f"📅 {field}: {value}")
            elif field == "Country":
                ack_lines.append(f"🌍 {field}: {value}")
            else:
                ack_lines.append(f"✅ {field}: {value}")
        
        reply_parts.append("✅ Got it!\n" + "\n".join(ack_lines))
    
    # Ask for next field
    next_field = missing[0]
    question = _get_short_question(next_field, memory.intent, language)
    reply_parts.append(question)
    
    memory.last_asked_field = _get_field_key(next_field)
    
    reply = "\n\n".join(reply_parts)
    
    memory.add_message("user", message)
    memory.add_message("assistant", reply)
    memory_store.update_memory(memory.session_id, memory)
    
    return AgentChatResponse(
        reply=reply,
        session_id=memory.session_id,
        stage="collecting_info",
        action="continue",
        missing_fields=missing,
        collected_info=new_summary,
        chat_mode="agent",
        next_expected=memory.last_asked_field
    )

async def _answer_question_in_booking(message: str, memory, language: str) -> str:
    """Answer user's question CONCISELY while in booking mode"""
    kb_prompt = get_base_system_prompt(language)
    
    messages = [
        {"role": "system", "content": kb_prompt},
        {"role": "system", "content": f"""Answer the question briefly in {language.upper()}. User is booking, so be CONCISE.

Rules:
- Maximum 3-4 sentences
- If listing items, use simple bullets (• item - price)
- NO lengthy explanations
- Just answer what was asked
- Be direct and clear

Keep it SHORT!"""},
        {"role": "user", "content": message}
    ]
    
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
                "temperature": 0.3,
                "max_tokens": 200
            },
            timeout=15,
        )
        
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"AI answer failed: {e}")
    
    # Fallback
    if "service" in message.lower() or "package" in message.lower():
        return """**Services:**
• Bridal (₹60k-100k)
• Party (₹7k-20k)
• Engagement (₹20k-60k)
• Henna (₹20k-50k)"""
    
    return "Sure, continuing with booking..."



async def _handle_general_query(message: str, memory, language: str) -> AgentChatResponse:
    """Handle general queries using AI with knowledge base"""
    kb_prompt = get_base_system_prompt(language)
    
    # Check conversation context
    recent_context = ""
    if len(memory.conversation_history) >= 2:
        last_assistant = None
        for msg in reversed(memory.conversation_history):
            if msg["role"] == "assistant":
                last_assistant = msg["content"]
                break
        
        if last_assistant:
            recent_context = f"\nRecent context: User was just shown:\n{last_assistant[:500]}"
    
    messages = [
        {"role": "system", "content": kb_prompt},
        {"role": "system", "content": f"""You are JinniChirag AI assistant. Answer in {language.upper()}.

CRITICAL CONTEXT AWARENESS:
- If user says "1", "go for 1", "choose 1" etc., check what was just shown
- If you just listed services and they say "1", they want to BOOK service #1
- Respond: "Great choice! Would you like to book [Service Name]? Say 'book' to proceed."
- Be conversational and understand context

RESPONSE RULES:
- Keep responses SHORT (3-5 sentences max)
- Only show what user asked for
- If listing, use simple bullets
- NO lengthy descriptions
- End with ONE simple question if relevant{recent_context}"""}
    ]
    
    for msg in memory.conversation_history[-5:]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    messages.append({"role": "user", "content": message})
    
    # Retry logic
    max_retries = 3
    retry_delay = 2
    
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
                    "messages": messages,
                    "temperature": 0.4,
                    "max_tokens": 300
                },
                timeout=15,
            )
            
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(f"GROQ rate limit, retrying in {wait_time}s...")
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    reply = "I'm here to help! Ask about our services or say 'book' to make a booking."
                    break
            
            if response.status_code == 200:
                data = response.json()
                if "choices" in data and data["choices"]:
                    reply = data["choices"][0]["message"]["content"]
                    break
                else:
                    reply = "I'm here to help! Ask about our services or say 'book' to make a booking."
                    break
            else:
                logger.error(f"GROQ API error: {response.status_code}")
                if attempt < max_retries - 1:
                    continue
                reply = "I'm here to help! Ask about our services or say 'book' to make a booking."
                break
        
        except Exception as e:
            logger.error(f"AI query failed: {e}")
            if attempt < max_retries - 1:
                continue
            reply = "I'm here to help! Ask about our services or say 'book' to make a booking."
            break
    else:
        reply = "I'm here to help! Ask about our services or say 'book' to make a booking."
    
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



def _get_short_question(field: str, intent, language: str) -> str:
    """SHORT questions - no lengthy explanations"""
    
    questions = {
        "en": {
            "service type": "Which service? (Bridal/Party/Engagement/Henna)",
            "package choice": lambda: _get_short_packages(intent.service, language),
            "your name": "Your name?",
            "email address": "Email?",
            "phone number": "Phone number? (with country code like +91, +977)",
            "service country": "Service in which country? (India/Nepal/Pakistan/Bangladesh/Dubai)",
            "service address": "Service address?",
            "PIN/postal code": "PIN code?",
            "preferred date": "Preferred date? (e.g. 5 Feb 2026)"
        },
        "ne": {
            "service type": "कुन सेवा? (Bridal/Party/Engagement/Henna)",
            "package choice": lambda: _get_short_packages(intent.service, language),
            "your name": "नाम?",
            "email address": "इमेल?",
            "phone number": "फोन? (+91, +977)",
            "service country": "कुन देशमा? (India/Nepal/Pakistan/Bangladesh/Dubai)",
            "service address": "ठेगाना?",
            "PIN/postal code": "PIN?",
            "preferred date": "मिति? (जस्तै: 5 Feb 2026)"
        }
    }
    
    lang_q = questions.get(language, questions["en"])
    q = lang_q.get(field)
    
    if callable(q):
        return q()
    
    return q or f"{field}?"

def _get_short_packages(service: str, language: str) -> str:
    """Short package list"""
    if not service or service not in SERVICES:
        return "Package?"
    
    packages = SERVICES[service]["packages"]
    result = "Choose package:\n"
    
    for idx, (pkg, price) in enumerate(packages.items(), 1):
        # Shorten package names
        short_name = pkg.split("(")[0].strip() if "(" in pkg else pkg
        short_name = short_name.replace("Makeup", "").replace("Services", "").strip()
        result += f"{idx}. {short_name} - {price}\n"
    
    return result.strip()


async def _send_otp_to_user(memory, language: str) -> AgentChatResponse:
    """Send OTP when all info is collected"""
    
    # Validate all required fields
    required_fields = {
        'service': memory.intent.service,
        'package': memory.intent.package,
        'name': memory.intent.name,
        'email': memory.intent.email,
        'phone': memory.intent.phone,
        'service_country': memory.intent.service_country,
        'address': memory.intent.address,
        'pincode': memory.intent.pincode,
        'date': memory.intent.date
    }
    
    missing = [field for field, value in required_fields.items() if not value]
    
    if missing:
        next_field = memory.intent.missing_fields()[0] if memory.intent.missing_fields() else None
        if next_field:
            reply = _get_short_question(next_field, memory.intent, language)
            memory.last_asked_field = _get_field_key(next_field)
        else:
            reply = "Please provide all required information."
        
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply,
            session_id=memory.session_id,
            stage="collecting_info",
            action="continue",
            missing_fields=memory.intent.missing_fields(),
            collected_info=memory.intent.get_summary(),
            chat_mode="agent",
            next_expected=memory.last_asked_field
        )
    
    # Format phone
    phone_country = memory.intent.phone_country or memory.intent.service_country or "India"
    phone = format_phone_for_api(memory.intent.phone, phone_country)
    
    if not phone or not phone.startswith("+"):
        return AgentChatResponse(
            reply="❌ Invalid phone. Please provide with country code (+91, +977, etc.)",
            session_id=memory.session_id,
            stage=memory.stage,
            action="continue",
            missing_fields=["phone number"],
            collected_info=memory.intent.get_summary(),
            chat_mode="agent"
        )
    
    # Show comprehensive summary
    from agent_service import get_comprehensive_summary
    summary_display = get_comprehensive_summary(memory.intent)
    
    confirmation = "🎯 **BOOKING SUMMARY** 🎯\n"
    confirmation += "═══════════════════════════\n"
    confirmation += summary_display
    confirmation += "\n═══════════════════════════"
    confirmation += "\n✅ **All information collected!**"
    confirmation += "\n🔐 **Sending OTP for verification...**"
    
    otp = str(randint(100000, 999999))
    booking_id = secrets.token_urlsafe(16)
    
    TEMP_OTP_STORE[booking_id] = {
        "otp": otp,
        "expires_at": datetime.utcnow() + timedelta(minutes=5),
        "booking_data": create_booking_data(memory),
        "session_id": memory.session_id,
        "phone": phone,  # Store phone for later use
        "language": language  # Store language for later use
    }
    
    try:
        # Send ONLY OTP via WhatsApp (no booking details)
        message_body = f"Your JinniChirag booking OTP is {otp}. Valid for 5 minutes."
        
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{phone}",
            body=message_body
        )
        
        memory.stage = "otp_sent"
        memory.booking_id = booking_id
        memory.last_asked_field = "otp"
        
        phone_display = format_phone_display(memory.intent.phone, phone_country)
        
        # Simple OTP message
        otp_msg = f"✅ I've sent a 6-digit OTP to {phone_display} via WhatsApp.\n\nPlease enter the OTP here to verify your booking:"
        
        final_reply = f"{confirmation}\n\n{otp_msg}"
        
        memory.add_message("assistant", final_reply)
        memory_store.update_memory(memory.session_id, memory)
        
        logger.info(f"✅ OTP sent to {phone} for booking {booking_id[:8]}...")
        
        return AgentChatResponse(
            reply=final_reply,
            session_id=memory.session_id,
            stage=memory.stage,
            action="send_otp",
            missing_fields=[],
            collected_info=memory.intent.get_summary(),
            booking_id=booking_id,
            chat_mode="agent",
            next_expected="otp"
        )
        
    except Exception as e:
        logger.error(f"Failed to send OTP: {e}")
        TEMP_OTP_STORE.pop(booking_id, None)
        
        error_reply = f"{confirmation}\n\n❌ **Failed to send OTP.**\nPlease verify your phone number (+{phone_country}) and try again."
        
        return AgentChatResponse(
            reply=error_reply,
            session_id=memory.session_id,
            stage="collecting_info",
            action="continue",
            missing_fields=["phone number"],
            collected_info=memory.intent.get_summary(),
            chat_mode="agent"
        )

async def _handle_otp_verification(otp_message: str, memory, language: str) -> AgentChatResponse:
    """Handle OTP verification"""
    
    otp_match = re.search(r'\b\d{6}\b', otp_message)
    
    if not otp_match:
        reply = "Please enter the 6-digit OTP."
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
            reply="❌ OTP expired. Please start a new booking.",
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
            reply="⏰ OTP expired (5 min). Please start new booking.",
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
                reply="❌ Too many failed attempts. Start new booking.",
                session_id=memory_store.create_session(language),
                stage="greeting",
                action="reset",
                missing_fields=[],
                collected_info={},
                chat_mode="normal"
            )
        
        reply = f"❌ Wrong OTP. {3 - memory.otp_attempts} attempts left."
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
    
    # OTP VERIFIED - Send booking confirmation via WhatsApp
    booking_data = temp_data["booking_data"]
    booking_data["otp_verified"] = True
    booking_data["verified_at"] = datetime.utcnow()
    
    try:
        result = booking_collection.insert_one(booking_data)
        booking_id_str = str(result.inserted_id)
        
        # Get user details for WhatsApp message
        name = memory.intent.name or "Customer"
        service = memory.intent.service or "Service"
        package = memory.intent.package or "Package"
        date = memory.intent.date or "Date"
        address = memory.intent.address or "Address"
        country = memory.intent.service_country or "India"
        
        # Send booking confirmation via WhatsApp
        booking_whatsapp_message = f"""✅ **Your Booking Request Has Been Successfully Sent to Chirag Sharma!**

📋 **Booking Details:**
• Name: {name}
• Service: {service}
• Package: {package}
• Date: {date}
• Location: {country}
• Address: {address[:100]}...

⏳ **Status:** Pending Admin Approval
Chirag Sharma will review your request and contact you soon for confirmation.

🔔 **Next Steps:**
1. Wait for Chirag's approval (within 24 hours)
2. He will contact you via WhatsApp
3. Payment details will be shared after approval

Thank you for choosing JinniChirag! 💄✨

📞 For urgent queries, contact: +91 81499 92239"""
        
        # Send WhatsApp message
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{temp_data['phone']}",
            body=booking_whatsapp_message
        )
        
        # Clean up OTP store
        TEMP_OTP_STORE.pop(memory.booking_id, None)
        
        logger.info(f"✅ Booking confirmed & WhatsApp sent: {booking_id_str}")
        
        # Get chat confirmation message
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
            booking_id=booking_id_str,
            chat_mode="normal"
        )
        
    except Exception as e:
        logger.error(f"Failed to save booking or send WhatsApp: {e}")
        
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