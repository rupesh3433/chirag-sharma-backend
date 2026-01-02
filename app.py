from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import os
import requests
import logging
from dotenv import load_dotenv

# ----------------------
# Basic Logging
# ----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------
# Load Environment (local only; Render uses dashboard vars)
# ----------------------
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY not found. AI will not work.")

# ----------------------
# App Setup
# ----------------------
app = FastAPI(title="JinniChirag Website Chatbot")

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
# Models
# ----------------------
class Message(BaseModel):
    role: str   # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

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
# Chat Endpoint
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
            return {
                "reply": "⚠️ AI service is temporarily unavailable. Please try again."
            }

        try:
            data = response.json()
        except Exception:
            logger.error("Invalid JSON from Groq API")
            return {
                "reply": "⚠️ AI service returned an invalid response."
            }

        if "error" in data:
            logger.error(f"Groq API error: {data['error']}")
            return {
                "reply": "⚠️ AI service encountered an error."
            }

        if data.get("choices"):
            return {
                "reply": data["choices"][0]["message"]["content"]
            }

        logger.error("Unexpected Groq response format")
        return {
            "reply": "⚠️ AI service returned an unexpected response."
        }

    except requests.exceptions.Timeout:
        logger.error("Groq API timeout")
        return {
            "reply": "⚠️ AI service timed out. Please try again."
        }

    except Exception as e:
        logger.exception("Internal chatbot error")
        return {
            "reply": "⚠️ Chatbot is temporarily unavailable."
        }

# ----------------------
# Health Check
# ----------------------
@app.get("/health")
async def health():
    return {"status": "ok"}
