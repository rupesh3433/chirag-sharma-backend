from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Literal, List, Dict, Any
from datetime import datetime
import re

# ==========================================================
# AGENT STATE MODELS
# ==========================================================

class BookingIntent(BaseModel):
    """Extracted booking information from conversation"""
    service: Optional[str] = None
    package: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None  # Changed from EmailStr to allow None
    phone: Optional[str] = None
    phone_country: Optional[str] = None
    service_country: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    date: Optional[str] = None
    message: Optional[str] = None
    
    @validator('email')
    def validate_email(cls, v):
        if v is not None:
            # Simple email validation
            email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_regex, v):
                raise ValueError('Invalid email format')
        return v
    
    def copy(self):
        """Create a copy of the intent"""
        return BookingIntent(**self.dict())

class ConversationMemory(BaseModel):
    """Conversation state and memory"""
    session_id: str
    language: str
    intent: BookingIntent = Field(default_factory=BookingIntent)
    stage: Literal["greeting", "collecting_info", "otp_sent", "otp_verification", "confirmed"] = "greeting"
    booking_id: Optional[str] = None
    otp_attempts: int = 0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class AgentResponse(BaseModel):
    """Response from agent including state and reply"""
    reply: str
    memory: ConversationMemory
    action: Optional[Literal["send_otp", "verify_otp", "booking_confirmed", "continue"]] = "continue"
    missing_fields: List[str] = []
    chat_mode: Literal["normal", "agent"] = "agent"  # Add this field