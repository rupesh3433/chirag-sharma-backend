import logging
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from twilio.rest import Client
from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_EMAIL,
    SMTP_PASSWORD,
    BREVO_API_KEY,
    FRONTEND_URL
)
from database import knowledge_collection
from security import hash_password

logger = logging.getLogger(__name__)

# ----------------------
# Twilio Client
# ----------------------
try:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
except Exception as e:
    logger.warning(f"Twilio client initialization failed: {e}")
    twilio_client = None

# ----------------------
# WhatsApp Messaging
# ----------------------

def send_whatsapp_message(phone: str, message: str):
    """Send WhatsApp message via Twilio"""
    if not twilio_client:
        logger.warning("Twilio not configured - cannot send WhatsApp message")
        return
    
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{phone}",
            body=message
        )
        logger.info(f"WhatsApp message sent to {phone}")
    except Exception as e:
        logger.error(f"WhatsApp message failed for {phone}: {e}")

# ----------------------
# Email Service
# ----------------------

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

# ----------------------
# Knowledge Base Service
# ----------------------

def load_knowledge_from_db(language: str) -> str:
    """Load knowledge base content from database for specific language"""
    try:
        # Get all active knowledge entries for the specified language
        knowledge_entries = knowledge_collection.find({
            "language": language,
            "is_active": True
        }).sort("created_at", -1)
        
        # Combine all content
        content_blocks = []
        for entry in knowledge_entries:
            content_blocks.append(entry.get("content", ""))
        
        return "\n\n".join(content_blocks)
    except Exception as e:
        logger.error(f"Error loading knowledge from database: {e}")
        return ""