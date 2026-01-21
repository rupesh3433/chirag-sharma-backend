from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from random import randint
import secrets
import requests
import logging
import re
from models import ChatRequest, BookingRequest, OtpVerifyRequest
from config import GROQ_API_KEY, LANGUAGE_MAP
from database import booking_collection
from services import send_whatsapp_message, twilio_client
from config import TWILIO_WHATSAPP_FROM
from prompts import get_base_system_prompt, get_language_reset_prompt

router = APIRouter()
logger = logging.getLogger(__name__)

# Temporary OTP storage (in-memory)
TEMP_BOOKING_OTPS = {}

# ############################################################
# PUBLIC ROUTES
# ############################################################

@router.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@router.post("/chat")
async def chat(req: ChatRequest):
    """Public chatbot endpoint"""
    
    language_name = LANGUAGE_MAP.get(req.language)
    if not language_name:
        raise HTTPException(status_code=400, detail="Unsupported language")

    language_reset_prompt = get_language_reset_prompt(req.language)

    # Get the base system prompt with knowledge base content
    base_prompt = get_base_system_prompt(req.language)
    
    messages_for_ai = [
        {"role": "system", "content": base_prompt},
        {"role": "system", "content": language_reset_prompt},
    ]

    for msg in req.messages:
        messages_for_ai.append(msg.dict())

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
            },
            timeout=20,
        )
    except Exception as e:
        logger.error(f"GROQ API failure: {e}")
        raise HTTPException(status_code=500, detail="AI service unavailable")

    data = response.json()

    return {
        "reply": data["choices"][0]["message"]["content"]
    }

@router.post("/bookings/request")
async def request_booking(booking: BookingRequest):
    """Send or resend OTP (single booking_id)"""

    if not re.match(r"^\+\d{10,15}$", booking.phone):
        raise HTTPException(400, "Invalid phone number format")

    otp = str(randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    # 🔁 RESEND OTP (reuse SAME booking_id)
    if booking.booking_id:
        if booking.booking_id not in TEMP_BOOKING_OTPS:
            raise HTTPException(400, "Invalid or expired booking request")

        TEMP_BOOKING_OTPS[booking.booking_id] = {
            "otp": otp,
            "expires_at": expires_at,
            "booking_data": booking.dict(exclude={"booking_id"})
        }

        booking_id = booking.booking_id

    # 🆕 FIRST REQUEST
    else:
        booking_id = secrets.token_urlsafe(16)
        TEMP_BOOKING_OTPS[booking_id] = {
            "otp": otp,
            "expires_at": expires_at,
            "booking_data": booking.dict()
        }

    # 📲 Send OTP
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{booking.phone}",
            body=f"Your JinniChirag booking OTP is {otp}"
        )
    except Exception:
        TEMP_BOOKING_OTPS.pop(booking_id, None)
        raise HTTPException(500, "Failed to send WhatsApp OTP")

    return {
        "booking_id": booking_id,
        "message": "OTP sent via WhatsApp"
    }

@router.post("/bookings/verify-otp")
async def verify_otp(data: OtpVerifyRequest):
    """Verify OTP and create booking"""
    temp = TEMP_BOOKING_OTPS.get(data.booking_id)

    if not temp:
        raise HTTPException(400, "Invalid or expired booking request")

    if datetime.utcnow() > temp["expires_at"]:
        TEMP_BOOKING_OTPS.pop(data.booking_id, None)
        raise HTTPException(400, "OTP expired")

    if data.otp != temp["otp"]:
        raise HTTPException(400, "Invalid OTP")

    # ✅ OTP VERIFIED → SAVE TO DB
    booking_data = temp["booking_data"]
    booking_data.update({
        "status": "pending",
        "otp_verified": True,
        "created_at": datetime.utcnow()
    })

    result = booking_collection.insert_one(booking_data)

    TEMP_BOOKING_OTPS.pop(data.booking_id, None)

    return {
        "message": "Booking confirmed",
        "booking_id": str(result.inserted_id)
    }