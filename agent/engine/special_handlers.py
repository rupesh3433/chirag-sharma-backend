"""Complete special case handlers for FSM."""
import re
import logging
from typing import Tuple, Dict, Any
from datetime import datetime
from ..models.intent import BookingIntent
from ..models.state import BookingState

logger = logging.getLogger(__name__)

class SpecialHandlers:
    """Handle all special cases: email selection, year response, cancellation."""
    
    def __init__(self, extractors, prompt_generator):
        self.extractors = extractors
        self.prompts = prompt_generator
    
    def handle_email_selection(
        self,
        message: str,
        intent: BookingIntent,
        email_options: Dict,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Complete email selection handling."""
        emails = email_options.get('emails', [])
        
        # Check for numeric selection
        num_match = re.search(r'\b([1-9])\b', message)
        if num_match:
            idx = int(num_match.group(1)) - 1
            if 0 <= idx < len(emails):
                return self._handle_numeric_email_selection(intent, emails[idx], language)
        
        # Check for direct email
        email_match = re.search(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', message, re.IGNORECASE)
        if email_match:
            return self._handle_direct_email_selection(intent, email_match.group(0).lower(), language)
        
        # Not understood
        return (BookingState.COLLECTING_DETAILS.value, intent, {
            "action": "email_selection",
            "message": self.prompts.get_email_selection_prompt(emails, language),
            "mode": "booking",
            "understood": False
        })
    
    def _handle_numeric_email_selection(
        self,
        intent: BookingIntent,
        email: str,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle numeric email selection."""
        intent.email = email
        intent.metadata.pop('email_options', None)
        logger.info(f"✅ Email selected: {email}")
        
        return self._post_email_selection(intent, language)
    
    def _handle_direct_email_selection(
        self,
        intent: BookingIntent,
        email: str,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle direct email input."""
        intent.email = email
        intent.metadata.pop('email_options', None)
        logger.info(f"✅ Email selected directly: {intent.email}")
        
        return self._post_email_selection(intent, language)
    
    def _post_email_selection(
        self,
        intent: BookingIntent,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle post-email selection logic."""
        if intent.is_complete():
            return (BookingState.CONFIRMING.value, intent, {
                "action": "ask_confirmation",
                "message": self.prompts.get_confirmation_prompt(intent, language),
                "mode": "booking",
                "understood": True
            })
        
        missing = intent.missing_fields()
        return (BookingState.COLLECTING_DETAILS.value, intent, {
            "action": "ask_details",
            "message": self.prompts.get_collected_summary_prompt(intent, missing, language),
            "missing": missing,
            "mode": "booking",
            "understood": True
        })
    
    def handle_year_response(
        self,
        message: str,
        intent: BookingIntent,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Complete year response handling."""
        year = self.extractors.extract_year_from_message(message)
        
        if year:
            date_info = intent.metadata.get('date_info', {}) if hasattr(intent, 'metadata') and intent.metadata else {}
            
            if date_info.get('needs_year', False) and intent.date:
                try:
                    return self._update_year_in_date(intent, year, date_info, language)
                except Exception as e:
                    logger.error(f"Error updating year: {e}")
        
        # Ask for year again
        return self._ask_for_year_again(intent, language)
    
    def _update_year_in_date(
        self,
        intent: BookingIntent,
        year: int,
        date_info: Dict,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Update year in existing date."""
        old_date = datetime.strptime(intent.date, '%Y-%m-%d')
        new_date = old_date.replace(year=year)
        intent.date = new_date.strftime('%Y-%m-%d')
        
        # Update metadata
        intent.metadata['date_info']['needs_year'] = False
        intent.metadata['date_info']['user_provided_year'] = year
        
        missing = intent.missing_fields()
        
        return (BookingState.COLLECTING_DETAILS.value, intent, {
            "action": "year_provided",
            "message": f"✅ Updated year to {year}. " + 
                      self.prompts.get_collected_summary_prompt(intent, missing, language),
            "mode": "booking",
            "understood": True
        })
    
    def _ask_for_year_again(
        self,
        intent: BookingIntent,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Ask for year again with appropriate message."""
        date_original = intent.metadata.get('date_info', {}).get('original', 'the date')
        
        prompt_map = {
            'en': f"📅 **You provided date: '{date_original}' but not the year. Please provide the year (e.g., 2025, 2026):**",
            'hi': f"📅 **आपने तारीख दी: '{date_original}' लेकिन साल नहीं दिया। कृपया साल दें (जैसे 2025, 2026):**",
            'ne': f"📅 **तपाईंले मिति दिनुभयो: '{date_original}' तर वर्ष दिनुभएन। कृपया वर्ष दिनुहोस् (जस्तै 2025, 2026):**",
            'mr': f"📅 **तुम्ही तारीख दिली: '{date_original}' पण वर्ष दिले नाही. कृपया वर्ष द्या (उदा. 2025, 2026):**"
        }
        
        prompt = prompt_map.get(language, prompt_map['en'])
        
        return (BookingState.COLLECTING_DETAILS.value, intent, {
            "action": "ask_year",
            "message": prompt,
            "mode": "booking",
            "understood": False
        })
    
    def handle_cancellation(
        self,
        msg_lower: str,
        intent: BookingIntent,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle cancellation request."""
        if any(word in msg_lower for word in ['cancel', 'stop', 'quit', 'exit', 'abort', 'nevermind']):
            intent.reset()
            logger.info("✅ User cancelled booking")
            return (BookingState.GREETING.value, intent, {
                "action": "cancelled",
                "message": "✅ Booking cancelled. How else can I help?",
                "mode": "chat",
                "understood": True
            })
        return None
    
    def handle_already_provided(
        self,
        msg_lower: str,
        intent: BookingIntent,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle when user says they already provided info."""
        if any(phrase in msg_lower for phrase in ['already gave', 'already told', 'i gave', 'i told', 'i provided']):
            missing = intent.missing_fields()
            logger.info(f"ℹ️ User says already provided. Missing: {missing}")
            
            if not missing:
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "ask_confirmation",
                    "message": self.prompts.get_confirmation_prompt(intent, language),
                    "mode": "booking",
                    "understood": True
                })
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "clarify_details",
                "message": self.prompts.get_collected_summary_prompt(intent, missing, language),
                "missing": missing,
                "mode": "booking",
                "understood": True
            })
        return None