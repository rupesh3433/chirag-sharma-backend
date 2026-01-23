from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import re

class BookingIntent(BaseModel):
    """Extracted booking information from conversation"""
    service: Optional[str] = None
    package: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_country: Optional[str] = None
    service_country: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    date: Optional[str] = None
    message: Optional[str] = None
    
    @validator('email')
    def validate_email(cls, v):
        if v and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w{2,}$', v):
            raise ValueError('Invalid email')
        return v
    
    @validator('phone')
    def validate_phone(cls, v):
        if v:
            # Must have country code
            if not v.startswith('+'):
                raise ValueError('Phone must start with country code (e.g., +91)')
            digits = re.sub(r'\D', '', v)
            if len(digits) < 10 or len(digits) > 15:
                raise ValueError('Phone must be 10-15 digits')
        return v
    
    @validator('date')
    def validate_date(cls, v):
        if v:
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
                raise ValueError('Date must be YYYY-MM-DD format')
        return v
    
    def is_complete(self) -> bool:
        """Check if all required fields are filled"""
        required = ['service', 'package', 'name', 'email', 'phone', 
                   'service_country', 'address', 'pincode', 'date']
        
        for field in required:
            value = getattr(self, field)
            if not value or value == "":
                return False
        
        # Special check: phone must have country code
        if self.phone and not self.phone.startswith('+'):
            return False
            
        return True
    
    def missing_fields(self) -> List[str]:
        """Get human-readable missing fields in priority order"""
        field_labels = {
            "service": "service type",
            "package": "package choice",
            "name": "your name",
            "email": "email address",
            "phone": "phone number with country code",
            "service_country": "service country",
            "address": "service address",
            "pincode": "PIN/postal code",
            "date": "preferred date"
        }
        
        priority_fields = ['service', 'package', 'name', 'email', 'phone', 
                          'service_country', 'address', 'pincode', 'date']
        
        missing = []
        for field in priority_fields:
            value = getattr(self, field)
            if not value or value == "":
                missing.append(field_labels.get(field, field))
            elif field == 'phone' and not value.startswith('+'):
                missing.append("phone number with country code")
        
        return missing
    
    def get_summary(self) -> Dict[str, str]:
        """Get a summary of collected info"""
        summary = {}
        fields = {
            "service": "Service",
            "package": "Package",
            "name": "Name",
            "email": "Email",
            "phone": "Phone",
            "phone_country": "Phone Country",
            "service_country": "Country",
            "address": "Address",
            "pincode": "PIN Code",
            "date": "Date",
            "message": "Message"
        }
        
        for field, label in fields.items():
            value = getattr(self, field)
            if value:
                if field == 'phone' and value:
                    # Mask phone for display
                    if len(value) > 8:
                        summary[label] = f"{value[:8]}****{value[-4:]}"
                    else:
                        summary[label] = value
                else:
                    summary[label] = value
        
        return summary
    
    def copy(self):
        """Create a copy of the intent"""
        return BookingIntent(**self.dict())

class ConversationMemory(BaseModel):
    """Conversation state and memory"""
    session_id: str
    language: str
    intent: BookingIntent = Field(default_factory=BookingIntent)
    stage: str = "greeting"
    booking_id: Optional[str] = None
    otp_attempts: int = 0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    last_shown_list: Optional[str] = None  # "services", "packages", "countries"
    last_asked_field: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True
    
    def add_message(self, role: str, content: str) -> None:
        """Add message to history with timestamp"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        if len(self.conversation_history) > 15:
            self.conversation_history = self.conversation_history[-15:]
    
    def reset(self) -> None:
        """Reset for new booking"""
        self.intent = BookingIntent()
        self.stage = "greeting"
        self.booking_id = None
        self.otp_attempts = 0
        self.last_shown_list = None
        self.last_asked_field = None
        self.conversation_history.clear()
    
    def get_context(self) -> str:
        """Get conversation context summary"""
        missing = self.intent.missing_fields()
        collected = self.intent.get_summary()
        
        context = f"Stage: {self.stage}\n"
        context += f"Missing: {', '.join(missing) if missing else 'None'}\n"
        context += "Collected:\n"
        for key, value in collected.items():
            context += f"  - {key}: {value}\n"
        
        return context

class AgentChatRequest(BaseModel):
    """Incoming chat request"""
    message: str
    session_id: Optional[str] = None
    language: str = "en"

class AgentChatResponse(BaseModel):
    """Agent response with state"""
    reply: str
    session_id: str
    stage: str
    action: str  # continue, send_otp, verify_otp, booking_confirmed, reset
    missing_fields: List[str]
    collected_info: Dict[str, str] = Field(default_factory=dict)
    booking_id: Optional[str] = None
    chat_mode: str = "agent"
    next_expected: Optional[str] = None