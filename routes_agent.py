from fastapi import APIRouter, HTTPException
import logging
import requests
from datetime import datetime, timedelta
from random import randint
import secrets
import re

from agent_models import AgentChatRequest, AgentChatResponse, BookingIntent
from agent_fsm import booking_fsm, BookingState
from agent_service import format_phone_for_api, format_phone_display, create_booking_data, validate_phone_with_country_code
from agent_prompts import get_booking_confirmed_message, get_phone_prompt, get_country_inquiry_prompt
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
    """STRICT PROMPT COMPLIANCE"""

    logger.info(f"=== AGENT CHAT REQUEST ===")
    logger.info(f"Session ID: {req.session_id}")
    logger.info(f"Language: {req.language}")
    logger.info(f"Message: '{req.message[:100]}'")
    logger.info(f"Message length: {len(req.message)}")
    
    if req.language not in ["en", "ne", "hi", "mr"]:
        raise HTTPException(400, "Unsupported language")
    
    rate_limit_key = req.session_id or "anonymous"
    if not rate_limiter.check_rate_limit(rate_limit_key):
        remaining_time = int(rate_limiter.get_reset_time(rate_limit_key))
        raise HTTPException(429, f"Too many requests. Please wait {remaining_time} seconds.")
    
    memory = memory_store.get_memory(req.session_id) if req.session_id else None
    if not memory:
        session_id = memory_store.create_session(req.language)
        memory = memory_store.get_memory(session_id)
    
    msg_lower = req.message.lower().strip()
    
    exit_keywords = ["exit booking", "cancel booking", "stop booking", "exit", "cancel", "quit"]
    
    if any(keyword in msg_lower for keyword in exit_keywords):
        if memory.stage != BookingState.GREETING.value:
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
    
    if "restart" in msg_lower or "start over" in msg_lower:
        memory_store.reset_memory(memory.session_id)
        memory = memory_store.get_memory(memory.session_id)
        
        reply = "🔄 No problem! Let's start fresh.\n\nWhich service?\n\n1. Bridal Makeup\n2. Party Makeup\n3. Engagement & Pre-Wedding\n4. Henna/Mehendi"
        memory.add_message("user", req.message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply, 
            session_id=memory.session_id, 
            stage=BookingState.SELECTING_SERVICE.value, 
            action="continue", 
            missing_fields=memory.intent.missing_fields(), 
            collected_info={}, 
            chat_mode="agent"
        )
    
    current_state = memory.stage
    
    if _is_question_during_booking(req.message, current_state, memory.intent):
        return await _handle_question_during_booking(req.message, memory, req.language)
    
    logger.info(f"🎯 FSM: {current_state} | Last shown: {memory.last_shown_list} | '{req.message[:50]}'")
    
    try:
        next_state, updated_intent, metadata = booking_fsm.process_message(
            req.message, 
            current_state, 
            memory.intent, 
            req.language, 
            memory.conversation_history
        )
    except Exception as e:
        logger.error(f"FSM processing error: {e}")
        memory_store.reset_memory(memory.session_id)
        memory = memory_store.get_memory(memory.session_id)
        return AgentChatResponse(
            reply="⚠️ Something went wrong. Let's start over. How can I help?", 
            session_id=memory.session_id, 
            stage=memory.stage, 
            action="reset", 
            missing_fields=[], 
            collected_info={}, 
            chat_mode="normal"
        )
    
    logger.info(f"✅ Next: {next_state} | Action: {metadata.get('action')} | Mode: {metadata.get('mode', 'unknown')}")
    
    if hasattr(booking_fsm, 'last_shown_list'):
        memory.last_shown_list = booking_fsm.last_shown_list
    
    memory.intent = updated_intent
    memory.stage = next_state
    
    action = metadata.get("action")
    mode = metadata.get("mode", "unknown")
    
    if action == "provide_info":
        return await _handle_info_mode(req.message, memory, req.language)
    elif action == "general_chat":
        return await _handle_general_chat(req.message, memory, req.language)
    elif action == "send_otp":
        return await _send_otp(memory, req.language)
    elif action == "verify_otp":
        otp_value = metadata.get("otp")
        if not otp_value:
            otp_match = re.search(r'\b(\d{6})\b', req.message)
            otp_value = otp_match.group(1) if otp_match else None
        return await _verify_otp(otp_value, memory, req.language)
    elif action == "ask_country":
        reply = get_country_inquiry_prompt(req.language)
        
        memory.add_message("user", req.message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply, 
            session_id=memory.session_id, 
            stage=next_state, 
            action="continue", 
            missing_fields=memory.intent.missing_fields(), 
            collected_info=memory.intent.get_summary(), 
            chat_mode="agent"
        )
    elif action == "ask_details":
        reply = metadata.get("message", "")
        if not reply:
            missing = memory.intent.missing_fields()
            if missing:
                if "phone number with country code" in missing:
                    reply = get_phone_prompt(req.language)
                else:
                    reply = f"📝 Please provide: {', '.join(missing[:3])}"
            else:
                reply = "Please continue..."
        
        memory.add_message("user", req.message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply, 
            session_id=memory.session_id, 
            stage=next_state, 
            action="continue", 
            missing_fields=memory.intent.missing_fields(), 
            collected_info=memory.intent.get_summary(), 
            chat_mode="agent"
        )
    elif action == "retry":
        reply = metadata.get("message", "Please try again.")
        
        memory.add_message("user", req.message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply, 
            session_id=memory.session_id, 
            stage=next_state, 
            action="continue", 
            missing_fields=memory.intent.missing_fields(), 
            collected_info=memory.intent.get_summary(), 
            chat_mode="agent"
        )
    elif action == "restart":
        memory_store.reset_memory(memory.session_id)
        memory = memory_store.get_memory(memory.session_id)
        
        reply = metadata.get("message", "🔄 Let's start over.")
        memory.add_message("user", req.message)
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply, 
            session_id=memory.session_id, 
            stage=next_state, 
            action="continue", 
            missing_fields=memory.intent.missing_fields(), 
            collected_info={}, 
            chat_mode="agent"
        )
    else:
        reply = metadata.get("message", "")
        
        if metadata.get("collected"):
            ack_lines = []
            for k, v in metadata["collected"].items():
                if "phone" in k.lower() and v and isinstance(v, str) and v.startswith('+'):
                    phone_display = format_phone_display(v)
                    ack_lines.append(f"✅ {k}: {phone_display}")
                else:
                    ack_lines.append(f"✅ {k}: {v}")
            
            if ack_lines:
                ack_text = "\n".join(ack_lines)
                if reply and "✅" not in reply:
                    reply = f"{ack_text}\n\n{reply}"
                elif not reply:
                    reply = ack_text
        
        memory.add_message("user", req.message)
        if reply:
            memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        if mode == "booking" or next_state not in [BookingState.GREETING.value, BookingState.INFO_MODE.value]:
            chat_mode = "agent"
        else:
            chat_mode = "normal"
        
        return AgentChatResponse(
            reply=reply if reply else "Please continue...", 
            session_id=memory.session_id, 
            stage=next_state, 
            action=action, 
            missing_fields=memory.intent.missing_fields(), 
            collected_info=memory.intent.get_summary(), 
            chat_mode=chat_mode,
            next_expected=_get_next_expected_prompt(next_state, memory.intent, req.language)
        )

def _is_question_during_booking(message: str, state: str, intent: BookingIntent) -> bool:
    """Detect question during booking - FIXED to allow numeric selections"""
    
    booking_states = [
        BookingState.SELECTING_SERVICE.value, 
        BookingState.SELECTING_PACKAGE.value, 
        BookingState.COLLECTING_DETAILS.value,
        BookingState.CONFIRMING.value,
        BookingState.OTP_SENT.value
    ]
    
    if state not in booking_states:
        return False
    
    msg_lower = message.lower().strip()
    
    # ALLOW numeric selections (1, 2, 3, 4) - they are NOT questions
    if re.match(r'^[1-4]$', msg_lower):
        return False
    
    # ALLOW "go for 1", "choose 1", "select 1" - these are selections, not questions
    selection_patterns = [
        r'go for \d', r'choose \d', r'select \d', r'pick \d', 
        r'option \d', r'take \d', r'\d please', r'number \d'
    ]
    
    if any(re.search(pattern, msg_lower) for pattern in selection_patterns):
        return False
    
    # Now check for actual questions
    question_indicators = ["what", "which", "how", "why", "when", "where", 
                          "tell me", "show me", "explain", "describe", 
                          "include", "what's", "?", "details", "info",
                          "can you", "could you", "would you", "is there",
                          "are there", "do you", "does it"]
    
    has_question = any(ind in msg_lower for ind in question_indicators)
    
    # Check for info patterns (name, phone, email, etc.)
    info_patterns = [
        r'\b\d{10}\b', r'@\w+\.\w+', r'\d{5,6}', r'\+\d{1,3}',
        r'name[:\s]', r'phone[:\s]', r'email[:\s]', r'address[:\s]',
        r'pincode[:\s]', r'pin[:\s]', r'postal[:\s]', r'zip[:\s]',
        r'date[:\s]', r'today', r'tomorrow', r'\d{1,2}[\s\-\./]\d{1,2}[\s\-\./]\d{4}'
    ]
    
    has_info = any(re.search(pattern, message, re.IGNORECASE) for pattern in info_patterns)
    
    confirmation_words = ['yes', 'no', 'confirm', 'cancel', 'correct', 'wrong', 'ok', 'okay']
    has_confirmation = any(word in msg_lower for word in confirmation_words)
    
    # If it has question words BUT also has info OR is a confirmation, it's not a pure question
    if has_question and (has_info or has_confirmation):
        return False
    
    # If it's just a question with no info/confirmation
    return has_question and not has_info and not has_confirmation

async def _handle_question_during_booking(message: str, memory, language: str) -> AgentChatResponse:
    """Answer question then continue"""
    
    answer = await _get_concise_answer(message, memory, language)
    
    next_prompt = _get_next_expected_prompt(memory.stage, memory.intent, language)
    
    if next_prompt:
        reply = f"{answer}\n\n{next_prompt}"
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
        missing_fields=memory.intent.missing_fields(), 
        collected_info=memory.intent.get_summary(), 
        chat_mode="agent"
    )

async def _handle_info_mode(message: str, memory, language: str) -> AgentChatResponse:
    """Info mode - answer with soft CTA - FIXED for numeric selections"""
    
    msg_lower = message.lower().strip()
    
    # CHECK FOR NUMERIC SELECTIONS FIRST (like "go for 1", "choose 1", or just "1")
    # These should trigger booking mode, not info mode
    
    # Check for single digit selections (1, 2, 3, 4)
    single_digit_match = re.match(r'^[1-4]$', msg_lower)
    
    # Check for selection phrases
    selection_patterns = [
        r'go for \d', r'choose \d', r'select \d', r'pick \d', 
        r'option \d', r'take \d', r'\d please', r'number \d',
        r'want \d', r'need \d', r'book \d', r'booking \d'
    ]
    
    is_selection = (
        single_digit_match or 
        any(re.search(pattern, msg_lower) for pattern in selection_patterns)
    )
    
    # Check if we're in a context where numeric selection makes sense
    context_has_services = memory.last_shown_list == "services"
    context_has_packages = memory.last_shown_list == "packages"
    
    # If it's a numeric selection AND we have context, treat it as booking intent
    if is_selection and (context_has_services or context_has_packages):
        logger.info(f"🔀 INFO MODE: Detected selection '{message}' in context {memory.last_shown_list}")
        
        try:
            # Process through booking FSM
            next_state, updated_intent, metadata = booking_fsm.process_message(
                message, 
                BookingState.SELECTING_SERVICE.value if context_has_services else BookingState.SELECTING_PACKAGE.value,
                memory.intent, 
                language, 
                memory.conversation_history
            )
            
            # Update memory
            memory.intent = updated_intent
            memory.stage = next_state
            
            if hasattr(booking_fsm, 'last_shown_list'):
                memory.last_shown_list = booking_fsm.last_shown_list
            
            reply = metadata.get("message", "")
            action = metadata.get("action", "continue")
            mode = metadata.get("mode", "unknown")
            
            memory.add_message("user", message)
            memory.add_message("assistant", reply)
            memory_store.update_memory(memory.session_id, memory)
            
            # Determine chat mode
            if mode == "booking" or next_state not in [BookingState.GREETING.value, BookingState.INFO_MODE.value]:
                chat_mode = "agent"
            else:
                chat_mode = "normal"
            
            return AgentChatResponse(
                reply=reply, 
                session_id=memory.session_id, 
                stage=next_state, 
                action=action, 
                missing_fields=updated_intent.missing_fields(), 
                collected_info=updated_intent.get_summary(), 
                chat_mode=chat_mode
            )
            
        except Exception as e:
            logger.error(f"FSM processing failed for selection: {e}")
            # Fall through to regular info handling
    
    # REGULAR INFO QUERY HANDLING (original logic with improvements)
    kb_prompt = get_base_system_prompt(language)
    
    context_note = ""
    if memory.last_shown_list == "services":
        context_note = "IMPORTANT: If user says '1' or 'go for 1', they want to BOOK service #1. Respond with: 'Great! Would you like to book Bridal Makeup Services? Say \"book\" to start.'"
    elif memory.last_shown_list == "packages" and memory.intent.service:
        context_note = f"IMPORTANT: If user says '1' or 'choose 1', they want to BOOK package #1 for {memory.intent.service}. Respond with: 'Great choice! Say \"book\" to proceed with this package.'"
    
    messages = [
        {"role": "system", "content": kb_prompt}, 
        {"role": "system", "content": f"""You are JinniChirag AI. User is asking for INFORMATION (not booking yet).

RESPONSE RULES (VERY IMPORTANT):
1. Answer their question BRIEFLY (2-4 sentences max)
2. If listing services/packages, use simple format: • Service Name (Price range)
3. NO lengthy descriptions
4. END with soft CTA: "Would you like to book [service name]?" OR "Say 'book' to proceed."
5. Be warm but concise
6. {context_note}

Language: {language.upper()}"""}, 
        {"role": "user", "content": message}
    ]
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions", 
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}", 
                "Content-Type": "application/json"
            }, 
            json={
                "model": "llama-3.1-8b-instant", 
                "messages": messages, 
                "temperature": 0.4, 
                "max_tokens": 300
            }, 
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and data["choices"]:
                reply = data["choices"][0]["message"]["content"]
            else:
                reply = "I can help with that! Say 'book' when ready to make a reservation."
        else:
            reply = "I can help with that! Say 'book' when ready to make a reservation."
    
    except Exception as e:
        logger.error(f"LLM error: {e}")
        reply = "I can help with that! Say 'book' when ready to make a reservation."
    
    memory.add_message("user", message)
    memory.add_message("assistant", reply)
    memory_store.update_memory(memory.session_id, memory)
    
    return AgentChatResponse(
        reply=reply, 
        session_id=memory.session_id, 
        stage=BookingState.INFO_MODE.value, 
        action="continue", 
        missing_fields=[], 
        collected_info={}, 
        chat_mode="normal"
    )

async def _handle_general_chat(message: str, memory, language: str) -> AgentChatResponse:
    """General chat"""
    
    kb_prompt = get_base_system_prompt(language)
    
    last_assistant_msg = ""
    for msg in reversed(memory.conversation_history):
        if msg["role"] == "assistant":
            last_assistant_msg = msg["content"]
            break
    
    context_note = ""
    if memory.last_shown_list == "services" or "1. Bridal" in last_assistant_msg:
        context_note = "\nIMPORTANT: If user says '1' or 'go for 1', they want to BOOK service #1. Respond with: 'Great! Would you like to book Bridal Makeup Services? Say \"book\" to start.'"
    elif memory.last_shown_list == "packages" and memory.intent.service:
        context_note = f"\nIMPORTANT: If user says '1' or 'choose 1', they want to BOOK package #1 for {memory.intent.service}. Respond with: 'Great choice! Say \"book\" to proceed with this package.'"
    
    messages = [
        {"role": "system", "content": kb_prompt}, 
        {"role": "system", "content": f"""You are JinniChirag AI assistant. Language: {language.upper()}

RULES:
- Keep SHORT (3-5 sentences)
- Be warm and professional
- If user shows interest in services, suggest booking: "Say 'book' to reserve!"
- NO bullet points unless listing services{context_note}"""}
    ]
    
    for msg in memory.conversation_history[-3:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    messages.append({"role": "user", "content": message})
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions", 
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}", 
                "Content-Type": "application/json"
            }, 
            json={
                "model": "llama-3.1-8b-instant", 
                "messages": messages, 
                "temperature": 0.4, 
                "max_tokens": 250
            }, 
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and data["choices"]:
                reply = data["choices"][0]["message"]["content"]
            else:
                reply = "I'm here to help! Ask about services or say 'book' to reserve."
        else:
            reply = "I'm here to help! Ask about services or say 'book' to reserve."
    
    except Exception as e:
        logger.error(f"LLM error: {e}")
        reply = "I'm here to help! Ask about services or say 'book' to reserve."
    
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

async def _get_concise_answer(message: str, memory, language: str) -> str:
    """Get brief answer to question during booking"""
    
    kb_prompt = get_base_system_prompt(language)
    
    current_stage = memory.stage
    service = memory.intent.service
    package = memory.intent.package
    
    context_info = f"Current stage: {current_stage}"
    if service:
        context_info += f", Selected service: {service}"
    if package:
        context_info += f", Selected package: {package}"
    
    messages = [
        {"role": "system", "content": kb_prompt}, 
        {"role": "system", "content": f"""Answer BRIEFLY (2-3 sentences max). User is in booking process, so be CONCISE and return to booking.

{context_info}
Language: {language.upper()}
Just answer what was asked, nothing more. End with "Now back to your booking..." or similar."""}, 
        {"role": "user", "content": message}
    ]
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions", 
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}", 
                "Content-Type": "application/json"
            }, 
            json={
                "model": "llama-3.1-8b-instant", 
                "messages": messages, 
                "temperature": 0.3, 
                "max_tokens": 150
            }, 
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and data["choices"]:
                answer = data["choices"][0]["message"]["content"].strip()
                if not any(phrase in answer.lower() for phrase in ["back to", "continue with", "proceed with", "now,"]):
                    answer += "\n\nNow back to your booking..."
                return answer
    except Exception as e:
        logger.error(f"LLM error: {e}")
    
    return "Sure, continuing with your booking..."

def _get_next_expected_prompt(state: str, intent: BookingIntent, language: str) -> str:
    """Get appropriate prompt for current state"""
    
    if state == BookingState.SELECTING_SERVICE.value:
        return "🎯 **Please choose a service (1-4 or name):**\n\n1. Bridal Makeup Services\n2. Party Makeup Services\n3. Engagement & Pre-Wedding Makeup\n4. Henna (Mehendi) Services"
    
    elif state == BookingState.SELECTING_PACKAGE.value and intent.service:
        from agent_fsm import booking_fsm
        return booking_fsm._get_package_prompt(intent.service, language)
    
    elif state == BookingState.COLLECTING_DETAILS.value:
        missing = intent.missing_fields()
        if missing:
            if "phone number with country code" in missing:
                from agent_prompts import get_phone_prompt
                return get_phone_prompt(language)
            
            if len(missing) == 1:
                field = missing[0]
                if "name" in field:
                    return "👤 What's your full name?"
                elif "email" in field:
                    return "📧 What's your email address?"
                elif "date" in field:
                    return "📅 When is the event? (e.g., 5 Feb 2026, tomorrow)"
                elif "address" in field:
                    return "📍 What's the event address?"
                elif "pincode" in field or "PIN" in field:
                    return "📮 What's the PIN/postal code?"
                elif "country" in field:
                    from agent_prompts import get_country_inquiry_prompt
                    return get_country_inquiry_prompt(language)
            
            return f"📝 Please provide: {', '.join(missing[:3])}"
        
        return "Please continue..."
    
    elif state == BookingState.CONFIRMING.value:
        from agent_fsm import booking_fsm
        return booking_fsm._get_confirmation_prompt(intent, language)
    
    elif state == BookingState.OTP_SENT.value:
        return "🔢 Please enter the 6-digit OTP sent to your WhatsApp:"
    
    return ""

async def _send_otp(memory, language: str) -> AgentChatResponse:
    """Send OTP - FIXED with better phone validation"""
    
    if not memory.intent.is_complete():
        missing = memory.intent.missing_fields()
        reply = f"❌ Missing information: {', '.join(missing)}\n\nPlease provide the missing details."
        
        memory.stage = BookingState.COLLECTING_DETAILS.value
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
    
    if not memory.intent.phone:
        reply = "❌ Phone number is required. Please provide your WhatsApp number with country code."
        memory.stage = BookingState.COLLECTING_DETAILS.value
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply, 
            session_id=memory.session_id, 
            stage=memory.stage, 
            action="continue", 
            missing_fields=["phone number with country code"], 
            collected_info=memory.intent.get_summary(), 
            chat_mode="agent"
        )
    
    # Log the phone number for debugging
    logger.info(f"📱 Validating phone: {memory.intent.phone}")
    
    # FIX: Direct validation for common Indian format +91XXXXXXXXXX
    phone = memory.intent.phone.strip()
    
    # Quick check: If phone starts with +91 and has 12 digits total (+91 + 10 digits)
    if phone.startswith('+91'):
        digits_after_plus = re.sub(r'\D', '', phone[1:])  # Remove + first
        total_digits = len(digits_after_plus)
        
        if total_digits == 12:  # +91 (2) + 10 = 12
            # This is a valid Indian number format
            validated_phone = phone
            phone_country = "India"
            logger.info(f"✅ Valid Indian number: {validated_phone}")
            
            # Skip the validate_phone_with_country_code call and proceed
            # to OTP sending
            pass
        else:
            # Invalid length
            reply = f"❌ Indian number should have 10 digits after +91 (got {total_digits - 2} digits)\n\nFormat: +91-9876543210"
            memory.stage = BookingState.COLLECTING_DETAILS.value
            memory.add_message("assistant", reply)
            memory_store.update_memory(memory.session_id, memory)
            
            return AgentChatResponse(
                reply=reply, 
                session_id=memory.session_id, 
                stage=memory.stage, 
                action="continue", 
                missing_fields=["phone number with country code"], 
                collected_info=memory.intent.get_summary(), 
                chat_mode="agent"
            )
    else:
        # For non-Indian numbers, use the validation function
        phone_validation = validate_phone_with_country_code(memory.intent.phone)
        if not phone_validation["valid"]:
            # Show better error message
            error_msg = phone_validation.get('error', 'Invalid phone number')
            suggestion = phone_validation.get('suggestion', 'Please provide with country code like +91-9876543210')
            
            reply = f"❌ {error_msg}\n\n{suggestion}"
            memory.stage = BookingState.COLLECTING_DETAILS.value
            memory.add_message("assistant", reply)
            memory_store.update_memory(memory.session_id, memory)
            
            return AgentChatResponse(
                reply=reply, 
                session_id=memory.session_id, 
                stage=memory.stage, 
                action="continue", 
                missing_fields=["phone number with country code"], 
                collected_info=memory.intent.get_summary(), 
                chat_mode="agent"
            )
        
        validated_phone = phone_validation["phone"]
        phone_country = phone_validation.get("country", memory.intent.service_country or "India")
    
    # Generate OTP and booking ID
    otp = str(randint(100000, 999999))
    booking_id = secrets.token_urlsafe(16)
    
    TEMP_OTP_STORE[booking_id] = {
        "otp": otp, 
        "expires_at": datetime.utcnow() + timedelta(minutes=5), 
        "booking_data": create_booking_data(memory), 
        "session_id": memory.session_id, 
        "phone": validated_phone, 
        "language": language,
        "phone_country": phone_country
    }
    
    try:
        # Format phone for WhatsApp (ensure proper format)
        whatsapp_phone = validated_phone
        if not whatsapp_phone.startswith('whatsapp:'):
            whatsapp_phone = f"whatsapp:{validated_phone}"
        
        logger.info(f"📲 Sending OTP to: {whatsapp_phone}")
        
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM, 
            to=whatsapp_phone, 
            body=f"Your JinniChirag booking OTP is {otp}. Valid for 5 minutes."
        )
        
        memory.stage = BookingState.OTP_SENT.value
        memory.booking_id = booking_id
        
        phone_display = format_phone_display(validated_phone)
        
        summary = f"""✅ **All details verified!**

📲 OTP has been sent to {phone_display} via WhatsApp.

🔢 **Please enter the 6-digit OTP to confirm your booking:**

(OTP expires in 5 minutes)"""
        
        memory.add_message("assistant", summary)
        memory_store.update_memory(memory.session_id, memory)
        
        logger.info(f"✅ OTP sent successfully to {validated_phone}")
        
        return AgentChatResponse(
            reply=summary, 
            session_id=memory.session_id, 
            stage=memory.stage, 
            action="send_otp", 
            missing_fields=[], 
            collected_info=memory.intent.get_summary(), 
            booking_id=booking_id, 
            chat_mode="agent"
        )
        
    except Exception as e:
        logger.error(f"OTP send failed: {e}")
        TEMP_OTP_STORE.pop(booking_id, None)
        
        # Check if it's a Twilio validation error
        if "not a valid phone number" in str(e).lower():
            reply = f"❌ Twilio validation failed: {validated_phone}\n\nPlease provide a valid WhatsApp-enabled number with country code."
        else:
            reply = f"❌ Failed to send OTP: {str(e)}\n\nPlease verify your phone number and try again."
        
        memory.stage = BookingState.COLLECTING_DETAILS.value
        memory.add_message("assistant", reply)
        memory_store.update_memory(memory.session_id, memory)
        
        return AgentChatResponse(
            reply=reply, 
            session_id=memory.session_id, 
            stage=memory.stage, 
            action="continue", 
            missing_fields=["phone number"], 
            collected_info=memory.intent.get_summary(), 
            chat_mode="agent"
        )

async def _verify_otp(otp: str, memory, language: str) -> AgentChatResponse:
    """Verify OTP"""
    
    if not otp:
        reply = "❌ Please enter the 6-digit OTP."
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
    
    temp_data = TEMP_OTP_STORE.get(memory.booking_id)
    
    if not temp_data:
        memory_store.delete_memory(memory.session_id)
        return AgentChatResponse(
            reply="❌ OTP expired. Please start a new booking.", 
            session_id=memory_store.create_session(language), 
            stage=BookingState.GREETING.value, 
            action="reset", 
            missing_fields=[], 
            collected_info={}, 
            chat_mode="normal"
        )
    
    if datetime.utcnow() > temp_data["expires_at"]:
        TEMP_OTP_STORE.pop(memory.booking_id, None)
        memory_store.delete_memory(memory.session_id)
        
        return AgentChatResponse(
            reply="⏰ OTP expired (5 minutes). Please start new booking.", 
            session_id=memory_store.create_session(language), 
            stage=BookingState.GREETING.value, 
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
                stage=BookingState.GREETING.value, 
                action="reset", 
                missing_fields=[], 
                collected_info={}, 
                chat_mode="normal"
            )
        
        attempts_left = 3 - memory.otp_attempts
        reply = f"❌ Wrong OTP. {attempts_left} attempt{'s' if attempts_left > 1 else ''} left."
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
    
    booking_data = temp_data["booking_data"]
    booking_data["otp_verified"] = True
    booking_data["verified_at"] = datetime.utcnow()
    booking_data["otp"] = otp
    
    try:
        result = booking_collection.insert_one(booking_data)
        booking_id_str = str(result.inserted_id)
        
        name = memory.intent.name
        service = memory.intent.service
        package = memory.intent.package
        date = memory.intent.date
        country = memory.intent.service_country or "India"
        
        whatsapp_msg = f"""✅ **Booking Request Sent to Chirag Sharma!**

📋 **Details:**
• Name: {name}
• Service: {service}
• Package: {package}
• Date: {date}
• Location: {country}

⏳ **Status:** Pending Approval
Chirag will review and contact you within 24 hours via WhatsApp.

Thank you for choosing JinniChirag! 💄✨"""
        
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM, 
            to=f"whatsapp:{temp_data['phone']}", 
            body=whatsapp_msg
        )
        
        TEMP_OTP_STORE.pop(memory.booking_id, None)
        logger.info(f"✅ Booking confirmed: {booking_id_str}")
        
        success_msg = get_booking_confirmed_message(language, name)
        
        booking_id_for_response = booking_id_str
        
        memory_store.delete_memory(memory.session_id)
        
        return AgentChatResponse(
            reply=success_msg, 
            session_id=memory_store.create_session(language), 
            stage=BookingState.GREETING.value, 
            action="booking_confirmed", 
            missing_fields=[], 
            collected_info={}, 
            booking_id=booking_id_for_response, 
            chat_mode="normal"
        )
        
    except Exception as e:
        logger.error(f"Booking save failed: {e}")
        
        reply = f"❌ Failed to save booking: {str(e)}\n\nPlease contact support."
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