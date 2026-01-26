"""
Conversation Memory Model - Simplified
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

from .intent import BookingIntent


class ConversationMemory(BaseModel):
    """Conversation state and memory"""
    
    # Core fields
    session_id: str
    language: str = "en"
    intent: BookingIntent = Field(default_factory=BookingIntent)
    stage: str = "greeting"
    booking_id: Optional[str] = None
    otp_attempts: int = 0
    off_track_count: int = 0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    last_shown_list: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True
    
    # Essential methods only
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
        self.off_track_count = 0
        self.last_shown_list = None
        
        # Keep only system messages
        system_messages = [
            msg for msg in self.conversation_history 
            if msg.get("role") == "system"
        ]
        self.conversation_history = system_messages
        self.last_updated = datetime.utcnow()
    
    def update_stage(self, stage: str) -> None:
        """Update stage and refresh timestamp"""
        self.stage = stage
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
    
    def get_last_assistant_message(self) -> Optional[str]:
        """Get the last assistant message"""
        for msg in reversed(self.conversation_history):
            if msg.get("role") == "assistant":
                return msg.get("content", "")
        return None
    
    def get_conversation_summary(self, max_messages: int = 10) -> str:
        """Get summary of conversation for context"""
        if not self.conversation_history:
            return "No conversation yet."
        
        recent = self.conversation_history[-max_messages:]
        summary_lines = []
        
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if len(content) > 100:
                content = content[:100] + "..."
            summary_lines.append(f"{role}: {content}")
        
        # Add current state
        summary_lines.extend([
            f"\nCurrent stage: {self.stage}",
            f"Service: {self.intent.service or 'Not selected'}",
            f"Package: {self.intent.package or 'Not selected'}",
            f"Off-track count: {self.off_track_count}"
        ])
        
        return "\n".join(summary_lines)