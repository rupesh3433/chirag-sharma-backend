"""
OTP Service - FINAL VERSION
Uses templates.py for all messages
"""

import secrets
import logging
import threading
import time
from datetime import datetime, timedelta
from random import randint
from typing import Dict, Optional, Any

from ..config.config import (
    get_agent_setting,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE
)
from ..prompts.templates import (
    get_otp_sms_message,
    validate_language
)

logger = logging.getLogger(__name__)


class OTPService:
    """Service for OTP operations - FINAL VERSION"""
    
    def __init__(self, twilio_client=None, from_number: str = None, expiry_minutes: int = None):
        """Initialize OTP service"""
        self.twilio_client = twilio_client
        self.from_number = from_number
        
        # Get expiry from config if not provided
        self.expiry_minutes = expiry_minutes or get_agent_setting('otp_expiry_minutes', 5)
        
        self.otp_store: Dict[str, Dict] = {}
        self.lock = threading.RLock()
        
        # Stats tracking
        self.stats = {
            'generated': 0,
            'sent': 0,
            'verified': 0,
            'failed': 0,
            'expired': 0,
            'resent': 0
        }
        
        # Start background cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self.cleanup_thread.start()
        
        logger.info(f"✅ OTPService initialized (expiry: {self.expiry_minutes}m)")
    
    def generate_otp(self) -> str:
        """Generate 6-digit OTP"""
        otp = str(randint(100000, 999999))
        
        with self.lock:
            self.stats['generated'] += 1
        
        logger.debug(f"Generated OTP: {otp[:2]}****")
        return otp
    
    def generate_booking_id(self) -> str:
        """Generate unique booking ID"""
        booking_id = secrets.token_urlsafe(16)
        logger.debug(f"Generated booking ID: {booking_id[:8]}...")
        return booking_id
    
    def store_otp_data(self, booking_id: str, otp: str, phone: str, 
                      booking_data: Dict, language: str) -> None:
        """Store OTP with expiry and booking data"""
        
        # Validate language
        language = validate_language(language)
        
        with self.lock:
            expires_at = datetime.utcnow() + timedelta(minutes=self.expiry_minutes)
            
            self.otp_store[booking_id] = {
                "otp": otp,
                "expires_at": expires_at,
                "booking_data": booking_data,
                "phone": phone,
                "language": language,
                "attempts": 0,
                "created_at": datetime.utcnow(),
                "last_sent": datetime.utcnow()
            }
            
            logger.info(f"Stored OTP for {booking_id[:8]}... (expires: {expires_at.strftime('%H:%M:%S')})")
    
    def send_otp(self, phone: str, otp: str, language: str = "en") -> bool:
        """Send OTP via WhatsApp using Twilio"""
        
        # Validate language
        language = validate_language(language)
        
        if not self.twilio_client or not self.from_number:
            logger.warning("⚠️ Twilio not configured, skipping send")
            with self.lock:
                self.stats['sent'] += 1
            return True
        
        try:
            # Format phone numbers
            whatsapp_phone = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
            from_whatsapp = f"whatsapp:{self.from_number}" if not self.from_number.startswith("whatsapp:") else self.from_number
            
            # ✅ Use template function for OTP message
            message = get_otp_sms_message(otp, self.expiry_minutes, language)
            
            # Send via Twilio
            result = self.twilio_client.messages.create(
                from_=from_whatsapp,
                to=whatsapp_phone,
                body=message
            )
            
            with self.lock:
                self.stats['sent'] += 1
            
            logger.info(f"✅ OTP sent to {phone} (SID: {result.sid})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send OTP: {e}")
            with self.lock:
                self.stats['failed'] += 1
            return False
    
    def verify_otp(self, booking_id: str, user_otp: str) -> Dict[str, Any]:
        """Verify OTP and return result"""
        logger.info(f"🔍 Verifying OTP for {booking_id[:8]}...")
        
        with self.lock:
            otp_data = self.otp_store.get(booking_id)
            
            if not otp_data:
                logger.warning(f"❌ Booking ID not found: {booking_id[:8]}...")
                return {
                    "valid": False,
                    "error": "OTP expired or invalid booking ID",
                    "should_restart": True
                }
            
            # Check expiry
            now = datetime.utcnow()
            if now > otp_data["expires_at"]:
                logger.warning(f"⏰ OTP expired for {booking_id[:8]}...")
                del self.otp_store[booking_id]
                self.stats['expired'] += 1
                return {
                    "valid": False,
                    "error": f"OTP expired ({self.expiry_minutes} minutes)",
                    "should_restart": True
                }
            
            # Increment attempts
            otp_data["attempts"] += 1
            
            # Check max attempts (from config)
            max_attempts = get_agent_setting('max_otp_attempts', 3)
            if otp_data["attempts"] > max_attempts:
                logger.warning(f"🚫 Too many attempts for {booking_id[:8]}...")
                del self.otp_store[booking_id]
                self.stats['failed'] += 1
                return {
                    "valid": False,
                    "error": f"Too many failed attempts (max {max_attempts})",
                    "should_restart": True
                }
            
            # Verify OTP
            if user_otp != otp_data["otp"]:
                attempts_left = max_attempts - otp_data["attempts"]
                logger.warning(f"❌ Wrong OTP ({attempts_left} attempts left)")
                return {
                    "valid": False,
                    "error": f"Wrong OTP. {attempts_left} attempt{'s' if attempts_left > 1 else ''} left.",
                    "should_restart": False,
                    "attempts_left": attempts_left
                }
            
            # ✅ Success - don't delete, let orchestrator handle cleanup
            logger.info(f"✅ OTP verified for {booking_id[:8]}...")
            self.stats['verified'] += 1
            
            return {
                "valid": True,
                "booking_data": otp_data["booking_data"],
                "phone": otp_data["phone"],
                "language": otp_data["language"],
                "verified_at": datetime.utcnow().isoformat(),
                "booking_id": booking_id
            }
    
    def resend_otp(self, booking_id: str, force_new: bool = True) -> Dict[str, Any]:
        """Resend OTP - ALWAYS generates NEW OTP"""
        logger.info(f"🔄 Resending OTP for {booking_id[:8]}...")
        
        with self.lock:
            otp_data = self.otp_store.get(booking_id)
            
            if not otp_data:
                return {
                    "success": False,
                    "error": "OTP expired or invalid booking ID",
                    "should_regenerate": True
                }
            
            # Check expiry
            now = datetime.utcnow()
            if now > otp_data["expires_at"]:
                del self.otp_store[booking_id]
                self.stats['expired'] += 1
                return {
                    "success": False,
                    "error": "OTP expired",
                    "should_regenerate": True
                }
            
            # Rate limiting (30 seconds)
            last_sent = otp_data.get("last_sent")
            if last_sent:
                time_since_last = (now - last_sent).total_seconds()
                if time_since_last < 30:
                    wait_time = int(30 - time_since_last)
                    return {
                        "success": False,
                        "error": f"Please wait {wait_time} seconds before resending",
                        "should_regenerate": False
                    }
            
            # Generate NEW OTP
            new_otp = self.generate_otp()
            
            # Update OTP data
            otp_data["otp"] = new_otp
            otp_data["attempts"] = 0
            otp_data["expires_at"] = now + timedelta(minutes=self.expiry_minutes)
            otp_data["last_sent"] = now
            
            phone = otp_data["phone"]
            language = otp_data["language"]
            
            # Send new OTP
            sent = self.send_otp(phone, new_otp, language)
            
            if sent:
                self.stats['resent'] += 1
                logger.info(f"✅ NEW OTP sent to {phone}")
                return {
                    "success": True,
                    "phone": phone,
                    "new_otp_generated": True,
                    "resent_at": now.isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send OTP via SMS",
                    "should_regenerate": False
                }
    
    def cleanup_expired_otps(self) -> int:
        """Remove expired OTPs"""
        with self.lock:
            expired = []
            now = datetime.utcnow()
            
            for booking_id, data in self.otp_store.items():
                if now > data["expires_at"]:
                    expired.append(booking_id)
            
            for booking_id in expired:
                del self.otp_store[booking_id]
            
            if expired:
                self.stats['expired'] += len(expired)
                logger.info(f"🧹 Cleaned {len(expired)} expired OTP(s)")
            
            return len(expired)
    
    def delete_otp_data(self, booking_id: str) -> bool:
        """Delete OTP data for a booking"""
        with self.lock:
            if booking_id in self.otp_store:
                del self.otp_store[booking_id]
                logger.info(f"🗑️ Deleted OTP for {booking_id[:8]}...")
                return True
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        with self.lock:
            stats = self.stats.copy()
            
            now = datetime.utcnow()
            active_otps = len(self.otp_store)
            expired = sum(1 for data in self.otp_store.values() if now > data["expires_at"])
            
            stats.update({
                "active_otps": active_otps,
                "expired_otps": expired,
                "expiry_minutes": self.expiry_minutes,
                "twilio_configured": self.twilio_client is not None,
                "timestamp": now.isoformat()
            })
            
            return stats
    
    def _cleanup_worker(self):
        """Background cleanup thread"""
        # Get interval from config
        cleanup_interval = get_agent_setting('otp_cleanup_interval_seconds', 300)
        
        while True:
            try:
                time.sleep(cleanup_interval)
                cleaned = self.cleanup_expired_otps()
                if cleaned > 0:
                    logger.debug(f"Background cleanup: {cleaned} OTPs")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")