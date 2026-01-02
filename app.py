from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import os
import requests
from dotenv import load_dotenv

# ----------------------
# Load Environment
# ----------------------
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("❌ ERROR: GROQ_API_KEY not found in .env file")

# ----------------------
# App Setup
# ----------------------
app = FastAPI(title="JinniChirag Website Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev
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
# Load Website Content (TXT files)
# ----------------------
def load_website_content(folder="content"):
    blocks = []
    if not os.path.exists(folder):
        print("⚠️ content/ folder not found")
        return ""
    for file in os.listdir(folder):
        if file.endswith(".txt"):
            with open(os.path.join(folder, file), "r", encoding="utf-8") as f:
                blocks.append(f.read())
    return "\n\n".join(blocks)

WEBSITE_CONTENT = load_website_content()

# ----------------------
# System Prompt
# ----------------------
SYSTEM_PROMPT = f"""
You are the official AI assistant for the website "JinniChirag Makeup Artist".

Rules:
- Answer ONLY from the website content and conversation.
- Allowed topics: services, makeup, booking, Chirag Sharma.
- Be professional, polite, and concise.
- If information is missing, clearly say you don't have it.
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
        return {
            "reply": "⚠️ AI service is not configured properly."
        }

    messages_for_ai = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # Add previous conversation (session memory)
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
                "model": "llama-3.1-8b-instant",  # ✅ supported
                "messages": messages_for_ai,
                "temperature": 0.4,
            },
            timeout=20,
        )

        # ❌ HTTP-level error (401, 429, 500, etc.)
        if response.status_code != 200:
            return {
                "reply": f"⚠️ AI service error (HTTP {response.status_code}). Please try again later."
            }

        # ❌ Invalid JSON
        try:
            data = response.json()
        except Exception:
            return {
                "reply": "⚠️ AI service returned invalid response."
            }

        # ❌ Groq API error object
        if "error" in data:
            return {
                "reply": f"⚠️ AI service error: {data['error'].get('message', 'Unknown error')}"
            }

        # ✅ Success
        if "choices" in data and len(data["choices"]) > 0:
            return {
                "reply": data["choices"][0]["message"]["content"]
            }

        # ❌ Unexpected response format
        return {
            "reply": "⚠️ AI service returned an unexpected response."
        }

    except requests.exceptions.Timeout:
        return {
            "reply": "⚠️ AI service timed out. Please try again."
        }

    except Exception as e:
        print("❌ Internal Error:", e)
        return {
            "reply": "⚠️ Chatbot is temporarily unavailable."
        }

# ----------------------
# Health Check
# ----------------------
@app.get("/health")
async def health():
    return {"status": "ok"}
