from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional
import os
import requests
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
from random import randint
import secrets
import jwt
import bcrypt

from pymongo import MongoClient
from bson import ObjectId
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
JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-jwt-key-change-this")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")

# Email configuration for password reset
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Brevo API (for environments that block SMTP)
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

# Frontend URL for Admin-Panel
FRONTEND_URL = os.getenv("FRONTEND_URL")

# ----------------------
# Permanent Admins (Auto-create on first reset)
# ----------------------
PERMANENT_ADMINS = {
    "poudelrupace@gmail.com",
    "jinni.chirag.mua101@gmail.com",
}

# ----------------------
# Country Codes
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
        "https://sharmachiragadmin.vercel.app",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# MongoDB
# ----------------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["jinnichirag_db"]
booking_collection = db["bookings"]
admin_collection = db["admins"]
reset_token_collection = db["reset_tokens"]

# Create indexes for better performance
reset_token_collection.create_index("expires_at", expireAfterSeconds=0)
admin_collection.create_index("email", unique=True)
booking_collection.create_index("created_at")
booking_collection.create_index("status")

# ----------------------
# Twilio
# ----------------------
try:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
except Exception as e:
    logger.warning(f"Twilio client initialization failed: {e}")
    twilio_client = None

# ----------------------
# Security (FIXED: auto_error=False to allow unauthenticated routes)
# ----------------------
security = HTTPBearer(auto_error=False)

# ==========================================================
# MODELS - PUBLIC
# ==========================================================

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    language: str  # en | ne | hi | mr

class BookingRequest(BaseModel):
    service: str
    package: str
    name: str
    email: EmailStr
    phone: str
    phone_country: str
    service_country: str
    address: str
    pincode: str
    date: str
    message: Optional[str] = None

class OtpVerifyRequest(BaseModel):
    booking_id: str
    otp: str

# ==========================================================
# MODELS - ADMIN ONLY
# ==========================================================

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str

class AdminPasswordResetRequest(BaseModel):
    email: EmailStr

class AdminPasswordResetConfirm(BaseModel):
    token: str
    new_password: str
    
    @validator('new_password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v

class BookingStatusUpdate(BaseModel):
    status: str
    
    @validator('status')
    def valid_status(cls, v):
        allowed = ['pending', 'completed', 'cancelled']
        if v not in allowed:
            raise ValueError(f'Status must be one of {allowed}')
        return v

class BookingSearchQuery(BaseModel):
    search: Optional[str] = None
    status: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 50
    skip: int = 0

# ==========================================================
# UTILITY FUNCTIONS
# ==========================================================

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_jwt_token(email: str, role: str) -> str:
    """Create JWT token for admin"""
    payload = {
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token: str) -> dict:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_admin(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """Dependency to get current authenticated admin"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = credentials.credentials
    payload = verify_jwt_token(token)
    
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    admin = admin_collection.find_one({"email": payload["email"]})
    if not admin:
        raise HTTPException(status_code=403, detail="Admin not found")
    
    return {
        "email": admin["email"],
        "role": admin["role"]
    }

def send_password_reset_email(email: str, token: str):
    """Send password reset email via Brevo API or SMTP"""
    
    if not FRONTEND_URL:
        logger.error("FRONTEND_URL not configured")
        raise Exception("FRONTEND_URL not configured")

    reset_link = f"{FRONTEND_URL}/admin/reset-password?token={token}"
    
    # Try Brevo API first (works on Render), fallback to SMTP (for local dev)
    if BREVO_API_KEY:
        try:
            response = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "accept": "application/json",
                    "api-key": BREVO_API_KEY,
                    "content-type": "application/json"
                },
                json={
                    "sender": {"name": "JinniChirag Admin", "email": "poudelrupace@gmail.com"},
                    "to": [{"email": email}],
                    "subject": "JinniChirag Admin - Password Reset",
                    "htmlContent": f"""
                        <html>
                          <body>
                            <h2>Password Reset Request</h2>
                            <p>You requested to reset your password for JinniChirag Admin Panel.</p>
                            <p>Click the link below to reset your password:</p>
                            <p><a href="{reset_link}">Reset Password</a></p>
                            <p>This link will expire in 1 hour.</p>
                            <p>If you didn't request this, please ignore this email.</p>
                            <br>
                            <p>- JinniChirag Team</p>
                          </body>
                        </html>
                    """
                },
                timeout=10
            )
            if response.status_code == 201:
                logger.info(f"Password reset email sent to {email} via Brevo API")
                return
            else:
                logger.error(f"Brevo API failed: {response.status_code} - {response.text}")
                raise Exception("Brevo API failed")
        except Exception as e:
            logger.error(f"Brevo API error: {e}")
            raise
    
    # Fallback to SMTP for local development
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        logger.error("Neither Brevo API nor SMTP credentials configured")
        raise Exception("Email service not configured")
    
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    message = MIMEMultipart("alternative")
    message["Subject"] = "JinniChirag Admin - Password Reset"
    message["From"] = SMTP_EMAIL
    message["To"] = email
    
    html = f"""
    <html>
      <body>
        <h2>Password Reset Request</h2>
        <p>You requested to reset your password for JinniChirag Admin Panel.</p>
        <p>Click the link below to reset your password:</p>
        <p><a href="{reset_link}">Reset Password</a></p>
        <p>This link will expire in 1 hour.</p>
        <p>If you didn't request this, please ignore this email.</p>
        <br>
        <p>- JinniChirag Team</p>
      </body>
    </html>
    """
    
    part = MIMEText(html, "html")
    message.attach(part)
    
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
        server.ehlo()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, email, message.as_string())
    
    logger.info(f"Password reset email sent to {email} via SMTP")

def serialize_booking(booking: dict) -> dict:
    """Convert MongoDB document to JSON-safe format"""
    booking["_id"] = str(booking["_id"])
    if "otp" in booking:
        del booking["otp"]
    if "created_at" in booking and isinstance(booking["created_at"], datetime):
        booking["created_at"] = booking["created_at"].isoformat()
    if "updated_at" in booking and isinstance(booking["updated_at"], datetime):
        booking["updated_at"] = booking["updated_at"].isoformat()
    return booking

# ==========================================================
# LOAD WEBSITE CONTENT
# ==========================================================

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

# ==========================================================
# SYSTEM PROMPTS
# ==========================================================

BASE_SYSTEM_PROMPT = f"""
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

LANGUAGE_MAP = {
    "en": "English",
    "ne": "Nepali",
    "hi": "Hindi",
    "mr": "Marathi",
}

# ############################################################
# PUBLIC ROUTES
# ############################################################

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/chat")
async def chat(req: ChatRequest):
    """Public chatbot endpoint"""
    
    language_name = LANGUAGE_MAP.get(req.language)
    if not language_name:
        raise HTTPException(status_code=400, detail="Unsupported language")

    language_reset_prompt = f"""
IMPORTANT LANGUAGE CONTROL RULES:
- You must respond ONLY in {language_name}.
- Do NOT mix languages.
- Do NOT automatically switch languages based on user input.
- If the user writes in a different language than {language_name}, do NOT reply in that language.

USER GUIDANCE RULE:
- If the user uses a different language, politely inform them:
  "Please select your preferred language from the language selector above.
   I can respond only in the selected language."

STRICTLY FORBIDDEN:
- Do NOT say you lack support for any language.
- Do NOT mention internal limitations, models, or capabilities.
- Do NOT apologize for language support.
"""

    messages_for_ai = [
        {"role": "system", "content": BASE_SYSTEM_PROMPT},
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

@app.post("/bookings/request")
async def request_booking(booking: BookingRequest):
    """Public booking request endpoint - sends OTP"""
    
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

    if not twilio_client:
        raise HTTPException(status_code=500, detail="WhatsApp service unavailable")

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
    """Public OTP verification endpoint"""
    
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

# ############################################################
# ADMIN ROUTES - AUTHENTICATION
# ############################################################

@app.post("/admin/login")
async def admin_login(credentials: AdminLoginRequest):
    """Admin login endpoint - returns JWT token"""
    
    admin = admin_collection.find_one({"email": credentials.email})
    
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(credentials.password, admin["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_jwt_token(credentials.email, admin["role"])
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "email": admin["email"],
        "role": admin["role"]
    }

@app.post("/admin/forgot-password")
async def admin_forgot_password(request: AdminPasswordResetRequest):
    """Request password reset - sends email with reset token"""
    
    email = request.email.lower()
    
    # Only permanent admins can reset
    if email not in PERMANENT_ADMINS:
        return {
            "message": "If your email is registered, you will receive a password reset link"
        }
    
    reset_token = secrets.token_urlsafe(32)
    hashed_token = hash_password(reset_token)
    
    reset_token_collection.insert_one({
        "email": email,
        "token": hashed_token,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=1),
        "used": False
    })
    
    # FIXED: Never expose SMTP errors (security best practice)
    try:
        send_password_reset_email(email, reset_token)
    except Exception as e:
        logger.error(f"Password reset email failed for {email}: {e}")
        # Still return success to prevent email enumeration
    
    return {
        "message": "If your email is registered, you will receive a password reset link"
    }

@app.post("/admin/reset-password")
async def admin_reset_password(request: AdminPasswordResetConfirm):
    """Reset password using token from email - Auto-creates admin if not exists"""
    
    valid_tokens = reset_token_collection.find({
        "expires_at": {"$gt": datetime.utcnow()},
        "used": False
    })
    
    token_doc = None
    for doc in valid_tokens:
        if verify_password(request.token, doc["token"]):
            token_doc = doc
            break
    
    if not token_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    # Mark token as used
    reset_token_collection.update_one(
        {"_id": token_doc["_id"]},
        {"$set": {"used": True}}
    )
    
    # Check if admin exists
    admin = admin_collection.find_one({"email": token_doc["email"]})
    new_hashed_password = hash_password(request.new_password)
    
    if not admin:
        # Auto-create admin on first reset
        admin_collection.insert_one({
            "email": token_doc["email"],
            "password": new_hashed_password,
            "role": "admin",
            "created_at": datetime.utcnow()
        })
    else:
        # Update existing admin password
        admin_collection.update_one(
            {"email": token_doc["email"]},
            {"$set": {"password": new_hashed_password}}
        )
    
    return {"message": "Password reset successful"}

@app.get("/admin/verify-token")
async def verify_admin_token(admin: dict = Depends(get_current_admin)):
    """Verify if current token is valid"""
    return {
        "valid": True,
        "email": admin["email"],
        "role": admin["role"]
    }

# ############################################################
# ADMIN ROUTES - BOOKING MANAGEMENT
# ############################################################

@app.get("/admin/bookings")
async def get_all_bookings(
    status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    admin: dict = Depends(get_current_admin)
):
    """Get all bookings with optional filtering"""
    
    query = {}
    if status:
        query["status"] = status
    
    bookings = list(
        booking_collection
        .find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    
    total = booking_collection.count_documents(query)
    
    return {
        "bookings": [serialize_booking(b) for b in bookings],
        "total": total,
        "limit": limit,
        "skip": skip
    }

@app.post("/admin/bookings/search")
async def search_bookings(
    query: BookingSearchQuery,
    admin: dict = Depends(get_current_admin)
):
    """Advanced booking search"""
    
    filters = {}
    
    if query.status:
        filters["status"] = query.status
    
    if query.search:
        filters["$or"] = [
            {"name": {"$regex": query.search, "$options": "i"}},
            {"email": {"$regex": query.search, "$options": "i"}},
            {"phone": {"$regex": query.search, "$options": "i"}},
            {"service": {"$regex": query.search, "$options": "i"}}
        ]
    
    if query.date_from or query.date_to:
        date_filter = {}
        if query.date_from:
            date_filter["$gte"] = query.date_from
        if query.date_to:
            date_filter["$lte"] = query.date_to
        filters["date"] = date_filter
    
    bookings = list(
        booking_collection
        .find(filters)
        .sort("created_at", -1)
        .skip(query.skip)
        .limit(query.limit)
    )
    
    total = booking_collection.count_documents(filters)
    
    return {
        "bookings": [serialize_booking(b) for b in bookings],
        "total": total
    }

@app.get("/admin/bookings/{booking_id}")
async def get_booking_details(
    booking_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Get single booking details"""
    
    try:
        booking = booking_collection.find_one({"_id": ObjectId(booking_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID")
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return serialize_booking(booking)

@app.patch("/admin/bookings/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    status_update: BookingStatusUpdate,
    admin: dict = Depends(get_current_admin)
):
    """Update booking status"""
    
    try:
        result = booking_collection.update_one(
            {"_id": ObjectId(booking_id)},
            {"$set": {"status": status_update.status, "updated_at": datetime.utcnow()}}
        )
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID")
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return {"message": "Status updated successfully"}

@app.delete("/admin/bookings/{booking_id}")
async def delete_booking(
    booking_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Delete a booking (use with caution)"""
    
    try:
        result = booking_collection.delete_one({"_id": ObjectId(booking_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID")
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return {"message": "Booking deleted successfully"}

# ############################################################
# ADMIN ROUTES - ANALYTICS & STATISTICS
# ############################################################

@app.get("/admin/analytics/overview")
async def get_analytics_overview(admin: dict = Depends(get_current_admin)):
    """Get booking statistics overview"""
    
    total_bookings = booking_collection.count_documents({})
    pending_bookings = booking_collection.count_documents({"status": "pending"})
    completed_bookings = booking_collection.count_documents({"status": "completed"})
    cancelled_bookings = booking_collection.count_documents({"status": "cancelled"})
    otp_pending = booking_collection.count_documents({"status": "otp_pending"})
    
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_bookings = booking_collection.count_documents({
        "created_at": {"$gte": seven_days_ago}
    })
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_bookings = booking_collection.count_documents({
        "created_at": {"$gte": today_start}
    })
    
    return {
        "total_bookings": total_bookings,
        "pending_bookings": pending_bookings,
        "completed_bookings": completed_bookings,
        "cancelled_bookings": cancelled_bookings,
        "otp_pending": otp_pending,
        "recent_bookings_7_days": recent_bookings,
        "today_bookings": today_bookings
    }

@app.get("/admin/analytics/by-service")
async def get_bookings_by_service(admin: dict = Depends(get_current_admin)):
    """Get booking count grouped by service"""
    
    pipeline = [
        {"$group": {"_id": "$service", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    results = list(booking_collection.aggregate(pipeline))
    
    return {
        "services": [
            {"service": item["_id"], "count": item["count"]}
            for item in results
        ]
    }

@app.get("/admin/analytics/by-month")
async def get_bookings_by_month(admin: dict = Depends(get_current_admin)):
    """Get booking count by month"""
    
    pipeline = [
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$created_at"},
                    "month": {"$month": "$created_at"}
                },
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"_id.year": -1, "_id.month": -1}},
        {"$limit": 12}
    ]
    
    results = list(booking_collection.aggregate(pipeline))
    
    return {
        "monthly_data": [
            {
                "year": item["_id"]["year"],
                "month": item["_id"]["month"],
                "count": item["count"]
            }
            for item in results
        ]
    }

# ############################################################
# END OF API
# ############################################################