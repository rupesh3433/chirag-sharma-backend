# agent/models/memory.py
"""
Conversation Memory Model with off-track tracking
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

from .intent import BookingIntent


class ConversationMemory(BaseModel):
    """Conversation state and memory with off-track tracking"""
    
    session_id: str
    language: str = "en"
    intent: BookingIntent = Field(default_factory=BookingIntent)
    stage: str = "greeting"
    booking_id: Optional[str] = None
    otp_attempts: int = 0
    off_track_count: int = 0  # Track consecutive off-track messages
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    last_shown_list: Optional[str] = None
    last_asked_field: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True
    
    def add_message(self, role: str, content: str) -> None:
        """Add message to conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep only last 20 messages
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]
        
        self.last_updated = datetime.utcnow()
    
    def reset(self) -> None:
        """Reset memory for new booking"""
        self.intent = BookingIntent()
        self.stage = "greeting"
        self.booking_id = None
        self.otp_attempts = 0
        self.off_track_count = 0  # Reset off-track counter
        self.last_shown_list = None
        self.last_asked_field = None
        
        # Keep only system messages in history
        system_messages = [
            msg for msg in self.conversation_history 
            if msg.get("role") == "system"
        ]
        self.conversation_history = system_messages
        
        self.last_updated = datetime.utcnow()
    
    def get_context(self) -> str:
        """Get conversation context summary"""
        if not self.conversation_history:
            return "No conversation history."
        
        # Get last 5 messages
        recent_messages = self.conversation_history[-5:]
        
        context_lines = []
        for msg in recent_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]  # Truncate long messages
            context_lines.append(f"{role.upper()}: {content}")
        
        # Add current state info
        context_lines.append(f"\nCurrent Stage: {self.stage}")
        
        if self.intent.service:
            context_lines.append(f"Selected Service: {self.intent.service}")
        if self.intent.package:
            context_lines.append(f"Selected Package: {self.intent.package}")
        
        missing = self.intent.missing_fields()
        if missing:
            context_lines.append(f"Missing Fields: {', '.join(missing)}")
        
        return "\n".join(context_lines)
    
    def update_stage(self, stage: str) -> None:
        """Update stage and refresh timestamp"""
        self.stage = stage
        self.last_updated = datetime.utcnow()
    
    def increment_otp_attempts(self) -> None:
        """Increment OTP attempts"""
        self.otp_attempts += 1
        self.last_updated = datetime.utcnow()
    
    def increment_off_track_count(self) -> None:
        """Increment off-track count"""
        self.off_track_count += 1
        self.last_updated = datetime.utcnow()
    
    def reset_off_track_count(self) -> None:
        """Reset off-track count"""
        self.off_track_count = 0
        self.last_updated = datetime.utcnow()
    
    def get_recent_user_messages(self, count: int = 3) -> List[str]:
        """Get recent user messages"""
        user_messages = [
            msg["content"] for msg in self.conversation_history[-count*2:] 
            if msg.get("role") == "user"
        ]
        return user_messages[-count:] if user_messages else []