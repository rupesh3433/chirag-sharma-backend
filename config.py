import os
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# ----------------------
# API Keys
# ----------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

# ----------------------
# JWT Configuration
# ----------------------
JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-jwt-key-change-this")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# ----------------------
# Twilio Configuration
# ----------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")

# ----------------------
# Email Configuration
# ----------------------
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Brevo API (for environments that block SMTP)
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

# ----------------------
# Frontend URL
# ----------------------
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
# Language Configuration
# ----------------------
LANGUAGE_MAP = {
    "en": "English",
    "ne": "Nepali",
    "hi": "Hindi",
    "mr": "Marathi",
}

# ----------------------
# CORS Origins
# ----------------------
CORS_ORIGINS = [
    "https://sharmachirag.vercel.app",
    "https://sharmachiragadmin.vercel.app",
    "http://localhost:5173",
    "http://localhost:5174",
]