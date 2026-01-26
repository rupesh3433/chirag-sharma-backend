# agent/utils/question_detector.py
"""
Enhanced Question Detector - Smarter off-topic detection
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class QuestionDetector:
    """Smarter question detection for booking flow"""
    
    def __init__(self):
        # Booking states where questions should be allowed
        self.booking_states = [
            "SELECTING_SERVICE", "SELECTING_PACKAGE", 
            "COLLECTING_DETAILS", "CONFIRMING", "OTP_SENT"
        ]
        
        # Question starters that should trigger knowledge base
        self.QUESTION_STARTERS = [
            "what", "which", "who", "when", "where", "why", "how",
            "list", "show", "tell", "give", "explain", "describe",
            "compare", "define", "clarify", "summarize",
            "can you", "could you", "would you", "will you",
            "do you", "does it", "is it", "are there", "is there",
            "i want to know", "i would like to know", "tell me about",
            "explain to me", "help me understand", "what about"
        ]
        
        # Pure off-topic patterns (always off-topic)
        self.PURE_OFF_TOPIC = [
            'instagram', 'facebook', 'twitter', 'youtube', 'linkedin',
            'social media', 'social', 'media', 'follow', 'subscriber',
            'channel', 'profile', 'page', 'account', 'handle',
            'username', 'link', 'website', 'web', 'site', 'online',
            'internet', 'net', 'whatsapp channel', 'telegram'
        ]
        
        # Booking-related keywords (these are NOT off-topic)
        self.BOOKING_KEYWORDS = [
            'book', 'booking', 'reserve', 'appointment', 'schedule',
            'service', 'package', 'price', 'cost', '₹', 'charge', 'fee',
            'name', 'phone', 'number', 'email', 'mail', 'address',
            'date', 'day', 'month', 'year', 'location', 'place',
            'pincode', 'zipcode', 'postal', 'code', 'country',
            'event', 'function', 'ceremony', 'wedding', 'bridal',
            'party', 'engagement', 'henna', 'mehendi', 'makeup',
            'artist', 'chirag', 'sharma', 'my ', 'i ', 'me '
        ]
        
        logger.info("✅ QuestionDetector initialized")
    
    def is_off_topic(self, message: str, current_state: str) -> bool:
        """
        Determine if message is off-topic for current state
        Returns True only for pure off-topic queries
        """
        msg_lower = message.lower().strip()
        
        # If current state is not a booking state, don't treat as off-topic
        if current_state not in self.booking_states:
            return False
        
        # Check for pure off-topic patterns first
        for pattern in self.PURE_OFF_TOPIC:
            if pattern in msg_lower:
                logger.info(f"🔍 Pure off-topic detected: {pattern}")
                return True
        
        # Check if it's a question starter
        is_question = False
        for starter in self.QUESTION_STARTERS:
            if msg_lower.startswith(starter):
                is_question = True
                break
        
        # If it's not a question, it's probably booking data
        if not is_question:
            return False
        
        # If it's a question but contains booking keywords, it's NOT off-topic
        # (e.g., "what is the price?" is booking-related)
        for keyword in self.BOOKING_KEYWORDS:
            if keyword in msg_lower:
                logger.info(f"🔍 Question contains booking keyword: {keyword}")
                return False
        
        # Question without booking keywords might be off-topic
        # But be lenient during details collection
        if current_state == "COLLECTING_DETAILS":
            # During details collection, only social media is off-topic
            return any(pattern in msg_lower for pattern in self.PURE_OFF_TOPIC)
        
        # For other states, be more strict
        return True
    
    def is_social_media_question(self, message: str) -> Tuple[bool, Optional[str]]:
        """Check if message is about social media"""
        msg_lower = message.lower()
        
        if 'instagram' in msg_lower:
            return True, 'instagram'
        elif 'facebook' in msg_lower:
            return True, 'facebook'
        elif 'whatsapp' in msg_lower:
            return True, 'whatsapp'
        elif 'twitter' in msg_lower or 'x ' in msg_lower:
            return True, 'twitter'
        elif 'youtube' in msg_lower:
            return True, 'youtube'
        elif any(pattern in msg_lower for pattern in ['social media', 'social', 'media']):
            return True, 'social_media'
        
        return False, None
    
    def get_social_media_response(self, platform: str, language: str) -> str:
        """Get response for social media questions"""
        responses = {
            "en": {
                "instagram": "You can follow us on Instagram @ChiragSharmaMakeup for latest work and updates! 📸",
                "facebook": "You can find us on Facebook as ChiragSharmaMakeup! 👍",
                "whatsapp": "You can WhatsApp us at +91XXXXXXXXXX for direct booking inquiries! 💬",
                "twitter": "Follow us on Twitter/X @ChiragSharmaMU for updates! 🐦",
                "youtube": "Subscribe to our YouTube channel Chirag Sharma Makeup for tutorials! ▶️",
                "social_media": "We're active on social media! You can find links to all our platforms. 🌐"
            },
            "hi": {
                "instagram": "आप हमें Instagram पर @ChiragSharmaMakeup फॉलो कर सकते हैं! 📸",
                "facebook": "आप हमें Facebook पर ChiragSharmaMakeup के रूप में पा सकते हैं! 👍",
                "whatsapp": "आप हमें +91XXXXXXXXXX पर WhatsApp कर सकते हैं! 💬",
                "twitter": "हमें Twitter/X पर @ChiragSharmaMU फॉलो करें! 🐦",
                "youtube": "हमारे YouTube चैनल Chirag Sharma Makeup को सब्सक्राइब करें! ▶️",
                "social_media": "हम सोशल मीडिया पर सक्रिय हैं! आप सभी प्लेटफॉर्म के लिंक पा सकते हैं। 🌐"
            }
        }
        
        lang_responses = responses.get(language, responses["en"])
        return lang_responses.get(platform, lang_responses["social_media"])
    
    def is_booking_related_question(self, message: str) -> bool:
        """Check if question is related to booking"""
        msg_lower = message.lower()
        
        # Check for question indicators
        has_question = '?' in message
        starts_with_question = any(msg_lower.startswith(starter) for starter in self.QUESTION_STARTERS)
        
        if not (has_question or starts_with_question):
            return False
        
        # Check for booking keywords in the question
        for keyword in self.BOOKING_KEYWORDS:
            if keyword in msg_lower:
                return True
        
        return False

    # Add this method to your existing QuestionDetector class
    def is_question_during_booking(self, message: str, current_state: str) -> bool:
        """
        Compatibility method for FieldExtractor
        """
        # For backward compatibility, treat as off-topic check
        return self.is_off_topic(message, current_state)