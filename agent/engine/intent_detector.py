"""
Intent Detector - Enhanced user intent detection
"""

import re
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class IntentDetector:
    """Detects various user intents with confidence scoring"""
    
    def __init__(self):
        """Initialize intent detector with comprehensive patterns"""
        
        # Booking intent patterns
        self.booking_keywords = [
            'book', 'booking', 'reserve', 'reservation', 'schedule', 
            'appointment', 'i want to book', 'make booking', 'proceed',
            'book now', 'book service', 'book makeup', 'book bridal',
            'book party', 'book henna', 'make reservation', 'get appointment',
            'interested in booking', 'looking to book', 'want to reserve'
        ]
        
        # Info query patterns
        self.info_keywords = [
            'what', 'which', 'how', 'tell me', 'show me', 'list',
            'information', 'info', 'details', 'about', 'price', 'cost',
            'available', 'offer', 'have', 'do you have', 'can you show',
            'what are', 'what is', 'how much', 'pricing', 'packages'
        ]
        
        # Completion/confirmation patterns
        self.completion_keywords = [
            'done', 'finish', 'finished', 'complete', 'completed',
            'proceed', 'confirm', 'confirmed', 'go ahead', 'send otp',
            'book now', 'ready', 'all set', 'submit', 'finalize',
            "that's all", "that's it", 'all done', 'ready to book'
        ]
        
        # Exit intent patterns
        self.exit_keywords = [
            'exit', 'cancel', 'quit', 'stop', 'nevermind', 'never mind',
            'exit booking', 'cancel booking', 'stop booking', 'abort',
            'forget it', 'not interested', 'changed my mind'
        ]
        
        # Restart patterns
        self.restart_keywords = [
            'restart', 'start over', 'begin again', 'reset', 'new booking',
            'start fresh', 'start again', 'from beginning', 'retry'
        ]
        
        # Frustration indicators
        self.frustration_keywords = [
            'again', 'seriously', 'ugh', 'come on', 'really',
            'annoying', 'frustrating', "what's wrong", 'problem',
            'already gave', 'already provided', 'already told',
            'i told you', 'i said', 'i mentioned', 'you asked',
            'stupid', 'ridiculous', 'unbelievable', 'crazy',
            'not working', 'broken', 'error', 'wrong'
        ]
        
        # Affirmative patterns
        self.affirmative_keywords = [
            'yes', 'yeah', 'yep', 'yup', 'sure', 'ok', 'okay',
            'correct', 'right', 'exactly', 'absolutely', 'definitely',
            'of course', 'indeed', 'affirmative', 'confirmed'
        ]
        
        # Negative patterns
        self.negative_keywords = [
            'no', 'nope', 'nah', 'not', 'never', 'wrong', 'incorrect',
            'not correct', 'not right', "don't", 'dont', 'negative'
        ]
        
        # Service keywords mapping
        self.service_keywords = {
            'Bridal Makeup Services': [
                'bridal', 'bride', 'wedding', 'marriage', 'shaadi',
                'dulhan', 'wedding makeup', 'bridal makeup'
            ],
            'Party Makeup Services': [
                'party', 'function', 'celebration', 'event',
                'party makeup', 'occasion', 'gathering'
            ],
            'Engagement & Pre-Wedding Makeup': [
                'engagement', 'pre-wedding', 'pre wedding', 'sangeet',
                'mehendi', 'cocktail', 'engagement makeup',
                'engagement ceremony', 'ring ceremony'
            ],
            'Henna (Mehendi) Services': [
                'henna', 'mehendi', 'mehndi', 'henna art',
                'bridal henna', 'mehandi', 'mendhi'
            ]
        }
        
        # Question patterns
        self.question_patterns = [
            r'\?$',  # Ends with question mark
            r'^(what|where|when|why|how|which|who|can|could|would|will|is|are|do|does)',
            r'(tell me|show me|explain|describe|help me understand)',
            r'(what if|how about|what about)',
        ]
    
    def detect_intent(self, message: str, context: Dict = None) -> Dict[str, any]:
        """
        Detect primary intent with confidence score
        
        Returns:
            {
                'intent': str (booking|info|completion|exit|restart|question|unknown),
                'confidence': float (0.0-1.0),
                'sub_intent': str (optional),
                'entities': Dict (extracted entities)
            }
        """
        msg_lower = message.lower().strip()
        
        # Check each intent type with scoring
        scores = {
            'booking': self._score_booking_intent(msg_lower, context),
            'info': self._score_info_intent(msg_lower),
            'completion': self._score_completion_intent(msg_lower),
            'exit': self._score_exit_intent(msg_lower),
            'restart': self._score_restart_intent(msg_lower),
            'question': self._score_question_intent(msg_lower),
            'affirmative': self._score_affirmative(msg_lower),
            'negative': self._score_negative(msg_lower)
        }
        
        # Get highest scoring intent
        primary_intent = max(scores.items(), key=lambda x: x[1])
        
        return {
            'intent': primary_intent[0],
            'confidence': primary_intent[1],
            'all_scores': scores,
            'is_question': scores['question'] > 0.3,
            'has_frustration': self.detect_frustration(message)
        }
    
    def detect_booking_intent(self, message: str, history: List = None) -> bool:
        """Detect if user wants to make a booking"""
        msg_lower = message.lower().strip()
        
        # Strong signals - explicit booking keywords
        if any(keyword in msg_lower for keyword in self.booking_keywords):
            return True
        
        # Numeric selection (1-4) when services context exists
        if history:
            last_assistant = self._get_last_assistant_message(history)
            if last_assistant and self._has_service_list_context(last_assistant):
                if re.match(r'^[1-4]$', msg_lower):
                    return True
        
        # Pattern: "I want/need [service]" without info keywords
        want_pattern = r'i\s+(?:want|need|would\s+like)\s+(?:to\s+)?(?:book|get|have|reserve|schedule)'
        if re.search(want_pattern, msg_lower):
            return True
        
        # Pattern: "for [service]" (e.g., "for bridal makeup")
        for_pattern = r'for\s+(?:bridal|party|engagement|henna|mehendi|wedding)'
        if re.search(for_pattern, msg_lower):
            return True
        
        return False
    
    def detect_info_intent(self, message: str) -> bool:
        """Detect if user wants information"""
        msg_lower = message.lower()
        
        has_info = any(keyword in msg_lower for keyword in self.info_keywords)
        has_booking = any(keyword in msg_lower for keyword in self.booking_keywords)
        
        # Info intent if has info keywords but NOT booking keywords
        return has_info and not has_booking
    
    def detect_service_selection(self, message: str, last_shown_list: Optional[str] = None) -> Optional[str]:
        """
        Detect service selection from message
        
        Returns: service number (1-4) or service name
        """
        msg_lower = message.lower().strip()
        
        # Numeric selection (1-4)
        if last_shown_list == "services":
            num_match = re.search(r'\b([1-4])\b', msg_lower)
            if num_match:
                return num_match.group(1)
        
        # Text-based selection
        for service_name, keywords in self.service_keywords.items():
            for keyword in keywords:
                if keyword in msg_lower:
                    return service_name
        
        # Pattern matching for "go for X", "choose X", "select X"
        selection_patterns = [
            r'(?:go\s+for|choose|select|pick|want|need)\s+([1-4])',
            r'([1-4])\s+(?:please|pls)',
            r'option\s+([1-4])',
            r'number\s+([1-4])'
        ]
        
        for pattern in selection_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                return match.group(1)
        
        return None
    
    def detect_package_selection(self, message: str, service: str, last_shown_list: Optional[str] = None) -> Optional[str]:
        """
        Detect package selection from message
        
        Returns: package number (1-3) or None
        """
        msg_lower = message.lower().strip()
        
        # Numeric selection (1-3)
        if last_shown_list == "packages":
            num_match = re.search(r'\b([1-3])\b', msg_lower)
            if num_match:
                return num_match.group(1)
        
        # Pattern matching
        selection_patterns = [
            r'(?:go\s+for|choose|select|pick|want|need)\s+([1-3])',
            r'([1-3])\s+(?:please|pls)',
            r'option\s+([1-3])',
            r'number\s+([1-3])'
        ]
        
        for pattern in selection_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                return match.group(1)
        
        # Keywords like "lowest", "cheapest", "highest", "premium"
        if 'lowest' in msg_lower or 'cheapest' in msg_lower or 'affordable' in msg_lower:
            return 'lowest_price'
        
        if 'highest' in msg_lower or 'premium' in msg_lower or 'best' in msg_lower or 'top' in msg_lower:
            return 'highest_price'
        
        if 'senior' in msg_lower or 'artist' in msg_lower:
            return 'senior_artist'
        
        if 'chirag' in msg_lower or 'signature' in msg_lower:
            return 'chirag_signature'
        
        return None
    
    def detect_completion_intent(self, message: str) -> bool:
        """Detect if user wants to complete/confirm"""
        msg_lower = message.lower()
        return any(keyword in msg_lower for keyword in self.completion_keywords)
    
    def detect_frustration(self, message: str) -> bool:
        """Detect user frustration"""
        msg_lower = message.lower()
        
        # Check frustration keywords
        has_frustration_keywords = any(
            keyword in msg_lower for keyword in self.frustration_keywords
        )
        
        # Check for excessive punctuation (!!!, ???)
        has_excessive_punctuation = bool(
            re.search(r'[!?]{2,}', message)
        )
        
        # Check for all caps (minimum 3 words)
        words = message.split()
        caps_words = [w for w in words if w.isupper() and len(w) > 2]
        has_all_caps = len(caps_words) >= 2
        
        return has_frustration_keywords or has_excessive_punctuation or has_all_caps
    
    def detect_exit_intent(self, message: str) -> bool:
        """Detect if user wants to exit"""
        msg_lower = message.lower()
        return any(keyword in msg_lower for keyword in self.exit_keywords)
    
    def detect_restart_intent(self, message: str) -> bool:
        """Detect if user wants to restart"""
        msg_lower = message.lower()
        return any(keyword in msg_lower for keyword in self.restart_keywords)
    
    def detect_affirmative(self, message: str) -> bool:
        """Detect affirmative response"""
        msg_lower = message.lower().strip()
        return any(keyword == msg_lower or keyword in msg_lower 
                  for keyword in self.affirmative_keywords)
    
    def detect_negative(self, message: str) -> bool:
        """Detect negative response"""
        msg_lower = message.lower().strip()
        return any(keyword == msg_lower or keyword in msg_lower 
                  for keyword in self.negative_keywords)
    
    def is_question(self, message: str) -> bool:
        """Detect if message is a question"""
        for pattern in self.question_patterns:
            if re.search(pattern, message.lower()):
                return True
        return False
    
    # ============== SCORING METHODS ==============
    
    def _score_booking_intent(self, message: str, context: Dict = None) -> float:
        """Score booking intent (0.0-1.0)"""
        score = 0.0
        
        # Strong keywords
        strong_matches = sum(1 for kw in self.booking_keywords if kw in message)
        score += min(strong_matches * 0.4, 0.8)
        
        # Numeric selection in service context
        if context and context.get('last_shown_list') == 'services':
            if re.match(r'^[1-4]$', message.strip()):
                score += 0.9
        
        # Pattern matching
        if re.search(r'i\s+(?:want|need|would\s+like)\s+to\s+book', message):
            score += 0.5
        
        return min(score, 1.0)
    
    def _score_info_intent(self, message: str) -> float:
        """Score info intent (0.0-1.0)"""
        score = 0.0
        
        # Info keywords
        info_matches = sum(1 for kw in self.info_keywords if kw in message)
        score += min(info_matches * 0.3, 0.7)
        
        # Booking keywords (negative score)
        booking_matches = sum(1 for kw in self.booking_keywords if kw in message)
        score -= booking_matches * 0.3
        
        # Question marks
        if '?' in message:
            score += 0.2
        
        return max(min(score, 1.0), 0.0)
    
    def _score_completion_intent(self, message: str) -> float:
        """Score completion intent (0.0-1.0)"""
        score = 0.0
        
        matches = sum(1 for kw in self.completion_keywords if kw in message)
        score += min(matches * 0.5, 1.0)
        
        return score
    
    def _score_exit_intent(self, message: str) -> float:
        """Score exit intent (0.0-1.0)"""
        score = 0.0
        
        matches = sum(1 for kw in self.exit_keywords if kw in message)
        score += min(matches * 0.6, 1.0)
        
        return score
    
    def _score_restart_intent(self, message: str) -> float:
        """Score restart intent (0.0-1.0)"""
        score = 0.0
        
        matches = sum(1 for kw in self.restart_keywords if kw in message)
        score += min(matches * 0.6, 1.0)
        
        return score
    
    def _score_question_intent(self, message: str) -> float:
        """Score question intent (0.0-1.0)"""
        score = 0.0
        
        for pattern in self.question_patterns:
            if re.search(pattern, message):
                score += 0.4
        
        return min(score, 1.0)
    
    def _score_affirmative(self, message: str) -> float:
        """Score affirmative response (0.0-1.0)"""
        msg = message.strip()
        
        if msg in self.affirmative_keywords:
            return 1.0
        
        matches = sum(1 for kw in self.affirmative_keywords if kw in message)
        return min(matches * 0.5, 1.0)
    
    def _score_negative(self, message: str) -> float:
        """Score negative response (0.0-1.0)"""
        msg = message.strip()
        
        if msg in self.negative_keywords:
            return 1.0
        
        matches = sum(1 for kw in self.negative_keywords if kw in message)
        return min(matches * 0.5, 1.0)
    
    # ============== HELPER METHODS ==============
    
    def _get_last_assistant_message(self, history: List) -> Optional[str]:
        """Get last assistant message from history"""
        for msg in reversed(history):
            if isinstance(msg, dict) and msg.get('role') == 'assistant':
                return msg.get('content', '').lower()
        return None
    
    def _has_service_list_context(self, message: str) -> bool:
        """Check if message contains service list"""
        indicators = ['1.', '2.', '3.', '4.', 'bridal', 'party', 'henna', 'service']
        return any(ind in message for ind in indicators)