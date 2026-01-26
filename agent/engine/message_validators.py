# agent/engine/message_validators.py
"""
Message validation utilities for FSM
"""
import re
from typing import List
from .engine_config import (
    QUESTION_STARTERS, SOCIAL_MEDIA_PATTERNS, OFF_TOPIC_PATTERNS,
    BOOKING_KEYWORDS, BOOKING_DETAIL_KEYWORDS, COMPLETION_KEYWORDS,
    CONFIRMATION_KEYWORDS, REJECTION_KEYWORDS
)


class MessageValidators:
    """Message validation utilities"""
    
    @staticmethod
    def is_booking_intent(message: str) -> bool:
        """Check if message indicates booking intent"""
        msg_lower = message.lower()
        booking_keywords = ['book', 'booking', 'reserve', 'schedule', 'appointment',
                           'i want to book', 'want to book', 'book service', 'i want your', 
                           'your services', 'your service', 'best services']
        return any(kw in msg_lower for kw in booking_keywords)
    
    @staticmethod
    def is_general_question(message: str) -> bool:
        """Check if message is a general question using master list"""
        msg_lower = message.lower().strip()
        
        # Check for question mark
        if '?' in message:
            return True
        
        # Check if it starts with any question starter
        for starter in QUESTION_STARTERS:
            if msg_lower.startswith(starter):
                # Safety filter: check if it contains booking keywords
                if any(b in msg_lower for b in BOOKING_KEYWORDS):
                    return False
                return True
        
        # Check for social media patterns
        for pattern in SOCIAL_MEDIA_PATTERNS:
            if pattern in msg_lower:
                return True
        
        # Check for off-topic patterns
        for pattern in OFF_TOPIC_PATTERNS:
            if pattern in msg_lower and len(msg_lower.split()) <= 5:
                return True
        
        return False
    
    @staticmethod
    def is_off_topic_question(message: str) -> bool:
        """Check if message is off-topic (not related to booking details)"""
        msg_lower = message.lower().strip()
        
        # Check for social media patterns
        for pattern in SOCIAL_MEDIA_PATTERNS:
            if pattern in msg_lower:
                return True
        
        # Check if it's a question starter AND doesn't contain booking detail keywords
        is_question = False
        for starter in QUESTION_STARTERS:
            if msg_lower.startswith(starter):
                is_question = True
                break
        
        if is_question:
            # Check if it contains booking detail keywords
            has_booking_detail = any(kw in msg_lower for kw in BOOKING_DETAIL_KEYWORDS)
            
            # If it's a question but doesn't have booking details, it's off-topic
            if not has_booking_detail:
                return True
        
        # Check for specific off-topic patterns
        off_topic_patterns = [
            'instagram', 'facebook', 'youtube', 'channel',
            'follow', 'subscribe', 'social media',
            'contact', 'reach', 'get in touch',
            'website', 'online', 'web',
            'about you', 'about your', 'who are you',
            'what do you do', 'where are you',
            'experience', 'portfolio', 'gallery',
            'rating', 'review', 'feedback', 'testimonial'
        ]
        
        for pattern in off_topic_patterns:
            if pattern in msg_lower:
                return True
        
        return False
    
    @staticmethod
    def is_completion_intent(message: str) -> bool:
        """Check if user wants to complete details"""
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in COMPLETION_KEYWORDS)
    
    @staticmethod
    def is_confirmation(message: str) -> bool:
        """Check if user confirms"""
        msg_lower = message.lower()
        return any(word in msg_lower for word in CONFIRMATION_KEYWORDS)
    
    @staticmethod
    def is_rejection(message: str) -> bool:
        """Check if user rejects/requests change"""
        msg_lower = message.lower()
        return any(word in msg_lower for word in REJECTION_KEYWORDS)
    
    @staticmethod
    def is_service_question(message: str) -> bool:
        """Check if message is asking about services, prices, etc."""
        msg_lower = message.lower()
        
        service_keywords = [
            'price', 'cost', 'charge', 'rate', 'fee',
            'how much', 'what is the price', 'what does it cost',
            'reception', 'senior', 'artist', 'package',
            'list', 'service', 'services', 'offer', 'provide'
        ]
        
        return any(kw in msg_lower for kw in service_keywords)