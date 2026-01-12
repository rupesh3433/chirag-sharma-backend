from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import os
import requests
import logging
from dotenv import load_dotenv
from datetime import datetime

# MongoDB
from pymongo import MongoClient

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

if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY not found. AI will not work.")

if not MONGO_URI:
    logger.error("MONGO_URI not found. Booking system will not work.")

# ----------------------
# App Setup
# ----------------------
app = FastAPI(title="JinniChirag Website Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sharmachirag.vercel.app",  # production frontend
        "http://localhost:5173",            # local dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# MongoDB Setup (NEW)
# ----------------------
mongo_client = None
booking_collection = None

if MONGO_URI:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["jinnichirag_db"]
    booking_collection = db["bookings"]
    logger.info("MongoDB connected successfully")

# ----------------------
# Chatbot Models (EXISTING)
# ----------------------
class Message(BaseModel):
    role: str   # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

# ----------------------
# Booking Models (NEW)
# ----------------------
class BookingRequest(BaseModel):
    service: str
    package: str
    name: str
    email: EmailStr
    phone: str
    date: str
    message: Optional[str] = None

# ----------------------
# Load Website Content
# ----------------------
def load_website_content(folder="content") -> str:
    blocks = []
    if not os.path.exists(folder):
        logger.warning("content/ folder not found")
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
# System Prompt
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
# Chat Endpoint (EXISTING)
# ----------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    if not GROQ_API_KEY:
        return {"reply": "⚠️ AI service is not configured."}

    messages_for_ai = [{"role": "system", "content": SYSTEM_PROMPT}]

    for msg in req.messages:
        messages_for_ai.append({
            "role": msg.role,
            "content": msg.content
        })

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

        if response.status_code != 200:
            logger.error(f"Groq HTTP error: {response.status_code}")
            return {"reply": "⚠️ AI service is temporarily unavailable."}

        data = response.json()

        if "choices" in data and data["choices"]:
            return {"reply": data["choices"][0]["message"]["content"]}

        logger.error("Unexpected Groq response format")
        return {"reply": "⚠️ AI service returned an unexpected response."}

    except requests.exceptions.Timeout:
        logger.error("Groq API timeout")
        return {"reply": "⚠️ AI service timed out."}

    except Exception:
        logger.exception("Internal chatbot error")
        return {"reply": "⚠️ Chatbot is temporarily unavailable."}

# ----------------------
# Booking Endpoint (NEW)
# ----------------------
@app.post("/bookings")
async def create_booking(booking: BookingRequest):
    if booking_collection is None:
        return {"error": "Booking service is not configured."}

    booking_data = booking.dict()
    booking_data["created_at"] = datetime.utcnow()
    booking_data["status"] = "pending"

    booking_collection.insert_one(booking_data)

    return {"message": "Booking submitted successfully"}

# ----------------------
# Health Check
# ----------------------
@app.get("/health")
async def health():
    return {"status": "ok"}
