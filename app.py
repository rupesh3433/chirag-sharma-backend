from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import os
import requests
import logging
from dotenv import load_dotenv
from datetime import datetime
from random import randint

# MongoDB
from pymongo import MongoClient
from bson import ObjectId

# Twilio
from twilio.rest import Client

# ----------------------
# Basic Logging
# ----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------
# Load Environment
# ----------------------
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")

# ----------------------
# Country → Country Code (PHONE ONLY)
# ----------------------
COUNTRY_CODES = {
    "Nepal": "+977",
    "India": "+91",
    "Pakistan": "+92",
    "Bangladesh": "+880",
    "Dubai": "+971",
}

# ----------------------
# App Setup
# ----------------------
app = FastAPI(title="JinniChirag Website Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sharmachirag.vercel.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# MongoDB Setup
# ----------------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["jinnichirag_db"]
booking_collection = db["bookings"]

# ----------------------
# Twilio Client
# ----------------------
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ----------------------
# Chatbot Models
# ----------------------
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

# ----------------------
# Booking Models (FIXED)
# ----------------------
class BookingRequest(BaseModel):
    service: str
    package: str
    name: str
    email: EmailStr

    phone: str
    phone_country: str          # ✅ NEW (OTP destination)

    service_country: str        # ✅ NEW (booking location)
    address: str
    pincode: str
    date: str

    message: Optional[str] = None

class OtpVerifyRequest(BaseModel):
    booking_id: str
    otp: str

# ----------------------
# Load Website Content
# ----------------------
def load_website_content(folder="content") -> str:
    blocks = []
    if not os.path.exists(folder):
        return ""

    for file in os.listdir(folder):
        if file.endswith(".txt"):
            try:
                with open(os.path.join(folder, file), "r", encoding="utf-8") as f:
                    blocks.append(f.read())
            except Exception as e:
                logger.warning(f"Failed to read {file}: {e}")

    return "\n\n".join(blocks)

WEBSITE_CONTENT = load_website_content()

# ----------------------
# SYSTEM PROMPT (UNCHANGED)
# ----------------------
SYSTEM_PROMPT = f"""
You are the official AI assistant for the website "JinniChirag Makeup Artist".

Rules:
- Answer ONLY using the website content and conversation context.
- Allowed topics: services, makeup, booking, Chirag Sharma.
- Be professional, polite, and concise.
- If information is missing, clearly say you do not have that information.
- NEVER invent prices, experience, or contact details.

Website Content:
{WEBSITE_CONTENT}
"""

# ----------------------
# Chat Endpoint
# ----------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    messages_for_ai = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in req.messages:
        messages_for_ai.append(msg.dict())

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

    data = response.json()
    return {"reply": data["choices"][0]["message"]["content"]}

# ==========================================================
# 🔐 BOOKING WITH WHATSAPP OTP (FIXED LOGIC)
# ==========================================================

@app.post("/bookings/request")
async def request_booking(booking: BookingRequest):

    # ✅ Validate PHONE country (not service country)
    phone_code = COUNTRY_CODES.get(booking.phone_country)
    if not phone_code:
        raise HTTPException(status_code=400, detail="Unsupported phone country")

    if not booking.phone.startswith(phone_code):
        raise HTTPException(
            status_code=400,
            detail=f"Phone number must start with {phone_code}"
        )

    otp = randint(100000, 999999)

    booking_data = booking.dict()
    booking_data.update({
        "otp": otp,
        "otp_verified": False,
        "status": "otp_pending",
        "created_at": datetime.utcnow()
    })

    result = booking_collection.insert_one(booking_data)

    # ✅ Send OTP to WhatsApp number (independent of service country)
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{booking.phone}",
            body=f"Your JinniChirag booking OTP is {otp}"
        )
    except Exception as e:
        logger.error(f"WhatsApp OTP failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to send WhatsApp OTP")

    return {
        "booking_id": str(result.inserted_id),
        "message": "OTP sent via WhatsApp"
    }

@app.post("/bookings/verify-otp")
async def verify_otp(data: OtpVerifyRequest):
    booking = booking_collection.find_one({
        "_id": ObjectId(data.booking_id),
        "otp": int(data.otp)
    })

    if not booking:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    booking_collection.update_one(
        {"_id": booking["_id"]},
        {
            "$set": {
                "otp_verified": True,
                "status": "pending"
            },
            "$unset": {"otp": ""}
        }
    )

    return {"message": "Booking request confirmed"}

# ----------------------
# Health Check
# ----------------------
@app.get("/health")
async def health():
    return {"status": "ok"}
