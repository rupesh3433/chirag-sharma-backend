"""
OTP Service - Enhanced with proper generation, storage, and verification
"""

import secrets
import logging
import re
from datetime import datetime, timedelta
from random import randint
from typing import Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class OTPService:
    """Service for OTP operations with enhanced security"""
    
    def __init__(self, twilio_client=None, from_number: str = None, expiry_minutes: int = 5):
        """
        Initialize OTP service
        
        Args:
            twilio_client: Twilio client instance
            from_number: WhatsApp-enabled Twilio number
            expiry_minutes: OTP expiry time in minutes
        """
        self.twilio_client = twilio_client
        self.from_number = from_number
        self.expiry_minutes = expiry_minutes
        self.otp_store: Dict[str, Dict] = {}  # In-memory store: booking_id -> otp_data
        
        logger.info(f"OTPService initialized (expiry: {expiry_minutes} minutes)")
    
    def generate_otp(self) -> str:
        """
        Generate a 6-digit OTP
        
        Returns:
            6-digit OTP string
        """
        otp = str(randint(100000, 999999))
        logger.debug(f"Generated OTP: {otp[:2]}****")
        return otp
    
    def generate_booking_id(self) -> str:
        """
        Generate a unique booking ID
        
        Returns:
            Secure booking ID string
        """
        booking_id = secrets.token_urlsafe(16)
        logger.debug(f"Generated booking ID: {booking_id[:8]}...")
        return booking_id
    
    def store_otp_data(self, booking_id: str, otp: str, phone, 
                      booking_data: Dict, language: str) -> None:
        """
        Store OTP with expiry and booking data
        
        Args:
            booking_id: Unique booking identifier
            otp: 6-digit OTP
            phone: User's phone number (can be string or dict)
            booking_data: Complete booking information
            language: User's language preference
        """
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
        
        logger.info(
            f"Stored OTP for booking {booking_id[:8]}..., "
            f"expires at {expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    
    def send_otp(self, phone, otp: str, language: str = "en") -> bool:
        """
        Send OTP via WhatsApp using Twilio
        
        Args:
            phone: Phone number (with country code) - can be string or dict
            otp: 6-digit OTP to send
            language: Language for OTP message
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.twilio_client or not self.from_number:
            logger.warning("Twilio client or from_number not configured, skipping SMS send")
            # In development, we can skip actual sending
            return True
        
        try:
            # ✅ Extract phone string from phone object (could be string or dict)
            phone_str = self._extract_phone_string(phone)
            
            if not phone_str:
                logger.error(f"❌ No valid phone found in: {phone}")
                return False
            
            # Ensure phone has whatsapp: prefix
            whatsapp_phone = f"whatsapp:{phone_str}" if not phone_str.startswith("whatsapp:") else phone_str
            
            # Format from number
            from_whatsapp = f"whatsapp:{self.from_number}" if not self.from_number.startswith("whatsapp:") else self.from_number
            
            # Get message in appropriate language
            message = self._get_otp_message(otp, language)
            
            # Send via Twilio
            result = self.twilio_client.messages.create(
                from_=from_whatsapp,
                to=whatsapp_phone,
                body=message
            )
            
            logger.info(f"✅ OTP sent to {phone_str} (SID: {result.sid})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send OTP to {phone}: {e}")
            return False
    
    def _extract_phone_string(self, phone) -> str:
        """
        Extract phone string from phone object (string or dict)
        
        Args:
            phone: Phone object (string or dict)
            
        Returns:
            Formatted phone string with country code
        """
        if not phone:
            return ""
            
        if isinstance(phone, dict):
            # Try different keys that might contain the phone number
            phone_str = phone.get('full_phone') or phone.get('formatted') or phone.get('phone', '')
            
            # If it's a dict with phone details, construct the full phone
            if not phone_str and 'country_code' in phone and 'phone' in phone:
                country_code = str(phone.get('country_code', '')).replace('+', '').strip()
                phone_num = str(phone.get('phone', '')).strip()
                if country_code and phone_num:
                    phone_str = f"+{country_code}{phone_num}"
        else:
            phone_str = str(phone)
        
        # Clean and validate the phone string
        if not phone_str:
            return ""
        
        # Remove any whitespace
        phone_str = phone_str.strip()
        
        # Remove non-digit characters except plus
        digits = re.sub(r'[^\d+]', '', phone_str)
        
        # Ensure it starts with +
        if digits and not digits.startswith('+'):
            # Check if it has a country code in another format
            if phone_str.startswith('whatsapp:'):
                phone_str = phone_str.replace('whatsapp:', '')
                digits = re.sub(r'[^\d+]', '', phone_str)
            
            # Add default India code if no country code
            if digits and not digits.startswith('+'):
                # Check if it already has 91 as country code
                if digits.startswith('91') and len(digits) >= 12:
                    phone_str = f"+{digits}"
                else:
                    # Add +91 for India
                    phone_str = f"+91{digits}"
        
        return phone_str
    
    def verify_otp(self, booking_id: str, user_otp: str) -> Dict[str, Any]:
        """
        Verify OTP and return result
        
        Args:
            booking_id: Booking identifier
            user_otp: OTP entered by user
            
        Returns:
            Dict with verification result and metadata
        """
        logger.info(f"🔍 Verifying OTP for booking {booking_id[:8]}...")
        
        # Check if booking exists
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
            logger.warning(f"⏰ OTP expired for booking {booking_id[:8]}...")
            del self.otp_store[booking_id]
            return {
                "valid": False,
                "error": f"OTP expired ({self.expiry_minutes} minutes)",
                "should_restart": True
            }
        
        # Increment attempts
        otp_data["attempts"] += 1
        
        # Check max attempts
        if otp_data["attempts"] > 3:
            logger.warning(f"🚫 Too many OTP attempts for booking {booking_id[:8]}...")
            del self.otp_store[booking_id]
            return {
                "valid": False,
                "error": "Too many failed attempts (max 3)",
                "should_restart": True
            }
        
        # Verify OTP
        if user_otp != otp_data["otp"]:
            attempts_left = 3 - otp_data["attempts"]
            logger.warning(
                f"❌ Wrong OTP for booking {booking_id[:8]}... "
                f"({attempts_left} attempts left)"
            )
            # ✅ DON'T delete here - only after max attempts or success
            return {
                "valid": False,
                "error": f"Wrong OTP. {attempts_left} attempt{'s' if attempts_left > 1 else ''} left.",
                "should_restart": False,
                "attempts_left": attempts_left
            }
        
        # ✅ OTP verified successfully
        logger.info(f"✅ OTP verified successfully for booking {booking_id[:8]}...")
        
        booking_data = otp_data["booking_data"]
        phone = otp_data["phone"]
        language = otp_data["language"]
        
        # ✅ IMPORTANT: Keep OTP data until booking is saved successfully
        # It will be deleted by the orchestrator after successful booking save
        # OR manually after booking failure
        
        return {
            "valid": True,
            "booking_data": booking_data,
            "phone": phone,
            "language": language,
            "verified_at": datetime.utcnow().isoformat(),
            "booking_id": booking_id  # ✅ Return booking_id for cleanup later
        }
    
    def resend_otp(self, booking_id: str, force_new: bool = True) -> Dict[str, Any]:
        """
        Resend OTP for existing booking - ALWAYS generates NEW OTP
        
        Args:
            booking_id: Booking identifier
            force_new: If True, always generate new OTP (default)
            
        Returns:
            Dict with resend result
        """
        logger.info(f"🔄 Resending OTP for booking {booking_id[:8]}... (force_new={force_new})")
        
        otp_data = self.otp_store.get(booking_id)
        
        if not otp_data:
            logger.warning(f"❌ Cannot resend: Booking ID not found {booking_id[:8]}...")
            return {
                "success": False,
                "error": "OTP expired or invalid booking ID",
                "should_regenerate": True
            }
        
        # Check if expired
        now = datetime.utcnow()
        if now > otp_data["expires_at"]:
            logger.warning(f"⏰ Cannot resend: OTP expired for {booking_id[:8]}...")
            del self.otp_store[booking_id]
            return {
                "success": False,
                "error": "OTP expired",
                "should_regenerate": True
            }
        
        # Check rate limiting (prevent spam)
        last_sent = otp_data.get("last_sent")
        if last_sent:
            time_since_last = (now - last_sent).total_seconds()
            if time_since_last < 30:  # Minimum 30 seconds between resends
                wait_time = int(30 - time_since_last)
                logger.warning(f"⏱️ Rate limit: Wait {wait_time}s before resending")
                return {
                    "success": False,
                    "error": f"Please wait {wait_time} seconds before resending",
                    "should_regenerate": False
                }
        
        # ✅ ALWAYS generate NEW OTP when resending
        new_otp = self.generate_otp()
        
        # Update OTP data
        otp_data["otp"] = new_otp
        otp_data["attempts"] = 0  # ✅ Reset attempts with new OTP
        otp_data["expires_at"] = now + timedelta(minutes=self.expiry_minutes)
        otp_data["last_sent"] = now
        
        phone = otp_data["phone"]
        language = otp_data["language"]
        
        # Send new OTP
        sent = self.send_otp(phone, new_otp, language)
        
        if sent:
            # Format phone for display
            phone_display = self._format_phone_for_display(phone)
            logger.info(f"✅ NEW OTP generated and sent to {phone_display}")
            return {
                "success": True,
                "phone": phone_display,
                "new_otp_generated": True,
                "resent_at": now.isoformat()
            }
        else:
            logger.error(f"❌ Failed to send new OTP to {phone}")
            return {
                "success": False,
                "error": "Failed to send OTP via SMS",
                "should_regenerate": False
            }
    
    def cleanup_expired_otps(self) -> int:
        """
        Remove expired OTPs from store
        
        Returns:
            Number of expired OTPs cleaned
        """
        expired = []
        now = datetime.utcnow()
        
        for booking_id, data in self.otp_store.items():
            if now > data["expires_at"]:
                expired.append(booking_id)
        
        for booking_id in expired:
            del self.otp_store[booking_id]
        
        if expired:
            logger.info(f"🧹 Cleaned {len(expired)} expired OTP(s)")
        
        return len(expired)
    
    def get_otp_data(self, booking_id: str) -> Optional[Dict]:
        """
        Retrieve OTP data for a booking
        
        Args:
            booking_id: Booking identifier
            
        Returns:
            OTP data dict or None if not found
        """
        data = self.otp_store.get(booking_id)
        
        if data:
            # Check if expired
            if datetime.utcnow() > data["expires_at"]:
                logger.warning(f"⏰ Retrieved expired OTP for {booking_id[:8]}...")
                del self.otp_store[booking_id]
                return None
        
        return data
    
    def delete_otp_data(self, booking_id: str) -> bool:
        """
        Delete OTP data for a booking
        
        Args:
            booking_id: Booking identifier
            
        Returns:
            True if deleted, False if not found
        """
        if booking_id in self.otp_store:
            del self.otp_store[booking_id]
            logger.info(f"🗑️ Deleted OTP data for {booking_id[:8]}...")
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get OTP service statistics
        
        Returns:
            Dict with service stats
        """
        now = datetime.utcnow()
        active_otps = len(self.otp_store)
        expired = sum(1 for data in self.otp_store.values() if now > data["expires_at"])
        
        return {
            "active_otps": active_otps,
            "expired_otps": expired,
            "expiry_minutes": self.expiry_minutes,
            "twilio_configured": self.twilio_client is not None
        }
    
    def _get_otp_message(self, otp: str, language: str) -> str:
        """
        Get OTP message in appropriate language
        
        Args:
            otp: 6-digit OTP
            language: Language code
            
        Returns:
            Formatted OTP message
        """
        messages = {
            "en": f"Your JinniChirag booking OTP is {otp}. Valid for {self.expiry_minutes} minutes. Do not share this code.",
            
            "hi": f"आपका JinniChirag बुकिंग OTP {otp} है। {self.expiry_minutes} मिनट के लिए मान्य। इस कोड को साझा न करें।",
            
            "ne": f"तपाईंको JinniChirag बुकिङ OTP {otp} हो। {self.expiry_minutes} मिनेटको लागि मान्य। यो कोड साझा नगर्नुहोस्।",
            
            "mr": f"तुमचा JinniChirag बुकिंग OTP {otp} आहे। {self.expiry_minutes} मिनिटांसाठी वैध। हा कोड शेअर करू नका।"
        }
        
        return messages.get(language, messages["en"])
    
    def _format_phone_for_display(self, phone) -> str:
        """
        Format phone number for display (masked for privacy)
        
        Args:
            phone: Phone object (string or dict)
            
        Returns:
            Formatted and masked phone string
        """
        if not phone:
            return "[phone number]"
        
        # Extract phone string
        phone_str = ""
        if isinstance(phone, dict):
            phone_str = phone.get('formatted') or phone.get('full_phone') or str(phone)
        else:
            phone_str = str(phone)
        
        # Mask the phone for privacy
        digits = re.sub(r'\D', '', phone_str)
        
        if len(digits) >= 10:
            if phone_str.startswith('+'):
                # Keep country code visible, mask middle digits
                country_code = phone_str[:phone_str.find(digits[:2]) + 2]
                return f"{country_code}****{digits[-4:]}"
            else:
                return f"+XX{digits[:2]}****{digits[-4:]}"
        
        return phone_str